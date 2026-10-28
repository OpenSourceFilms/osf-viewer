"""Offline tests for exact-file generated Office provenance records."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import runpy
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
S = runpy.run_path(
    str(ROOT / "scripts" / "record_generated_office_evidence.py"),
    run_name="office_evidence_test_import",
)
make_record = S["make_record"]
publish_record = S["publish_record"]
EXPECTED = S["EXPECTED"]
VERSIONS = {
    "python-docx": "1.2.0",
    "python-pptx": "1.0.2",
    "openpyxl": "3.1.5",
    "odfpy": "1.4.1",
    "olefile": "0.47",
    "libreoffice": "LibreOffice 24.2.7.2",
    "python": "3.12.15",
}
ZIPS = {"sample.docx", "sample.xlsx", "sample.pptx",
        "sample.odt", "sample.ods", "sample.odp"}
LEGACY = {"sample.doc", "sample.xls", "sample.ppt", "sample.rtf"}


class CandidateEvidenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="viewer_evidence_")
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name) / "generated"
        self.folder.mkdir()
        for name in EXPECTED:
            (self.folder / name).write_bytes(("generated:" + name).encode())
        self.zip_audit = {
            "safe_from_unreviewed_binary_components": True,
            "packages": [{"file": name, "findings": []} for name in sorted(ZIPS)],
        }
        self.legacy_audit = {
            "pass_structural_checks": True,
            "results": [
                {
                    "file": name, "findings": [],
                    "sha256": hashlib.sha256(
                        (self.folder / name).read_bytes()
                    ).hexdigest(),
                }
                for name in sorted(LEGACY)
            ],
        }

    def make(self):
        return make_record(
            self.folder, tool_versions=VERSIONS,
            package_report=self.zip_audit,
            legacy_report=self.legacy_audit,
            checkout_sha="d" * 40,
        )

    def test_records_all_twelve_hashes_and_versions_without_clearance(self):
        record = self.make()
        self.assertEqual(record["candidate_count"], 12)
        self.assertEqual(
            {row["filename"] for row in record["candidates"]}, set(EXPECTED)
        )
        for row in record["candidates"]:
            expected = (self.folder / row["filename"]).read_bytes()
            self.assertEqual(row["sha256"], hashlib.sha256(expected).hexdigest())
            self.assertEqual(row["bytes"], len(expected))
            self.assertEqual(row["redistribution_rights"], "not_asserted")
        self.assertFalse(record["copyright_and_redistribution_cleared"])
        self.assertFalse(record["original_published_fixture_bytes_replaced"])
        self.assertEqual(record["dependencies"]["openpyxl"], "3.1.5")
        self.assertEqual(record["checkout_git_sha"], "d" * 40)

    def test_rejects_extra_missing_and_symlinked_files(self):
        (self.folder / "extra.txt").write_text("unexpected")
        with self.assertRaises(ValueError):
            self.make()
        (self.folder / "extra.txt").unlink()
        (self.folder / "sample.doc").unlink()
        with self.assertRaises(ValueError):
            self.make()
        (self.folder / "sample.doc").symlink_to(self.folder / "sample.xls")
        with self.assertRaises(ValueError):
            self.make()

    def test_refuses_failed_or_incomplete_component_evidence(self):
        self.zip_audit["safe_from_unreviewed_binary_components"] = False
        with self.assertRaises(ValueError):
            self.make()
        self.zip_audit["safe_from_unreviewed_binary_components"] = True
        self.legacy_audit["results"][0]["findings"] = ["embedded_or_macro"]
        with self.assertRaises(ValueError):
            self.make()
        self.legacy_audit["results"][0]["findings"] = []
        self.legacy_audit["results"].pop()
        with self.assertRaises(ValueError):
            self.make()

    def test_fails_for_missing_tool_version_or_changed_legacy_hash(self):
        self.legacy_audit["results"][0]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.make()
        self.legacy_audit["results"][0]["sha256"] = hashlib.sha256(
            (self.folder / self.legacy_audit["results"][0]["file"]).read_bytes()
        ).hexdigest()
        old = VERSIONS.pop("odfpy")
        try:
            with self.assertRaises(ValueError):
                self.make()
        finally:
            VERSIONS["odfpy"] = old

    def test_publication_writes_once_outside_repository(self):
        data = self.make()
        dest = self.folder.parent / "evidence.json"
        publish_record(dest, data, repo_root=ROOT)
        self.assertEqual(json.loads(dest.read_text())["candidate_count"], 12)
        with self.assertRaises(FileExistsError):
            publish_record(dest, data, repo_root=ROOT)
        with self.assertRaises(ValueError):
            publish_record(
                ROOT / "evidence.json", data, repo_root=ROOT
            )

    def test_rejects_symlink_evidence_target(self):
        data = self.make()
        dest = self.folder.parent / "evidence.json"
        dest.symlink_to(self.folder.parent / "elsewhere.json")
        with self.assertRaises((ValueError, FileExistsError)):
            publish_record(dest, data, repo_root=ROOT)
        self.assertFalse((self.folder.parent / "elsewhere.json").exists())


if __name__ == "__main__":
    unittest.main()
