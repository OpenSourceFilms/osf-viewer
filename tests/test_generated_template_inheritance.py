"""Offline regressions for installed Office template byte-inheritance audit."""
from __future__ import annotations

import hashlib
from pathlib import Path
import runpy
import tempfile
import unittest
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CODE = runpy.run_path(
    str(ROOT / "scripts" / "audit_generated_template_inheritance.py"),
    run_name="office_template_audit_import",
)
inspect_pair = CODE["inspect_pair"]
audit = CODE["audit"]


def zip_parts(path: Path, parts: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in parts.items():
            archive.writestr(name, content)


class TemplateInheritanceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="osf_inheritance_")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.generated = self.base / "generated"
        self.generated.mkdir()

    def test_distinguishes_exact_modified_added_and_removed_parts(self):
        source = self.base / "default.docx"
        target = self.generated / "sample.docx"
        zip_parts(source, {
            "word/theme/theme1.xml": b"upstream theme",
            "word/styles.xml": b"upstream styles",
            "word/removed.xml": b"upstream only",
        })
        zip_parts(target, {
            "word/theme/theme1.xml": b"upstream theme",
            "word/styles.xml": b"changed styles",
            "word/new.xml": b"new content",
        })
        result = inspect_pair(
            source, target, candidate_name="sample.docx",
            source_dependency="python-docx", source_template="templates/default.docx",
        )
        self.assertEqual(result["same_named_part_count"], 2)
        self.assertEqual(result["byte_identical_part_count"], 1)
        self.assertEqual(result["modified_same_named_parts"], ["word/styles.xml"])
        self.assertEqual(result["generated_only_parts"], ["word/new.xml"])
        self.assertEqual(result["source_only_parts"], ["word/removed.xml"])
        self.assertEqual(result["byte_identical_parts"][0]["part"], "word/theme/theme1.xml")
        self.assertEqual(
            result["byte_identical_parts"][0]["sha256"],
            hashlib.sha256(b"upstream theme").hexdigest(),
        )
        self.assertFalse(result["inherited_template_rights_cleared"])
        self.assertNotIn("upstream theme", str(result))

    def test_audit_both_packages_and_never_claim_rights_clearance(self):
        paths = {}
        for ext in ("docx", "pptx"):
            template = self.base / f"default.{ext}"
            candidate = self.generated / f"sample.{ext}"
            zip_parts(template, {"theme.xml": f"{ext}-theme".encode()})
            zip_parts(candidate, {"theme.xml": f"{ext}-theme".encode()})
            paths[f"sample.{ext}"] = template
        report = audit(self.generated, template_paths=paths)
        self.assertEqual(
            {p["candidate"] for p in report["candidates"]},
            {"sample.docx", "sample.pptx"},
        )
        self.assertTrue(all(p["byte_identical_part_count"] == 1
                            for p in report["candidates"]))
        self.assertFalse(report["template_content_copyright_cleared"])

    def test_duplicate_archive_member_fails_closed(self):
        source = self.base / "default.docx"
        target = self.generated / "sample.docx"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(source, "w") as z:
                z.writestr("word/styles.xml", b"first")
                z.writestr("word/styles.xml", b"second")
        zip_parts(target, {"word/styles.xml": b"first"})
        with self.assertRaisesRegex(ValueError, "Unsafe or duplicate"):
            inspect_pair(
                source, target, candidate_name="sample.docx",
                source_dependency="python-docx", source_template="templates/default.docx",
            )

    def test_unsafe_member_path_and_missing_package_fail_closed(self):
        source = self.base / "default.pptx"
        target = self.generated / "sample.pptx"
        zip_parts(source, {"../outside.xml": b"payload"})
        zip_parts(target, {"ppt/theme.xml": b"safe"})
        with self.assertRaisesRegex(ValueError, "Unsafe or duplicate"):
            inspect_pair(
                source, target, candidate_name="sample.pptx",
                source_dependency="python-pptx", source_template="templates/default.pptx",
            )
        source.unlink()
        with self.assertRaises(ValueError):
            inspect_pair(
                source, target, candidate_name="sample.pptx",
                source_dependency="python-pptx", source_template="templates/default.pptx",
            )

    def test_symlink_template_and_oversize_archive_rejected(self):
        target = self.generated / "sample.docx"
        source = self.base / "default.docx"
        zip_parts(target, {"content.xml": b"a"})
        source.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            inspect_pair(source, target, candidate_name="sample.docx",
                         source_dependency="python-docx",
                         source_template="templates/default.docx")
        source.unlink()
        zip_parts(source, {"content.xml": b"a" * (CODE["MAX_MEMBER_BYTES"] + 1)})
        with self.assertRaises(ValueError):
            inspect_pair(source, target, candidate_name="sample.docx",
                         source_dependency="python-docx",
                         source_template="templates/default.docx")


if __name__ == "__main__":
    unittest.main()
