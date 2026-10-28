#!/usr/bin/env python3
"""Fail-closed cross-check of Viewer fixture replacement decisions and history.

No files are modified. A green check means that the current 12 historically
unverified blobs are correctly mapped and blocked, NOT copyright clearance.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parents[1]
INVENTORY = Path("docs/fixture-inventory.json")
DECISIONS = Path("docs/fixture-replacement-assessment.json")
KINDS = {
    "synthetic_invalid": {"corrupt.docx", "corrupt.xls"},
    "mit_template": {"sample.docx", "sample.pptx"},
    "mit_writer": {"sample.xlsx"},
    "odf_apache_route": {"sample.odt", "sample.ods", "sample.odp"},
    "libreoffice_legacy": {"sample.doc", "sample.xls", "sample.ppt", "sample.rtf"},
}
PENDING = "provenance_and_redistribution_rights_unverified"
SHA1 = re.compile(r"^[a-f0-9]{40}$")


def check(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        root = Path(root)
        a = json.loads((root / INVENTORY).read_text(encoding="utf-8"))
        b = json.loads((root / DECISIONS).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError, TypeError):
        return ["unreadable_or_invalid_review_documents"]
    if a.get("schema_version") != 1 or b.get("schema_version") != 1:
        return ["unexpected_assessment_schema"]
    original, proposed = a.get("files"), b.get("files")
    if not isinstance(original, dict) or not isinstance(proposed, dict):
        return ["missing_file_records"]
    if len(original) != 12 or set(original) != set(proposed):
        errors.append("assessment_does_not_cover_exactly_historical_fixtures")
    if b.get("historical_manifest") != INVENTORY.as_posix():
        errors.append("manifest_reference_changed")
    if b.get("historical_bytes_preserved") is not True:
        errors.append("history_preservation_statement_missing")
    history = b.get("historical_git_history_exposure", "")
    if not isinstance(history, str) or "does not retract" not in history:
        errors.append("history_exposure_unacknowledged")
    gates = b.get("global_release_gates")
    if not isinstance(gates, list) or len(gates) < 5 or any(
        not isinstance(g, str) or len(g.strip()) < 40 for g in gates
    ):
        errors.append("insufficient_global_release_gates")
    notice = b.get("candidate_provenance_artifact")
    if notice != "viewer-office-evidence":
        errors.append("candidate_evidence_artifact_mismatch")
    if b.get("rights_issue") != (
        "https://github.com/OpenSourceFilms/osf-viewer/issues/1"
    ):
        errors.append("unexpected_rights_issue")
    for path in sorted(set(original) & set(proposed)):
        old, new = original[path], proposed[path]
        if not isinstance(old, dict) or not isinstance(new, dict):
            errors.append("invalid_review_record:" + path)
            continue
        if (new.get("historical_git_blob_sha1") != old.get("git_blob_sha1")
                or not isinstance(old.get("git_blob_sha1"), str)
                or not SHA1.fullmatch(old["git_blob_sha1"])
                or new.get("historical_size_bytes") != old.get("size_bytes")
                or new.get("historical_kind") != old.get("kind")
                or new.get("historical_flags") != old.get("flags")
                or old.get("review_status") != PENDING
                or new.get("historical_rights_status") != PENDING):
            errors.append("history_or_rights_status_mismatch:" + path)
        name = path.removeprefix("tests/fixtures/")
        kind = new.get("candidate_generation_kind")
        if (new.get("candidate_filename") != name or kind not in KINDS
                or name not in KINDS[kind]):
            errors.append("candidate_lineage_mismatch:" + path)
        if (new.get("decision") != "NOT_APPROVED"
                or new.get("release_approval") is not None
                or new.get("candidate_content_sha256") is not None):
            errors.append("unreviewed_release_approval_or_candidate:" + path)
        requirements = new.get("required_release_evidence")
        if (not isinstance(requirements, list) or len(requirements) < 3
                or any(not isinstance(v, str) or not v.strip()
                       for v in requirements)):
            errors.append("missing_file_specific_release_conditions:" + path)
        if (new.get("third_party_notice")
                != "docs/GENERATED_OFFICE_NOTICES.md"
                or not isinstance(new.get("technical_evidence"), str)
                or not new["technical_evidence"].startswith(
                    "https://github.com/OpenSourceFilms/osf-viewer/actions/runs/"
                )):
            errors.append("inadequate_evidence_or_notices:" + path)
        if not isinstance(new.get("candidate_source"), str) or not new["candidate_source"]:
            errors.append("missing_candidate_source:" + path)
    return sorted(set(errors))


def main() -> int:
    problems = check(HERE)
    if problems:
        for problem in problems:
            print("FIXTURE RELEASE REVIEW REQUIRED: " + problem, file=sys.stderr)
        return 1
    print("PASS: 12 source-matched fixture replacement assessments remain NOT_APPROVED.")
    print("Git-history exposure and independent exact-byte release review are retained.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
