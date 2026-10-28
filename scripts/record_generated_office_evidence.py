#!/usr/bin/env python3
"""Produce a read-only, per-run provenance record of disposable Office candidates.

This records exact candidate bytes, tool versions and earlier structural audit
results. It never copies generated binaries or promotes their rights status.
Usage: from the existing full compatibility runner after its tests pass.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys

EXPECTED = {
    "sample.doc": ("libreoffice", "sample.docx"),
    "sample.docx": ("python-docx", None),
    "sample.xls": ("libreoffice", "sample.xlsx"),
    "sample.xlsx": ("openpyxl", None),
    "sample.ppt": ("libreoffice", "sample.pptx"),
    "sample.pptx": ("python-pptx", None),
    "sample.rtf": ("libreoffice", "sample.docx"),
    "sample.odt": ("odfpy", None),
    "sample.ods": ("odfpy", None),
    "sample.odp": ("odfpy", None),
    "corrupt.docx": ("explicit_python_bytes", None),
    "corrupt.xls": ("explicit_python_bytes", None),
}
PACKAGES = ("python-docx", "python-pptx", "openpyxl", "odfpy", "olefile")
MAX_CANDIDATE_BYTES = 10 * 1024 * 1024
VERSION = re.compile(r"^[ -~]{1,150}$")


def _tool_versions() -> dict[str, str]:
    installed = {name: importlib.metadata.version(name) for name in PACKAGES}
    proc = subprocess.run(
        ["libreoffice", "--version"], check=True, capture_output=True,
        text=True, timeout=15,
    )
    version = proc.stdout.strip()
    if not VERSION.fullmatch(version) or not version.lower().startswith("libreoffice"):
        raise ValueError("Unexpected LibreOffice version response")
    installed["libreoffice"] = version
    installed["python"] = ".".join(map(str, sys.version_info[:3]))
    return dict(sorted(installed.items()))


def make_record(folder: Path, *, tool_versions: dict[str, str],
                package_report: dict, legacy_report: dict,
                checkout_sha: str | None = None) -> dict:
    """Fail closed if the exact candidate set or its audit gates differ."""
    folder = Path(folder)
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("Candidate directory missing or symlinked")
    actual = {p.name for p in folder.iterdir()}
    if actual != EXPECTED.keys():
        raise ValueError("Expected exactly 12 candidate files")
    if not package_report.get("safe_from_unreviewed_binary_components"):
        raise ValueError("ZIP package component audit has not passed")
    if not legacy_report.get("pass_structural_checks"):
        raise ValueError("OLE2/RTF audit has not passed")
    package_rows = package_report.get("packages", [])
    legacy_rows = legacy_report.get("results", [])
    if (len(package_rows) != 6 or {x.get("file") for x in package_rows} != {
        "sample.docx", "sample.xlsx", "sample.pptx",
        "sample.odt", "sample.ods", "sample.odp",
    } or any(x.get("findings") for x in package_rows)):
        raise ValueError("Incomplete or failed ZIP component evidence")
    if (len(legacy_rows) != 4 or {x.get("file") for x in legacy_rows} != {
        "sample.doc", "sample.xls", "sample.ppt", "sample.rtf",
    } or any(x.get("findings") for x in legacy_rows)):
        raise ValueError("Incomplete or failed legacy component evidence")
    if any(
        name not in tool_versions or not isinstance(tool_versions[name], str)
        or not tool_versions[name].strip()
        for name in (*PACKAGES, "libreoffice", "python")
    ):
        raise ValueError("Missing exact toolchain version")
    rows = []
    for filename, (tool, derived_from) in sorted(EXPECTED.items()):
        path = folder / filename
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Missing or symlinked candidate: {filename}")
        nbytes = path.stat().st_size
        if not 0 < nbytes <= MAX_CANDIDATE_BYTES:
            raise ValueError(f"Invalid candidate size: {filename}")
        data = path.read_bytes()
        if len(data) != nbytes:
            raise ValueError(f"Candidate mutated while being read: {filename}")
        digest = hashlib.sha256(data).hexdigest()
        prior = next((x for x in legacy_rows if x.get("file") == filename), None)
        if prior is not None and prior.get("sha256") != digest:
            raise ValueError(f"Legacy audit and evidence hash disagree: {filename}")
        rows.append({
            "filename": filename,
            "bytes": nbytes,
            "sha256": digest,
            "created_with": tool,
            "derived_from": derived_from,
            "redistribution_rights": "not_asserted",
        })
    return {
        "schema": "osf-viewer-generated-office-evidence-v1",
        "candidate_count": len(rows),
        "candidates": rows,
        "checkout_git_sha": checkout_sha if checkout_sha and re.fullmatch(
            r"[a-f0-9]{40}", checkout_sha) else None,
        "dependencies": dict(sorted(tool_versions.items())),
        "zip_component_audit": package_report,
        "legacy_component_audit": legacy_report,
        "semantic_assertions": "existing_26_regressions_must_pass_before_publication",
        "source": "scripts/generate_clean_office_candidates.py",
        "notice_reference": "docs/GENERATED_OFFICE_NOTICES.md",
        "original_published_fixture_bytes_replaced": False,
        "copyright_and_redistribution_cleared": False,
        "scope": "disposable_candidates_only",
    }


def publish_record(path: Path, record: dict, *, repo_root: Path) -> None:
    """Refuse to overwrite anything, especially within the checked-out repo."""
    raw_path = Path(path)
    if raw_path.is_symlink():
        raise ValueError("Refuse symlink evidence target")
    path, root = raw_path.resolve(), Path(repo_root).resolve()
    if path == root or root in path.parents:
        raise ValueError("Cannot publish candidate evidence inside source tree")
    if not path.parent.is_dir():
        raise ValueError("Evidence destination parent directory does not exist")
    if path.exists() or path.is_symlink():
        raise FileExistsError("Evidence target already exists")
    data = json.dumps(record, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    # Exclusive creation avoids silently overwriting previous evidence.
    with path.open("x", encoding="utf-8") as file:
        file.write(data)


def build(folder: Path, package_report: dict, legacy_report: dict,
          *, checkout_sha: str | None = None) -> dict:
    return make_record(
        folder, tool_versions=_tool_versions(),
        package_report=package_report, legacy_report=legacy_report,
        checkout_sha=checkout_sha,
    )
