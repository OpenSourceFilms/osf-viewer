"""Bounded request-worker admission for the public read-only Viewer.

ThreadingHTTPServer otherwise creates a new thread for every accepted
connection, including concurrent expensive archive/office/preview requests.
This subclass rejects excess sockets before spawning request threads.

This is a concurrency control, not a sandbox or process-wide byte/CPU quota.
"""
from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer


class BoundedViewerServer(ThreadingHTTPServer):
    """Reject overflow with 503 before starting an unbounded worker thread."""

    request_queue_size = 8
    daemon_threads = True

    def __init__(self, server_address, RequestHandlerClass, *,
                 max_active: int = 2, socket_timeout_s: float = 30.0):
        if type(max_active) is not int or max_active < 1 or max_active > 32:
            raise ValueError("max_active must be an integer between 1 and 32")
        if not 0 < socket_timeout_s <= 300:
            raise ValueError("socket_timeout_s must be in (0, 300]")
        self.max_active = max_active
        self.socket_timeout_s = socket_timeout_s
        self._worker_slots = threading.BoundedSemaphore(max_active)
        super().__init__(server_address, RequestHandlerClass)

    def process_request(self, request, client_address):
        # Called from the accept loop, not from a worker thread. A nonblocking
        # admission decision prevents a socket flood from spawning unlimited
        # blocked worker threads. No queue of waiting workers is created.
        if not self._worker_slots.acquire(blocking=False):
            self._reject_over_capacity(request)
            return
        try:
            request.settimeout(self.socket_timeout_s)
            super().process_request(request, client_address)
        except BaseException:
            # If spawning the worker fails, there is no worker to release it.
            self._worker_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._worker_slots.release()

    def _reject_over_capacity(self, request):
        try:
            request.settimeout(0.2)
            request.sendall(
                b"HTTP/1.1 503 Service Unavailable\r\n"
                b"Content-Type: text/plain; charset=utf-8\r\n"
                b"Content-Length: 0\r\n"
                b"Retry-After: 1\r\n"
                b"Connection: close\r\n"
                b"Cache-Control: no-store\r\n\r\n"
            )
        except OSError:
            # Drop overload connections without printing requester data.
            pass
        finally:
            self.shutdown_request(request)
