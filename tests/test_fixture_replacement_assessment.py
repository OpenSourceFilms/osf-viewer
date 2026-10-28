"""Regression tests for the fail-closed, source-only fixture release register."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import runpy
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECK = runpy.run_path(
    str(ROOT / "scripts" / "verify_fixture_replacement_assessment.py"),
    run_name="fixture_review_test_import",
)["check"]


class FixtureReplacementReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="viewer_rights_")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "docs").mkdir()
        self.inventory = json.loads(
            (ROOT / "docs" / "fixture-inventory.json").read_text()
        )
        self.assessment = json.loads(
            (ROOT / "docs" / "fixture-replacement-assessment.json").read_text()
        )
        self._save()

    def _save(self):
        (self.root / "docs" / "fixture-inventory.json").write_text(
            json.dumps(self.inventory), encoding="utf-8"
        )
        (self.root / "docs" / "fixture-replacement-assessment.json").write_text(
            json.dumps(self.assessment), encoding="utf-8"
        )

    def test_real_public_register_covers_exactly_twelve_pending_blobs(self):
        self.assertEqual(CHECK(ROOT), [])
        self.assertEqual(len(self.assessment["files"]), 12)

    def test_stale_historical_blob_hash_or_size_fails(self):
        path = "tests/fixtures/sample.docx"
        self.assessment["files"][path]["historical_git_blob_sha1"] = "0" * 40
        self._save()
        self.assertIn("history_or_rights_status_mismatch:" + path, CHECK(self.root))
        self.assessment["files"][path]["historical_git_blob_sha1"] = (
            self.inventory["files"][path]["git_blob_sha1"]
        )
        self.assessment["files"][path]["historical_size_bytes"] = 1
        self._save()
        self.assertIn("history_or_rights_status_mismatch:" + path, CHECK(self.root))

    def test_cannot_silently_approve_or_assign_proposed_hash(self):
        path = "tests/fixtures/sample.pptx"
        row = self.assessment["files"][path]
        row["decision"] = "APPROVED"
        row["release_approval"] = "not independently verified"
        row["candidate_content_sha256"] = "a" * 64
        self._save()
        self.assertIn("unreviewed_release_approval_or_candidate:" + path, CHECK(self.root))

    def test_new_or_missing_fixture_fails(self):
        self.assessment["files"].pop("tests/fixtures/sample.odt")
        self._save()
        self.assertIn("assessment_does_not_cover_exactly_historical_fixtures",
                      CHECK(self.root))

    def test_misclassified_generator_and_missing_notice_fail(self):
        path = "tests/fixtures/sample.doc"
        row = self.assessment["files"][path]
        row["candidate_generation_kind"] = "mit_template"
        row["third_party_notice"] = ""
        row["required_release_evidence"] = []
        self._save()
        problems = CHECK(self.root)
        self.assertIn("candidate_lineage_mismatch:" + path, problems)
        self.assertIn("missing_file_specific_release_conditions:" + path, problems)
        self.assertIn("inadequate_evidence_or_notices:" + path, problems)

    def test_history_exposure_must_not_be_hidden(self):
        self.assessment["historical_git_history_exposure"] = "all fixed"
        self._save()
        self.assertIn("history_exposure_unacknowledged", CHECK(self.root))

    def test_original_manifest_rights_change_requires_separate_gate_update(self):
        path = "tests/fixtures/corrupt.xls"
        self.inventory["files"][path]["review_status"] = "cleared"
        self._save()
        self.assertIn("history_or_rights_status_mismatch:" + path, CHECK(self.root))

    def test_invalid_json_fails_closed(self):
        (self.root / "docs" / "fixture-replacement-assessment.json").write_text(
            "{invalid JSON", encoding="utf-8"
        )
        self.assertIn("unreadable_or_invalid_review_documents", CHECK(self.root))


if __name__ == "__main__":
    unittest.main()
