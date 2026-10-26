"""Zero-dependency regression tests for public Viewer HTTP error sanitisation.

Loads the real app.py handler with stubbed optional inspector dependencies.
No HTTP socket is bound, production filesystem accessed or service changed.
"""
from __future__ import annotations

import io
from pathlib import Path
import runpy
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
SECRET = "synthetic-secret-path-/workspace/.pod-persist/secrets/test.env"


def load_handler_with_stub_inspectors():
    inspectors = types.ModuleType("inspectors")
    inspectors.read_archive_member = lambda *args: None
    inspectors.identify = lambda *args: "archive"
    inspectors.list_archive_members = lambda *args: []
    inspectors.get_text = lambda *args, **kwargs: "synthetic diagnostic text"
    with mock.patch.dict(sys.modules, {"inspectors": inspectors}):
        namespace = runpy.run_path(str(APP), run_name="viewer_handler_test")
    return namespace["ViewerHandler"], namespace, inspectors


def fake_handler(handler_type):
    handler = object.__new__(handler_type)
    handler.command = "GET"
    responses = []

    def record(code, body, content_type="text/plain; charset=utf-8"):
        responses.append((code, body, content_type))

    handler._send_text = record
    return handler, responses


class ViewerErrorRedactionTests(unittest.TestCase):
    def test_unexpected_dispatch_error_never_reveals_exception_or_traceback(self):
        cls, _, _ = load_handler_with_stub_inspectors()
        handler, sent = fake_handler(cls)

        def failure():
            raise RuntimeError(SECRET)

        handler._dispatch = failure
        stderr = io.StringIO()
        with mock.patch("sys.stderr", stderr):
            handler.do_GET()
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0], 500)
        self.assertEqual(sent[0][1], "internal server error")
        self.assertNotIn(SECRET, sent[0][1])
        self.assertNotIn("Traceback", sent[0][1])
        self.assertNotIn(SECRET, stderr.getvalue())
        self.assertIn("RuntimeError", stderr.getvalue())

    def test_unexpected_dispatch_error_on_head_returns_generic_message(self):
        cls, _, _ = load_handler_with_stub_inspectors()
        handler, sent = fake_handler(cls)
        handler.command = "HEAD"

        def failure():
            raise PermissionError(SECRET)

        handler._dispatch = failure
        with mock.patch("sys.stderr", io.StringIO()):
            handler.do_HEAD()
        self.assertEqual(sent[0][0], 500)
        self.assertEqual(sent[0][1], "internal server error")

    def test_archive_member_error_does_not_reflect_member_or_exception_details(self):
        cls, _, inspectors = load_handler_with_stub_inspectors()
        handler, sent = fake_handler(cls)

        def failure(*_args):
            raise RuntimeError(SECRET)

        inspectors.read_archive_member = failure
        handler._handle_member(
            ROOT / "synthetic.zip",
            "synthetic.zip",
            "chosen-name-" + SECRET,
            "text",
        )
        self.assertEqual(sent[0][0], 200)
        self.assertIn("could not extract", sent[0][1])
        self.assertNotIn(SECRET, sent[0][1])
        self.assertNotIn("RuntimeError", sent[0][1])

    def test_archive_listing_error_does_not_return_exception(self):
        cls, namespace, inspectors = load_handler_with_stub_inspectors()
        handler, sent = fake_handler(cls)

        def failure(*_args):
            raise RuntimeError(SECRET)

        inspectors.list_archive_members = failure
        with mock.patch.dict(namespace, {"_denied_predicate": lambda: (lambda p: False)}):
            # The function globals belong to app.py's runpy namespace.
            # Inject a safe predicate so no deployed root or denylist is read.
            handler._handle_hub(None, "synthetic.zip", member_bytes=b"fake")
        self.assertEqual(sent[0][0], 200)
        self.assertIn("could not list archive members", sent[0][1])
        self.assertNotIn(SECRET, sent[0][1])
        self.assertNotIn("RuntimeError", sent[0][1])


if __name__ == "__main__":
    unittest.main()
