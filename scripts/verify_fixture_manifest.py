#!/usr/bin/env python3
"""Verify the exact committed Office fixture inventory, without opening packages.

The SHA-1 values are Git *blob object IDs*: SHA1("blob {length}\0" + bytes),
not ordinary SHA1(file bytes). This only detects mismatches against reviewed
Git objects; it is NOT a statement of copyright, provenance, security or
commercial reuse rights.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_REL = "tests/fixtures"
MANIFEST_REL = "docs/fixture-inventory.json"
PENDING = "provenance_and_redistribution_rights_unverified"
KINDS = {"zip_office_package", "intentionally_corrupt", "legacy_binary_or_rtf"}


def git_blob_id(raw: bytes) -> str:
    header = b"blob " + str(len(raw)).encode("ascii") + b"\0"
    return hashlib.sha1(header + raw).hexdigest()  # noqa: S324 - Git object format


def verify(root: Path) -> list[str]:
    """Return findings; an empty list means the manifest and bytes agree."""
    issues: list[str] = []
    path = root / MANIFEST_REL
    if path.is_symlink() or not path.is_file():
        return ["missing_or_symlinked_fixture_manifest"]
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return ["invalid_fixture_manifest"]
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        return ["unexpected_manifest_schema"]
    expected = manifest.get("files")
    if not isinstance(expected, dict) or not expected:
        return ["missing_manifest_files"]

    fixture_dir = root / FIXTURES_REL
    if fixture_dir.is_symlink() or not fixture_dir.is_dir():
        return ["missing_or_symlinked_fixture_directory"]
    actual: set[str] = set()
    for file in fixture_dir.rglob("*"):
        rel = file.relative_to(root).as_posix()
        if file.is_symlink():
            issues.append("symlink_fixture:" + rel)
        elif file.is_file():
            actual.add(rel)
        elif not file.is_dir():
            issues.append("unsupported_fixture_entry:" + rel)

    for rel in sorted(set(expected) | actual):
        spec = expected.get(rel)
        parts = PurePosixPath(rel)
        if (not rel.startswith(FIXTURES_REL + "/")
                or parts.is_absolute() or any(p in (".", "..") for p in parts.parts)
                or "\\" in rel):
            issues.append("unsafe_manifest_path:" + rel)
            continue
        if rel not in actual:
            issues.append("listed_fixture_not_present:" + rel)
            continue
        if rel not in expected:
            issues.append("unreviewed_fixture:" + rel)
            continue
        if not isinstance(spec, dict):
            issues.append("invalid_fixture_record:" + rel)
            continue
        if (spec.get("review_status") != PENDING
                or spec.get("kind") not in KINDS
                or not isinstance(spec.get("flags"), list)
                or any(not isinstance(flag, str) for flag in spec["flags"])):
            issues.append("invalid_or_unapproved_rights_status:" + rel)
            continue
        blob = spec.get("git_blob_sha1")
        if not isinstance(blob, str) or len(blob) != 40 or any(c not in "0123456789abcdef" for c in blob):
            issues.append("invalid_git_object_id:" + rel)
            continue
        if not isinstance(spec.get("size_bytes"), int) or spec["size_bytes"] < 0:
            issues.append("invalid_recorded_file_size:" + rel)
            continue
        file = root / rel
        if file.is_symlink():
            continue
        raw = file.read_bytes()
        if len(raw) != spec["size_bytes"] or git_blob_id(raw) != blob:
            issues.append("fixture_bytes_changed:" + rel)
    return sorted(set(issues))


def main() -> int:
    problems = verify(ROOT)
    if problems:
        for problem in problems:
            print("FIXTURE REVIEW REQUIRED: " + problem, file=sys.stderr)
        return 1
    print("PASS: all 12 published fixture binaries match the rights-pending inventory.")
    print("No provenance, third-party asset or redistribution rights clearance is implied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
