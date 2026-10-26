"""Run the public fixture byte/provenance gate with only Python stdlib."""
from __future__ import annotations

import json
from pathlib import Path
import runpy
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
VERIFY = runpy.run_path(str(ROOT / "scripts" / "verify_fixture_manifest.py"),
                        run_name="fixture_manifest_import")
verify = VERIFY["verify"]
git_blob_id = VERIFY["git_blob_id"]
PENDING = VERIFY["PENDING"]


class FixtureInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="viewer_fixture_gate_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "docs").mkdir()
        (self.root / "tests" / "fixtures").mkdir(parents=True)
        self.path = self.root / "tests" / "fixtures" / "sample.txt"
        self.path.write_bytes(b"invented, disposable, synthetic test bytes")
        self.spec = {
            "git_blob_sha1": git_blob_id(self.path.read_bytes()),
            "size_bytes": self.path.stat().st_size,
            "kind": "legacy_binary_or_rtf",
            "review_status": PENDING,
            "flags": [],
        }
        self.manifest = {"schema_version": 1,
                         "files": {"tests/fixtures/sample.txt": self.spec}}
        self.write_manifest()

    def write_manifest(self):
        (self.root / "docs" / "fixture-inventory.json").write_text(
            json.dumps(self.manifest), encoding="utf-8"
        )

    def test_checked_in_inventory_matches_all_real_fixtures(self):
        self.assertEqual(verify(ROOT), [])
        inventory = json.loads((ROOT / "docs" / "fixture-inventory.json").read_text())
        self.assertEqual(len(inventory["files"]), 12)
        self.assertTrue(all(row["review_status"] == PENDING
                            for row in inventory["files"].values()))
        self.assertIn("embedded_thumbnail_rights_unresolved",
                      inventory["files"]["tests/fixtures/sample.docx"]["flags"])
        self.assertIn("embedded_thumbnail_rights_unresolved",
                      inventory["files"]["tests/fixtures/sample.pptx"]["flags"])

    def test_clean_temp_inventory_passes(self):
        self.assertEqual(verify(self.root), [])

    def test_altered_bytes_fail(self):
        self.path.write_bytes(b"changed")
        self.assertIn("fixture_bytes_changed:tests/fixtures/sample.txt",
                      verify(self.root))

    def test_unlisted_binary_fails(self):
        (self.path.parent / "new.pptx").write_bytes(b"new binary")
        self.assertIn("unreviewed_fixture:tests/fixtures/new.pptx",
                      verify(self.root))

    def test_removed_fixture_fails(self):
        self.path.unlink()
        self.assertIn("listed_fixture_not_present:tests/fixtures/sample.txt",
                      verify(self.root))

    def test_symlink_fixture_fails(self):
        self.path.unlink()
        self.path.symlink_to(self.root / "docs" / "fixture-inventory.json")
        findings = verify(self.root)
        self.assertIn("symlink_fixture:tests/fixtures/sample.txt", findings)

    def test_unrecognised_permission_status_fails(self):
        self.spec["review_status"] = "cleared_for_reuse"
        self.write_manifest()
        self.assertIn("invalid_or_unapproved_rights_status:tests/fixtures/sample.txt",
                      verify(self.root))

    def test_manifest_traversal_fails(self):
        self.manifest["files"]["tests/fixtures/../../oops.txt"] = self.spec.copy()
        self.write_manifest()
        self.assertIn("unsafe_manifest_path:tests/fixtures/../../oops.txt",
                      verify(self.root))

    def test_wrong_size_or_blob_id_fails(self):
        self.spec["size_bytes"] = 3
        self.write_manifest()
        self.assertIn("fixture_bytes_changed:tests/fixtures/sample.txt",
                      verify(self.root))
        self.spec["size_bytes"] = self.path.stat().st_size
        self.spec["git_blob_sha1"] = "f" * 40
        self.write_manifest()
        self.assertIn("fixture_bytes_changed:tests/fixtures/sample.txt",
                      verify(self.root))


if __name__ == "__main__":
    unittest.main()
