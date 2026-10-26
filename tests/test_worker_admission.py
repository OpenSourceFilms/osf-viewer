"""Loopback-only integration tests of bounded Viewer request worker admission.

No live Viewer, archive, file storage, credentials or reverse proxy is used.
These use a disposable localhost server with a synthetic blocking handler.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler
import queue
import socket
import threading
import unittest

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from request_limits import BoundedViewerServer  # noqa: E402


class ControlledHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/hold":
            self.server.entered.put(True)
            if not self.server.release_workers.wait(timeout=5):
                self.send_error(500, "fixture timeout")
                return
        body = b"synthetic response"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class ObservableServer(BoundedViewerServer):
    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.completed.put(True)


class ViewerWorkerLimitTests(unittest.TestCase):
    def setUp(self):
        self.server = ObservableServer(
            ("127.0.0.1", 0), ControlledHandler,
            max_active=2, socket_timeout_s=2.0,
        )
        self.server.entered = queue.Queue()
        self.server.completed = queue.Queue()
        self.server.release_workers = threading.Event()
        self.server_thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )
        self.server_thread.start()
        self.sockets = []

    def tearDown(self):
        self.server.release_workers.set()
        for connection in self.sockets:
            connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=2)

    def request(self, path="/hold"):
        connection = socket.create_connection(self.server.server_address, timeout=3)
        connection.settimeout(3)
        self.sockets.append(connection)
        connection.sendall(
            ("GET " + path + " HTTP/1.0\r\n"
             "Host: localhost\r\nConnection: close\r\n\r\n").encode()
        )
        return connection

    def read_response(self, connection):
        parts = []
        while True:
            chunk = connection.recv(16384)
            if not chunk:
                break
            parts.append(chunk)
        return b"".join(parts)

    def test_overflow_returns_503_before_starting_another_worker(self):
        first = self.request()
        second = self.request()
        self.server.entered.get(timeout=3)
        self.server.entered.get(timeout=3)

        third = self.request("/hold")
        overloaded = self.read_response(third)
        self.assertIn(b"503 Service Unavailable", overloaded)
        self.assertIn(b"Retry-After: 1", overloaded)
        self.assertIn(b"Connection: close", overloaded)
        self.assertTrue(self.server.entered.empty())

        self.server.release_workers.set()
        self.assertIn(b"200 OK", self.read_response(first))
        self.assertIn(b"200 OK", self.read_response(second))
        self.server.completed.get(timeout=3)
        self.server.completed.get(timeout=3)

        fourth = self.request("/ready")
        self.assertIn(b"200 OK", self.read_response(fourth))
        self.server.completed.get(timeout=3)

    def test_overflow_rejects_multiple_connections_without_worker_growth(self):
        self.request("/hold")
        self.request("/hold")
        self.server.entered.get(timeout=3)
        self.server.entered.get(timeout=3)
        for _ in range(5):
            overflow = self.request("/hold")
            self.assertIn(b"503 Service Unavailable", self.read_response(overflow))
        self.assertTrue(self.server.entered.empty())

    def test_invalid_worker_limits_are_rejected(self):
        for value in (0, -1, 1.5, True, 33):
            with self.subTest(value=value), self.assertRaises(ValueError):
                BoundedViewerServer(("127.0.0.1", 0), ControlledHandler,
                                    max_active=value)

    def test_source_starts_admission_control_instead_of_unbounded_server(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("httpd = BoundedViewerServer(", source)
        self.assertIn("MAX_ACTIVE_REQUESTS = 2", source)
        self.assertNotIn("httpd = ThreadingHTTPServer(", source)


if __name__ == "__main__":
    unittest.main()
