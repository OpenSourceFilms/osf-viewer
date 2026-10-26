"""Native PDF streaming regression without deployment or optional PDF packages.

The tests load the actual Viewer HTTP handler with a stub inspector, use
synthetic files in a temporary directory and never bind a network socket.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import runpy
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load_viewer():
    inspectors = types.ModuleType("inspectors")
    inspector_calls = []
    inspectors.is_native_pdf = lambda path, name: name.endswith(".pdf")

    def get_preview_pdf(*args):
        inspector_calls.append(args)
        return b"%PDF-generated-synthetic"

    inspectors.get_preview_pdf = get_preview_pdf
    with mock.patch.dict(sys.modules, {"inspectors": inspectors}):
        namespace = runpy.run_path(str(ROOT / "app.py"), run_name="pdf_stream_test")
    return namespace["ViewerHandler"], inspector_calls


class CountingWriter:
    def __init__(self):
        self.digest = hashlib.sha256()
        self.nbytes = 0
        self.max_chunk = 0
        self.calls = 0

    def write(self, chunk):
        self.digest.update(chunk)
        self.nbytes += len(chunk)
        self.max_chunk = max(self.max_chunk, len(chunk))
        self.calls += 1
        return len(chunk)


def fake_handler(klass, command="GET"):
    handler = object.__new__(klass)
    handler.command = command
    headers = []
    statuses = []
    handler.send_response = lambda code: statuses.append(code)
    handler.send_header = lambda name, value: headers.append((name, value))
    handler.end_headers = lambda: None
    handler.wfile = CountingWriter()
    return handler, statuses, headers


class NativePdfStreamingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="osfv_native_pdf_")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.pdf = self.base / "synthetic.pdf"
        block = b"%PDF-synthetic-no-real-content\n" + b"A" * (8192 - 31)
        # Deliberately more than the 1 MiB stream read cap.
        payload = block * 385
        self.assertGreater(len(payload), 3 * 1024 * 1024)
        self.pdf.write_bytes(payload)
        self.payload_digest = hashlib.sha256(payload).digest()

    def test_native_pdf_get_streams_correct_bytes_in_bounded_chunks(self):
        Handler, calls = load_viewer()
        handler, statuses, headers = fake_handler(Handler)
        handler._handle_preview_pdf(self.pdf, None, "synthetic.pdf")
        self.assertEqual(statuses, [200])
        self.assertIn(("Content-Type", "application/pdf"), headers)
        self.assertIn(("Content-Length", str(self.pdf.stat().st_size)), headers)
        self.assertEqual(handler.wfile.nbytes, self.pdf.stat().st_size)
        self.assertEqual(handler.wfile.digest.digest(), self.payload_digest)
        self.assertLessEqual(handler.wfile.max_chunk, 1024 * 1024)
        self.assertGreater(handler.wfile.calls, 1)
        self.assertEqual(calls, [], "PDF must bypass inspector bytes allocation")

    def test_native_pdf_head_sends_headers_without_copying_file(self):
        Handler, calls = load_viewer()
        handler, statuses, headers = fake_handler(Handler, "HEAD")
        with mock.patch.dict(Handler._stream_file.__globals__, {
            "shutil": types.SimpleNamespace(
                copyfileobj=lambda *args, **kwargs: self.fail("HEAD must not copy")
            )
        }):
            handler._handle_preview_pdf(self.pdf, None, "synthetic.pdf")
        self.assertEqual(statuses, [200])
        self.assertIn(("Content-Length", str(self.pdf.stat().st_size)), headers)
        self.assertEqual(handler.wfile.calls, 0)
        self.assertEqual(calls, [])

    def test_archive_pdf_member_still_uses_in_memory_preview(self):
        Handler, calls = load_viewer()
        handler, statuses, headers = fake_handler(Handler)
        content = b"%PDF-small-archive-member"
        handler._handle_preview_pdf(None, content, "archive.zip!nested/file.pdf")
        self.assertEqual(statuses, [200])
        self.assertEqual(handler.wfile.nbytes, len(b"%PDF-generated-synthetic"))
        self.assertEqual(len(calls), 1)
        self.assertIsNone(calls[0][0])
        self.assertEqual(calls[0][1], content)

    def test_generated_image_preview_path_remains_unchanged(self):
        Handler, calls = load_viewer()
        file_path = self.base / "image.png"
        file_path.write_bytes(b"synthetic-image")
        handler, statuses, headers = fake_handler(Handler)
        handler._handle_preview_pdf(file_path, None, "image.png")
        self.assertEqual(statuses, [200])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], file_path)
        self.assertEqual(handler.wfile.nbytes, len(b"%PDF-generated-synthetic"))

    def test_raw_stream_uses_same_descriptor_bound_chunked_path(self):
        Handler, calls = load_viewer()
        handler, statuses, headers = fake_handler(Handler)
        handler._stream_file(self.pdf, "application/octet-stream")
        self.assertEqual(statuses, [200])
        self.assertEqual(handler.wfile.digest.digest(), self.payload_digest)
        self.assertLessEqual(handler.wfile.max_chunk, 1024 * 1024)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
