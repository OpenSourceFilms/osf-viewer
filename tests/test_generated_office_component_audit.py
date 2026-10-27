"""Regression for generated Office package provenance/attachment inventory.

Synthetic temporary ZIPs only; never changes published Office fixtures.
"""
from __future__ import annotations

from pathlib import Path
import runpy
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCAN = runpy.run_path(
    str(ROOT / "scripts" / "audit_generated_office_components.py"),
    run_name="office_audit_import",
)
inspect = SCAN["inspect_package"]
audit = SCAN["audit_directory"]
NAMES = SCAN["NAMES"]


def create_package(path: Path, parts: dict[str, str | bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in parts.items():
            archive.writestr(name, content)


class GeneratedOfficeComponentAuditTests(unittest.TestCase):
    def test_expected_six_synthetic_packages_and_theme_inventory(self):
        with tempfile.TemporaryDirectory(prefix="osf_office_parts_") as root:
            folder = Path(root)
            for name in NAMES:
                create_package(folder / name, {"content.xml": "<root/>"})
            create_package(folder / "sample.docx", {
                "word/document.xml": "<root/>",
                "word/styles.xml": "<root/>",
                "word/theme/theme1.xml": "<root/>",
                "docProps/core.xml": "<root/>",
            })
            result = audit(folder)
            self.assertTrue(result["safe_from_unreviewed_binary_components"])
            self.assertEqual(len(result["packages"]), 6)
            docx = result["packages"][0]
            self.assertEqual(docx["parts_count"], 4)
            self.assertEqual(
                docx["template_and_formatting_parts"],
                ["word/styles.xml", "word/theme/theme1.xml"],
            )
            self.assertEqual(docx["findings"], [])

    def test_rejects_unreviewed_media_and_binary_payload(self):
        with tempfile.TemporaryDirectory(prefix="osf_office_parts_") as root:
            path = Path(root) / "sample.pptx"
            create_package(path, {
                "ppt/slides/slide1.xml": "<root/>",
                "ppt/media/image1.png": b"fake image bytes",
                "ppt/embeddings/oleObject1.bin": b"fake macro bytes",
            })
            errors = inspect(path)["findings"]
            self.assertIn("embedded_or_unreviewed_part:ppt/media/image1.png", errors)
            self.assertIn("embedded_or_unreviewed_part:ppt/embeddings/oleObject1.bin", errors)

    def test_rejects_external_relationship(self):
        with tempfile.TemporaryDirectory(prefix="osf_office_parts_") as root:
            path = Path(root) / "sample.docx"
            create_package(path, {
                "_rels/.rels":
                '<Relationships><Relationship TargetMode="External" '
                'Target="https://example.invalid/"/></Relationships>',
            })
            self.assertIn(
                "external_relationship:_rels/.rels",
                inspect(path)["findings"],
            )

    def test_rejects_private_metadata(self):
        with tempfile.TemporaryDirectory(prefix="osf_office_parts_") as root:
            path = Path(root) / "sample.odt"
            create_package(path, {
                "meta.xml": "<meta><creator>alice@gmail.com</creator></meta>",
            })
            self.assertIn("private_metadata:meta.xml", inspect(path)["findings"])

    def test_missing_package_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="osf_office_parts_") as root:
            result = audit(Path(root))
            self.assertFalse(result["safe_from_unreviewed_binary_components"])
            self.assertTrue(all(
                "unreadable_package" in row["findings"]
                for row in result["packages"]
            ))


if __name__ == "__main__":
    unittest.main()
