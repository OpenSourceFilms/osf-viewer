"""Offline regression for fail-closed Viewer denylist configuration.

Only disposable filesystem data and a stubbed Viewer handler are used.
Tests never bind a listener, read /workspace or access real credentials.
"""
from __future__ import annotations

from pathlib import Path
import runpy
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import security  # noqa: E402


def load_app_with_stubbed_inspectors():
    inspectors = types.ModuleType("inspectors")
    inspectors.get_text = lambda *args, **kwargs: "synthetic"
    with mock.patch.dict(sys.modules, {"inspectors": inspectors}):
        namespace = runpy.run_path(str(ROOT / "app.py"), run_name="viewer_policy_test")
    return namespace["ViewerHandler"], namespace["main"]


class DenylistFailureTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="osfv_policy_")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.root = self.base / "published"
        self.root.mkdir()
        (self.root / "safe.txt").write_text("synthetic non-sensitive text")
        (self.root / ".pod-persist").mkdir()
        (self.root / ".pod-persist" / "synthetic-secret.txt").write_text(
            "synthetic test data"
        )
        self.policy = self.base / "denylist.txt"
        self.write_policy()

    def write_policy(self, *, omit=(), extra=()):
        rules = sorted(set(security.REQUIRED_DENY_PATHS) - set(omit))
        self.policy.write_text(
            "# disposable Viewer denylist for tests\n"
            + "\n".join(rules + list(extra)) + "\n", encoding="utf-8"
        )

    def test_valid_baseline_denies_private_root_and_allows_public(self):
        rules = security.load_denylist(self.root, self.policy)
        self.assertEqual(security.safe_resolve(self.root, "safe.txt", rules),
                         (self.root / "safe.txt").resolve())
        with self.assertRaises(PermissionError):
            security.safe_resolve(self.root, ".pod-persist/synthetic-secret.txt", rules)

    def test_missing_policy_fails_closed(self):
        self.policy.unlink()
        with self.assertRaises(security.DenylistUnavailable):
            security.load_denylist(self.root, self.policy)

    def test_empty_policy_fails_closed(self):
        self.policy.write_text("# comments only\n")
        with self.assertRaises(security.DenylistUnavailable):
            security.load_denylist(self.root, self.policy)

    def test_missing_each_required_exclusion_fails_closed(self):
        for required in security.REQUIRED_DENY_PATHS:
            with self.subTest(missing=required):
                self.write_policy(omit=(required,))
                with self.assertRaises(security.DenylistUnavailable):
                    security.load_denylist(self.root, self.policy)

    def test_absolute_traversal_or_malformed_lines_fail_closed(self):
        for line in ("/outside", "../outside", "inside/../../outside",
                     "nested//secret", "inside\\other", "inside/./secret"):
            with self.subTest(line=line):
                self.write_policy(extra=(line,))
                with self.assertRaises(security.DenylistUnavailable):
                    security.load_denylist(self.root, self.policy)

    def test_unreadable_or_directory_policy_fails_closed(self):
        self.policy.write_bytes(b"\xff")
        with self.assertRaises(security.DenylistUnavailable):
            security.load_denylist(self.root, self.policy)
        self.policy.unlink()
        self.policy.mkdir()
        with self.assertRaises(security.DenylistUnavailable):
            security.load_denylist(self.root, self.policy)

    def test_configured_symlink_escape_fails_closed(self):
        outside = self.base / "outside"
        outside.mkdir()
        (self.root / "escape").symlink_to(outside, target_is_directory=True)
        self.write_policy(extra=("escape",))
        with self.assertRaises(security.DenylistUnavailable):
            security.load_denylist(self.root, self.policy)

    def test_http_health_and_content_refuse_missing_policy_then_recover(self):
        Handler, _ = load_app_with_stubbed_inspectors()
        handler = object.__new__(Handler)
        output = []
        served = []
        handler._send_text = lambda status, body: output.append((status, body))
        handler._handle_raw = lambda real: served.append(real)

        env = Handler._dispatch.__globals__
        with mock.patch.dict(env, {
            "ROOT": self.root,
            "DENYLIST_FILE": self.policy,
            "_DENYLIST_LOADED_AT": 0.0,
            "_DENYLIST_CACHE": [],
        }):
            self.policy.unlink()
            handler.path = "/__view_health__"
            handler.do_GET()
            self.assertEqual(output[-1][0], 503)
            self.assertNotIn(str(self.root), output[-1][1])

            handler.path = "/__view__/safe.txt/raw"
            handler.do_GET()
            self.assertEqual(output[-1][0], 503)
            self.assertFalse(served)

            self.write_policy()
            handler.path = "/__view_health__"
            handler.do_GET()
            self.assertEqual(output[-1], (200, "ok"))
            handler.path = "/__view__/safe.txt/raw"
            handler.do_GET()
            self.assertEqual(served, [(self.root / "safe.txt").resolve()])

    def test_startup_refuses_to_bind_without_policy(self):
        _, main = load_app_with_stubbed_inspectors()
        env = main.__globals__
        def reject_any_listener(*args, **kwargs):
            raise AssertionError("must not create HTTP listener without policy")
        self.policy.unlink()
        with mock.patch.dict(env, {
            "ROOT": self.root,
            "DENYLIST_FILE": self.policy,
            "_DENYLIST_LOADED_AT": 0.0,
            "_DENYLIST_CACHE": [],
            "BoundedViewerServer": reject_any_listener,
        }):
            with self.assertRaises(security.DenylistUnavailable):
                main()


if __name__ == "__main__":
    unittest.main()
