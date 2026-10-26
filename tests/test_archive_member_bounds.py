"""Offline TAR/ZIP member bound tests using disposable, in-memory archives."""
from __future__ import annotations

import io
from pathlib import Path
import sys
import tarfile
import unittest
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import archive_memory as am  # noqa: E402


def make_tar():
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w") as archive:
        content = b"x" * 64
        regular = tarfile.TarInfo("nested/large.txt")
        regular.size = len(content)
        archive.addfile(regular, io.BytesIO(content))

        soft = tarfile.TarInfo("nested/alias.txt")
        soft.type = tarfile.SYMTYPE
        soft.linkname = "large.txt"
        archive.addfile(soft)

        hard = tarfile.TarInfo("nested/hard.txt")
        hard.type = tarfile.LNKTYPE
        hard.linkname = "nested/large.txt"
        archive.addfile(hard)
    return data.getvalue()


class ArchiveMemberBoundsTests(unittest.TestCase):
    def test_tar_symlink_size_bypass_reproduced_but_blocked(self):
        data = make_tar()
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as arc:
            alias = arc.getmember("nested/alias.txt")
            self.assertEqual(alias.size, 0)
            self.assertFalse(alias.isfile())
            self.assertEqual(len(arc.extractfile(alias).read()), 64)
            with self.assertRaises(ValueError):
                am.read_tar_member(arc, "nested/alias.txt", 8)

    def test_tar_hardlinks_also_blocked(self):
        with tarfile.open(fileobj=io.BytesIO(make_tar()), mode="r:") as arc:
            with self.assertRaises(ValueError):
                am.read_tar_member(arc, "nested/hard.txt", 128)

    def test_regular_tar_is_accepted_if_within_actual_bound(self):
        with tarfile.open(fileobj=io.BytesIO(make_tar()), mode="r:") as arc:
            self.assertEqual(
                am.read_tar_member(arc, "nested/large.txt", 64), b"x" * 64
            )

    def test_regular_tar_oversize_rejected(self):
        with tarfile.open(fileobj=io.BytesIO(make_tar()), mode="r:") as arc:
            with self.assertRaises(ValueError):
                am.read_tar_member(arc, "nested/large.txt", 63)

    def test_tar_with_bad_name_is_rejected(self):
        with tarfile.open(fileobj=io.BytesIO(make_tar()), mode="r:") as arc:
            for item in ("/absolute", "../relative", "nested/../large.txt"):
                with self.subTest(name=item), self.assertRaises(ValueError):
                    am.read_tar_member(arc, item, 64)

    def test_zip_regular_and_small_limit(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, mode="w") as archive:
            archive.writestr("nested/hello.txt", b"synthetic" * 8)
        with zipfile.ZipFile(io.BytesIO(data.getvalue())) as archive:
            self.assertEqual(
                am.read_zip_member(archive, "nested/hello.txt", 72),
                b"synthetic" * 8,
            )
            with self.assertRaises(ValueError):
                am.read_zip_member(archive, "nested/hello.txt", 71)

    def test_duplicate_zip_names_fail_closed(self):
        data = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(data, mode="w") as archive:
                archive.writestr("duplicate.txt", "old")
                archive.writestr("duplicate.txt", "new")
        with zipfile.ZipFile(io.BytesIO(data.getvalue())) as archive:
            with self.assertRaises(KeyError):
                am.read_zip_member(archive, "duplicate.txt", 64)

    def test_only_bounded_read_helpers_are_used_by_viewer(self):
        source = (ROOT / "inspectors.py").read_text(encoding="utf-8")
        self.assertIn("archive_memory.read_zip_member(", source)
        self.assertIn("archive_memory.read_tar_member(", source)
        self.assertIn("archive_memory.read_7z_member(", source)
        self.assertNotIn("return arc.read(member)", source)
        self.assertNotIn("return f.read()", source)


if __name__ == "__main__":
    unittest.main()
