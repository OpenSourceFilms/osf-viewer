"""Synthetic preview-cache identity tests, including actual Office cache calls.

No credentials, sockets, production files, office converters or GPU used.
"""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

import cache
import office_extract


class PreviewCacheIdentityTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(prefix="osfv_cache_identity_")
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        patcher = mock.patch.object(cache, "CACHE_DIR", self.root / "cache")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.source = self.root / "sample.png"
        self.source.write_bytes(b"ALPHA")
        self.source_mtime = self.source.stat().st_mtime_ns

    def key(self, identity):
        return cache._key_path("test/shot.png", 5, 100.0, ".pdf", identity)

    def test_same_path_size_mtime_replacement_invalidates_old_pdf(self):
        first = cache.source_fingerprint(self.source, None)
        cache.put("test/shot.png", 5, 100.0, ".pdf", b"PDF-ALPHA", first)
        self.assertEqual(cache.get("test/shot.png", 5, 100.0, ".pdf", first),
                         b"PDF-ALPHA")

        replacement = self.root / "replacement.tmp"
        replacement.write_bytes(b"BRAVO")  # same byte count
        os.utime(replacement, ns=(self.source_mtime, self.source_mtime))
        replacement.replace(self.source)
        self.assertEqual(self.source.stat().st_size, 5)
        self.assertEqual(self.source.stat().st_mtime_ns, self.source_mtime)

        second = cache.source_fingerprint(self.source, None)
        self.assertNotEqual(first, second)
        self.assertIsNone(cache.get("test/shot.png", 5, 100.0, ".pdf", second))
        cache.put("test/shot.png", 5, 100.0, ".pdf", b"PDF-BRAVO", second)
        self.assertEqual(cache.get("test/shot.png", 5, 100.0, ".pdf", second),
                         b"PDF-BRAVO")

    def test_same_archive_member_name_size_and_mtime_cannot_reuse_old_preview(self):
        original = b"AAAA"
        modified = b"BBBB"
        a = cache.source_fingerprint(None, original)
        b = cache.source_fingerprint(None, modified)
        self.assertNotEqual(a, b)
        cache.put("archive.zip!frame.png", 4, 0.0, ".pdf", b"OLD-PDF", a)
        self.assertIsNone(cache.get("archive.zip!frame.png", 4, 0.0, ".pdf", b))
        cache.put("archive.zip!frame.png", 4, 0.0, ".pdf", b"NEW-PDF", b)
        self.assertEqual(cache.get("archive.zip!frame.png", 4, 0.0, ".pdf", b),
                         b"NEW-PDF")
        self.assertEqual(cache.get("archive.zip!frame.png", 4, 0.0, ".pdf", a),
                         b"OLD-PDF")

    def test_existing_source_identity_reuses_canonical_cache_entry(self):
        original = cache.source_fingerprint(None, b"unchanged")
        cache.put("archive.zip!member.docx", 9, 0.0, ".pdf", b"PDF", original)
        self.assertEqual(cache.get("archive.zip!member.docx", 9, 0.0,
                                   ".pdf", original), b"PDF")
        self.assertEqual(list(cache.CACHE_DIR.glob("*.pdf")), [
            cache._key_path("archive.zip!member.docx", 9, 0.0, ".pdf", original),
        ])

    def test_office_preview_conversion_is_not_reused_across_changed_member(self):
        calls = []

        def synthetic_convert(_path, data, _kind, _target):
            calls.append(data)
            return b"converted:" + data

        with mock.patch.object(office_extract, "_convert_with_soffice",
                               side_effect=synthetic_convert):
            results = [
                office_extract.get_preview_pdf(None, data, "member.docx", "docx",
                                               "archive.zip!member.docx", 4, 0.0)
                for data in (b"AAAA", b"BBBB", b"BBBB")
            ]
        self.assertEqual(results, [b"converted:AAAA", b"converted:BBBB",
                                   b"converted:BBBB"])
        self.assertEqual(calls, [b"AAAA", b"BBBB"])

    def test_concurrent_same_key_publications_never_leave_partial_tmp(self):
        identity = cache.source_fingerprint(None, b"source")
        failures = []
        payloads = (b"A" * 120000, b"B" * 160000, b"C" * 90000)
        ready = threading.Barrier(len(payloads))

        def publish(content):
            try:
                ready.wait(timeout=5)
                cache.put("a", 6, 1.0, ".pdf", content, identity)
            except Exception as exc:
                failures.append(type(exc).__name__)

        threads = [threading.Thread(target=publish, args=(p,))
                   for p in payloads]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(failures, [])
        self.assertIn(cache.get("a", 6, 1.0, ".pdf", identity), payloads)
        self.assertEqual(list(cache.CACHE_DIR.glob("*.tmp")), [])

    def test_missing_source_identity_refused(self):
        with self.assertRaisesRegex(ValueError, "file or an in-memory"):
            cache.source_fingerprint(None, None)
        with self.assertRaisesRegex(ValueError, "missing preview source identity"):
            cache.get("a", 1, 1.0, ".pdf", "")


if __name__ == "__main__":
    unittest.main()
