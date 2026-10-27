"""Pure-stdlib safety regressions for replacement Office fixture generation.

Does not read/modify the 12 published binary fixtures, download dependencies,
run LibreOffice, or write to a deployed Viewer.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_clean_office_candidates.py"
GEN = runpy.run_path(str(SCRIPT), run_name="clean_fixture_test_import")

sanitize = GEN["sanitize_generated_package"]
verify_clean = GEN["assert_clean_packages"]


class GeneratedFixtureSafetyTests(unittest.TestCase):
    def test_strips_template_parts_and_updates_relationships(self):
        with tempfile.TemporaryDirectory(prefix="osf_clean_office_") as tmp:
            file = Path(tmp) / "sample.docx"
            rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
            content_ns = "http://schemas.openxmlformats.org/package/2006/content-types"
            relationships = ET.Element(f"{{{rel_ns}}}Relationships")
            for rid, target in [
                ("rId1", "word/document.xml"),
                ("rId2", "docProps/thumbnail.jpeg"),
                ("rId3", "customXml/item1.xml"),
            ]:
                ET.SubElement(
                    relationships, f"{{{rel_ns}}}Relationship",
                    Id=rid, Target=target, Type="test",
                )
            types = ET.Element(f"{{{content_ns}}}Types")
            for part in [
                "/word/document.xml", "/docProps/thumbnail.jpeg",
                "/customXml/item1.xml",
            ]:
                ET.SubElement(
                    types, f"{{{content_ns}}}Override",
                    PartName=part, ContentType="test",
                )
            with zipfile.ZipFile(file, "w") as dst:
                dst.writestr("_rels/.rels", ET.tostring(relationships))
                dst.writestr("[Content_Types].xml", ET.tostring(types))
                dst.writestr("word/document.xml", "<text>keep me</text>")
                dst.writestr("docProps/thumbnail.jpeg", b"fake thumbnail")
                dst.writestr("customXml/item1.xml", "<private/>")
                dst.writestr("ppt/printerSettings/printer1.bin", b"unneeded")
            sanitize(file)
            with zipfile.ZipFile(file) as archive:
                names = set(archive.namelist())
                self.assertEqual(
                    names,
                    {"_rels/.rels", "[Content_Types].xml", "word/document.xml"},
                )
                self.assertEqual(
                    archive.read("word/document.xml"), b"<text>keep me</text>"
                )
                surviving_rels = ET.fromstring(archive.read("_rels/.rels"))
                self.assertEqual(
                    [x.get("Target") for x in surviving_rels],
                    ["word/document.xml"],
                )
                surviving_types = ET.fromstring(
                    archive.read("[Content_Types].xml")
                )
                self.assertEqual(
                    [x.get("PartName") for x in surviving_types],
                    ["/word/document.xml"],
                )
            self.assertFalse(file.with_name(file.name + ".sanitizing").exists())

    def test_rejects_external_ooxml_relationships(self):
        with tempfile.TemporaryDirectory(prefix="osf_clean_office_") as tmp:
            out = Path(tmp)
            for name in [
                "sample.docx", "sample.xlsx", "sample.pptx",
                "sample.odt", "sample.ods", "sample.odp",
            ]:
                with zipfile.ZipFile(out / name, "w") as dst:
                    dst.writestr("content.xml", "<root/>")
                    if name == "sample.docx":
                        dst.writestr(
                            "_rels/.rels",
                            '<Relationships><Relationship TargetMode="External"'
                            ' Target="https://example.invalid/tracker"/></Relationships>',
                        )
            with self.assertRaisesRegex(RuntimeError, "External relationship"):
                verify_clean(out)

    def test_refuses_existing_destination_before_loading_dependencies(self):
        with tempfile.TemporaryDirectory(prefix="osf_clean_office_") as tmp:
            out = Path(tmp)
            sentinel = out / "existing.txt"
            sentinel.write_text("unchanged")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--out", str(out)],
                capture_output=True, text=True, timeout=10, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("output must be a new directory", result.stderr)
            self.assertEqual(sentinel.read_text(), "unchanged")

    @unittest.skipUnless(
        all(importlib.util.find_spec(name) is not None
            for name in ("docx", "openpyxl", "pptx", "odf")),
        "Office authoring libraries not installed in stdlib-only CI",
    )
    def test_disposable_modern_documents_have_required_semantics(self):
        with tempfile.TemporaryDirectory(prefix="osf_clean_office_") as tmp:
            out = Path(tmp)
            GEN["create_modern"](out)
            verify_clean(out)
            for filename, member, required in [
                ("sample.docx", "word/document.xml",
                 ["Main Title", "Section One", "alpha", "café"]),
                ("sample.xlsx", "xl/worksheets/sheet1.xml",
                 ["alpha", "9.5"]),
                ("sample.pptx", "ppt/slides/slide1.xml",
                 ["Slide 1 Title", "café"]),
                ("sample.odt", "content.xml",
                 ["ODT Fixture Heading", "café"]),
                ("sample.ods", "content.xml",
                 ["Sheet1", "café"]),
                ("sample.odp", "content.xml",
                 ["slide 1 text cafe", "slide 2 text cafe"]),
            ]:
                with self.subTest(filename=filename):
                    with zipfile.ZipFile(out / filename) as archive:
                        text = archive.read(member).decode("utf-8")
                    for token in required:
                        self.assertIn(token, text)


if __name__ == "__main__":
    unittest.main()
