"""Offline symlink-deny contract for the public file viewer."""
from __future__ import annotations
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import security

class SymlinkDenyTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(prefix="osfv_link_")
        self.addCleanup(t.cleanup)
        self.base = Path(t.name)
        self.root = self.base / "published"
        self.root.mkdir()
        self.denied = self.root / "private"
        self.denied.mkdir()
        (self.denied / "secret.txt").write_text("synthetic")
        self.allowed = self.root / "allowed.txt"
        self.allowed.write_text("synthetic")
        self.denylist = [self.denied.resolve()]

    def test_alias_into_denied_folder(self):
        (self.root / "alias").symlink_to(self.denied, target_is_directory=True)
        self.assertTrue(security.is_denied(self.root / "alias", self.denylist, self.root))
        with self.assertRaises(PermissionError):
            security.safe_resolve(self.root, "alias/secret.txt", self.denylist)

    def test_alias_outside_public_root(self):
        outside = self.base / "outside.txt"
        outside.write_text("synthetic")
        (self.root / "external").symlink_to(outside)
        self.assertTrue(security.is_denied(self.root / "external", self.denylist, self.root))
        with self.assertRaises(PermissionError):
            security.safe_resolve(self.root, "external", self.denylist)

    def test_denied_basename_symlink_remains_denied(self):
        (self.root / ".claude").symlink_to(self.root, target_is_directory=True)
        self.assertTrue(security.is_denied(self.root / ".claude", self.denylist, self.root))
        with self.assertRaises(PermissionError):
            security.safe_resolve(self.root, ".claude/allowed.txt", self.denylist)

    def test_allowed_symlink_remains_accessible(self):
        (self.root / "link").symlink_to(self.allowed)
        self.assertFalse(security.is_denied(self.root / "link", self.denylist, self.root))
        self.assertEqual(security.safe_resolve(self.root, "link", self.denylist),
                         self.allowed.resolve())

    def test_symlink_loop_denied(self):
        (self.root / "a").symlink_to(self.root / "b")
        (self.root / "b").symlink_to(self.root / "a")
        self.assertTrue(security.is_denied(self.root / "a", self.denylist, self.root))
        with self.assertRaises(PermissionError):
            security.safe_resolve(self.root, "a", self.denylist)

    def test_nested_private_basename_denied(self):
        (self.root / "project").mkdir()
        (self.root / "project" / ".claude").mkdir()
        self.assertTrue(security.is_denied(self.root / "project" / ".claude",
                                           self.denylist, self.root))

if __name__ == "__main__":
    unittest.main()
