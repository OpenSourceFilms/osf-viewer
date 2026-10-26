"""CPU-only acceptance of bounded TAR metadata scans.

Synthetic archives only. The limit must bound parsed TAR header count, not
just the final output list. ZIP/7z use separate parser implementations.
"""
from __future__ import annotations

import io
from pathlib import Path
import sys
import tarfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import archive_memory as am  # noqa: E402


def synthetic_tar(n: int = 12, duplicate: bool = False) -> bytes:
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as arc:
        for i in range(n):
            payload = f"synthetic-{i}".encode()
            name = "file_0001" if duplicate and i == 2 else f"file_{i:04d}"
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            arc.addfile(info, io.BytesIO(payload))
    return out.getvalue()


class BoundedTarHeaderScanTests(unittest.TestCase):
    def test_truncated_scan_reads_at_most_cap_plus_one_header(self):
        with tarfile.open(fileobj=io.BytesIO(synthetic_tar(40)), mode="r:") as arc:
            entries, truncated = am.scan_tar_headers(arc, 3)
            self.assertEqual([i.name for i in entries],
                             ["file_0000", "file_0001", "file_0002"])
            self.assertTrue(truncated)
            self.assertEqual(len(arc.members), 4)  # one lookahead only
            self.assertFalse(arc._loaded)

    def test_short_archive_reports_not_truncated(self):
        with tarfile.open(fileobj=io.BytesIO(synthetic_tar(3)), mode="r:") as arc:
            entries, truncated = am.scan_tar_headers(arc, 5)
            self.assertEqual(len(entries), 3)
            self.assertFalse(truncated)
            self.assertTrue(arc._loaded)

    def test_member_beyond_list_cap_is_not_accessible(self):
        with tarfile.open(fileobj=io.BytesIO(synthetic_tar(12)), mode="r:") as arc:
            with self.assertRaises(KeyError):
                am.read_tar_member(arc, "file_0007", 64, max_entries=5)
            self.assertLessEqual(len(arc.members), 6)

    def test_member_within_cap_still_returns_actual_bytes(self):
        with tarfile.open(fileobj=io.BytesIO(synthetic_tar(12)), mode="r:") as arc:
            self.assertEqual(am.read_tar_member(arc, "file_0003", 64, max_entries=5),
                             b"synthetic-3")
            self.assertLessEqual(len(arc.members), 6)

    def test_duplicate_within_scanned_prefix_is_rejected(self):
        with tarfile.open(fileobj=io.BytesIO(synthetic_tar(5, duplicate=True)),
                          mode="r:") as arc:
            with self.assertRaises(KeyError):
                am.read_tar_member(arc, "file_0001", 64, max_entries=5)

    def test_already_loaded_tarfile_remains_supported(self):
        with tarfile.open(fileobj=io.BytesIO(synthetic_tar(5)), mode="r:") as arc:
            self.assertEqual(len(arc.getmembers()), 5)
            self.assertEqual(am.read_tar_member(arc, "file_0004", 64, max_entries=5),
                             b"synthetic-4")

    def test_invalid_scan_limits_fail_closed(self):
        with tarfile.open(fileobj=io.BytesIO(synthetic_tar(2)), mode="r:") as arc:
            for bad in (0, -1, 1.5, True):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    am.scan_tar_headers(arc, bad)

    def test_all_tar_public_paths_use_bounded_helper(self):
        content = (ROOT / "inspectors.py").read_text(encoding="utf-8")
        self.assertEqual(content.count("archive_memory.scan_tar_headers("), 2)
        self.assertIn("MAX_MEMBER_EXTRACT, MAX_ARCHIVE_LIST", content)
        self.assertNotIn("arc.getmembers()", content)
        self.assertNotIn("arc.getmember(", content)


if __name__ == "__main__":
    unittest.main()
