"""Regression tests: directory listings must omit denied entries.

Covers the 2026-09-08 finding that the HTML hub and the /text directory
listing built their own entry lists (real.iterdir() / path.iterdir()) without
consulting security.is_denied() -- so a denied path's *name* was visible in a
listing even though a direct fetch of it correctly 403'd. Fixed by threading
the same security.is_denied() predicate through both listing paths instead of
adding a second, independent check.

Run with: /workspace/services/osf_viewer/.venv/bin/python -m unittest
          tests.test_denied_listing -v
(from /workspace/services/osf_viewer/)
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import inspectors  # noqa: E402
import security  # noqa: E402


class DeniedListingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="osfv_test_"))
        # a directory laid out like a real project: one denied-by-basename
        # dir (.claude, matching security.DENIED_BASENAMES), one denied-by-
        # denylist.txt-style path (secrets/), and two ordinary siblings.
        (self.tmp / ".claude").mkdir()
        (self.tmp / ".claude" / "settings.local.json").write_text("{}")
        (self.tmp / "secrets").mkdir()
        (self.tmp / "secrets" / "token.txt").write_text("shh")
        (self.tmp / "README.md").write_text("hello")
        (self.tmp / "notes.txt").write_text("world")
        self.denylist = [(self.tmp / "secrets").resolve()]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _pred(self):
        dl = self.denylist
        root = self.tmp
        return lambda p: security.is_denied(p, dl, root)

    def test_is_denied_covers_basename_and_denylist(self):
        pred = self._pred()
        self.assertTrue(pred(self.tmp / ".claude"))
        self.assertTrue(pred(self.tmp / "secrets"))
        self.assertFalse(pred(self.tmp / "README.md"))
        self.assertFalse(pred(self.tmp / "notes.txt"))

    def test_direct_fetch_still_denied(self):
        # safe_resolve must still 403 (raise PermissionError) for both --
        # the listing fix must not have loosened direct-access enforcement.
        with self.assertRaises(PermissionError):
            security.safe_resolve(self.tmp, ".claude/settings.local.json", self.denylist)
        with self.assertRaises(PermissionError):
            security.safe_resolve(self.tmp, "secrets/token.txt", self.denylist)
        real = security.safe_resolve(self.tmp, "README.md", self.denylist)
        self.assertTrue(real.exists())

    def test_text_directory_listing_omits_denied(self):
        listing = inspectors._text_directory(self.tmp, self._pred())
        self.assertNotIn(".claude", listing)
        self.assertNotIn("secrets", listing)
        self.assertIn("README.md", listing)
        self.assertIn("notes.txt", listing)
        # header count must reflect the FILTERED list, not the true on-disk
        # count, so it can't be used to infer how many entries are hidden.
        self.assertIn("entries: 2", listing)

    def test_text_directory_listing_without_predicate_is_unfiltered(self):
        # sanity: confirms filtering is opt-in via is_denied, not
        # accidentally always-on -- i.e. the predicate is doing the work.
        listing = inspectors._text_directory(self.tmp, None)
        self.assertIn(".claude", listing)
        self.assertIn("secrets", listing)

    def test_get_text_dispatches_directory_with_predicate(self):
        listing = inspectors.get_text(self.tmp, None, str(self.tmp), is_denied=self._pred())
        self.assertNotIn(".claude", listing)
        self.assertNotIn("secrets", listing)
        self.assertIn("README.md", listing)


if __name__ == "__main__":
    unittest.main()
