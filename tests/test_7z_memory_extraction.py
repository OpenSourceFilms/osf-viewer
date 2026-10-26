"""Tests real py7zr 1.1.4 WriterFactory extraction, no GPU or live service.

Archives are constructed in memory from synthetic bytes; no archive member
is written to the filesystem. Fake decoders additionally exercise fail-closed
malicious metadata and output byte count conditions.
"""
from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
import unittest

import py7zr

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import archive_memory as am  # noqa: E402


def synthetic_7z(members: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with py7zr.SevenZipFile(output, mode="w") as archive:
        for name, content in members.items():
            archive.writestr(content, name)
    return output.getvalue()


class FakeArchive:
    def __init__(self, name, reported_size, output=None):
        self.name = name
        self.reported_size = reported_size
        self.output = output
        self.extracted = False

    def list(self):
        return [SimpleNamespace(filename=self.name, uncompressed=self.reported_size,
                                is_directory=False)]

    def extract(self, *, targets, recursive, factory):
        self.extracted = True
        writer = factory.create(self.name)
        writer.write(self.output or b"")


class SevenZipMemoryTests(unittest.TestCase):
    def test_real_single_file_archive_decodes_without_filesystem_extraction(self):
        payload = b"Hello from an invented 7z file"
        data = synthetic_7z({"hello.txt": payload})
        with py7zr.SevenZipFile(io.BytesIO(data), mode="r") as archive:
            self.assertEqual(am.read_7z_member(archive, "hello.txt", 1024), payload)

    def test_real_nested_member_archive_decodes(self):
        payload = b"Nested member containing invented text"
        data = synthetic_7z({"a/b/hello.txt": payload})
        with py7zr.SevenZipFile(io.BytesIO(data), mode="r") as archive:
            self.assertEqual(am.read_7z_member(archive, "a/b/hello.txt", 1024), payload)

    def test_real_7z_small_limit_fails_without_streaming(self):
        data = synthetic_7z({"hello.txt": b"a" * 128})
        with py7zr.SevenZipFile(io.BytesIO(data), mode="r") as archive:
            with self.assertRaises(ValueError):
                am.read_7z_member(archive, "hello.txt", 127)

    def test_path_like_malicious_names_are_rejected_before_decoder(self):
        names = [
            "", "../escape", "good/../escape", "/etc/passwd",
            "C:/windows/file", "a\\b", "a//b", "a/./b", "a/b/",
            "newline\nname", "nul\x00member", ".",
        ]
        for name in names:
            with self.subTest(name=name):
                decoder = FakeArchive(name, 4, b"good")
                with self.assertRaises(ValueError):
                    am.read_7z_member(decoder, name, 50)
                self.assertFalse(decoder.extracted)

    def test_reported_oversize_or_unknown_fails_before_decoder(self):
        for size in (None, -1, 51, "10"):
            with self.subTest(size=size):
                archive = FakeArchive("file.txt", size, b"good")
                with self.assertRaises(ValueError):
                    am.read_7z_member(archive, "file.txt", 50)
                self.assertFalse(archive.extracted)

    def test_actual_output_bytes_must_match_metadata(self):
        for declared, output in ((2, b"aaa"), (20, b"abc")):
            with self.subTest(declared=declared):
                archive = FakeArchive("file.txt", declared, output)
                with self.assertRaises(ValueError):
                    am.read_7z_member(archive, "file.txt", 30)

    def test_bounded_sink_rejects_overflow_even_with_false_small_metadata(self):
        archive = FakeArchive("file.txt", 1, b"x" * 9)
        with self.assertRaises(ValueError):
            am.read_7z_member(archive, "file.txt", 8)
        self.assertTrue(archive.extracted)

    def test_factory_refuses_other_member_streams(self):
        factory = am._SingleMemberFactory("only.txt", 100)
        with self.assertRaises(ValueError):
            factory.create("other.txt")
        product = factory.create("only.txt")
        with self.assertRaises(ValueError):
            factory.create("only.txt")
        self.assertEqual(product.write(b"abc"), 3)
        self.assertEqual(product.size(), 3)
        product.seek(0)
        self.assertEqual(product.read(), b"abc")
        with self.assertRaises(ValueError):
            product.seek(101)

    def test_no_symlink_or_7z_temporary_extraction_code_in_inspectors(self):
        source = (ROOT / "inspectors.py").read_text(encoding="utf-8")
        self.assertIn("archive_memory.read_7z_member", source)
        self.assertNotIn("arc.extract(path=td", source)
        self.assertNotIn("arc.extractall(", source)
        self.assertNotIn("arc.extract(path=", source)


if __name__ == "__main__":
    unittest.main()
