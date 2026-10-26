"""Offline, zero-dependency checks of public Office ZIP fixtures."""
from __future__ import annotations

import io
from pathlib import Path
import runpy
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
AUDIT = runpy.run_path(str(ROOT / "scripts" / "audit_fixture_packages.py"),
                       run_name="fixture_audit_import")
scan = AUDIT["scan_package"]
FIXTURES = AUDIT["FIXTURES"]
ARCHIVES = AUDIT["ARCHIVES"]


class FixturePackageSafetyTests(unittest.TestCase):
    def test_six_published_office_archives_are_inspectable(self):
        self.assertEqual(len(ARCHIVES), 6)
        results = {p: scan(FIXTURES / p) for p in ARCHIVES}
        for name, result in results.items():
            with self.subTest(file=name):
                self.assertEqual(result["issues"], [])
        # These embedded parts must be acknowledged, not silently described
        # as if the fixture containers consisted solely of visible text.
        self.assertIn("docProps/thumbnail.jpeg",
                      results["sample.docx"]["embedded_preview"])
        self.assertIn("docProps/thumbnail.jpeg",
                      results["sample.pptx"]["embedded_preview"])
        self.assertGreaterEqual(
            len(results["sample.pptx"]["printer_settings"]), 1)

    def test_rejects_external_relationship(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "external.docx"
            xml = (b'<Relationships xmlns="http://schemas.openxmlformats.org/'
                   b'package/2006/relationships"><Relationship '
                   b'Id="rId1" TargetMode="External" '
                   b'Target="https://example.net/tracker" '
                   b'Type="http://example.net/type"/></Relationships>')
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("word/_rels/document.xml.rels", xml)
            self.assertIn("external_relationship", scan(path)["issues"])

    def test_rejects_odf_external_xlink_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            for reference in ("https://example.test/track.png", "file:///etc/passwd",
                              "//example.test/image", "../outside.png"):
                with self.subTest(reference=reference):
                    path = Path(tmp) / "external.odt"
                    content = (f'<root xmlns:xlink="http://www.w3.org/1999/xlink">'
                               f'<image xlink:href="{reference}"/></root>').encode("utf-8")
                    with zipfile.ZipFile(path, "w") as z:
                        z.writestr("content.xml", content)
                    self.assertIn("external_odf_reference", scan(path)["issues"])

    def test_odf_package_local_xlink_reference_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "local.odt"
            content = ('<root xmlns:xlink="http://www.w3.org/1999/xlink">'
                       '<image xlink:href="Pictures/local.png"/>'
                       '<image xlink:href="#local"/>'
                       '</root>')
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("content.xml", content)
            self.assertEqual(scan(path)["issues"], [])

    def test_rejects_xml_decoded_email_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "encoded.odt"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("meta.xml", '<meta><creator>alice&#64;gmail.com</creator></meta>')
            self.assertIn("personal_email_metadata", scan(path)["issues"])

    def test_adjacent_metadata_elements_preserve_email_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "adjacent.odt"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("meta.xml", "<meta><creator>alice@gmail.com</creator>"
                                       "<date>2026-10-26</date></meta>")
            self.assertIn("personal_email_metadata", scan(path)["issues"])

    def test_rejects_utf16_encoded_email_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "utf16.odt"
            xml = ('<?xml version="1.0" encoding="UTF-16"?>'
                   '<meta><creator>alice@gmail.com</creator></meta>').encode("utf-16")
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("meta.xml", xml)
            self.assertIn("personal_email_metadata", scan(path)["issues"])

    def test_rejects_package_member_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "escape.docx"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("../outside.xml", "do not extract this")
            self.assertIn("unsafe_member_path", scan(path)["issues"])

    def test_rejects_macro_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "macro.docx"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("word/vbaProject.bin", b"not executable")
            self.assertIn("embedded_executable_or_attachment", scan(path)["issues"])


if __name__ == "__main__":
    unittest.main()
