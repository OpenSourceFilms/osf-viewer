#!/usr/bin/env python3
"""Inspect disposable legacy Office outputs for OLE/RTF component risks.

Read only. Does not parse embedded Office objects or establish copyright
ownership. Avoids logging raw author/property strings or document contents.
The olefile 0.47 dependency is audit-only and not part of the Viewer runtime.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys

NAMES = ("sample.doc", "sample.xls", "sample.ppt", "sample.rtf")
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_MEDIA_INSPECTION_BYTES = 4 * 1024 * 1024
OLE_MAGIC = bytes.fromhex("d0cf11e0a1b11ae1")
HARD_OLE_PARTS = re.compile(
    r"(?:^|/)(?:vba|macros|_vba_project_cur|ole10native|"
    r"objectpool|embeddings|activex|package)(?:/|$)", re.I
)
POSSIBLE_MEDIA = re.compile(r"(?:^|/)(?:pictures|images|media)(?:/|$)", re.I)
RTF_EMBEDDED = re.compile(
    rb"\\(?:object|objdata|pict|shppict|nonshppict|datastore)\b", re.I
)
RTF_EXTERNAL_FIELD = re.compile(
    rb"\\fldinst[^{}]{0,512}(?:INCLUDEPICTURE|INCLUDETEXT|DDEAUTO|"
    rb"(?:https?|file):)", re.I | re.S
)
RTF_METADATA = re.compile(
    rb"\\(?:author|operator|company|generator|creatim|revtim|printim)\b", re.I
)
PRIVATE_PATH = re.compile(
    rb"(?:[A-Za-z]:\\Users\\|/home/[^/\x00-\x20]+/|"
    rb"/Users/[^/\x00-\x20]+/)", re.I
)
PERSONAL_EMAIL = re.compile(
    rb"[A-Za-z0-9_.+-]+@(?:gmail|hotmail|outlook|yahoo|icloud)\.com", re.I
)
META_FIELDS = (
    "title", "subject", "author", "last_saved_by", "template",
    "comments", "company", "manager", "create_time", "last_saved_time",
)


def _base(file: Path, kind: str) -> dict:
    return {
        "file": file.name,
        "format": kind,
        "sha256": None,
        "bytes": None,
        "component_count": None,
        "possible_media_streams": [],
        "metadata_fields_present": [],
        "informational_flags": [],
        "findings": [],
        "copyright_and_redistribution_cleared": False,
    }


def _safe_file(file: Path, result: dict) -> bytes | None:
    if file.is_symlink() or not file.is_file():
        result["findings"].append("missing_or_symlinked_input")
        return None
    size = file.stat().st_size
    if size > MAX_FILE_BYTES:
        result["findings"].append("oversize_input")
        return None
    raw = file.read_bytes()
    result["bytes"] = len(raw)
    result["sha256"] = hashlib.sha256(raw).hexdigest()
    return raw


def inspect_ole(file: Path) -> dict:
    result = _base(file, "OLE2")
    raw = _safe_file(file, result)
    if raw is None:
        return result
    if not raw.startswith(OLE_MAGIC):
        result["findings"].append("invalid_ole_signature")
        return result
    try:
        import olefile
    except ImportError:
        result["findings"].append("missing_audit_only_olefile_dependency")
        return result
    try:
        with olefile.OleFileIO(file, raise_defects=olefile.DEFECT_INCORRECT) as ole:
            parts = ole.listdir(streams=True, storages=True)
            result["component_count"] = len(parts)
            if not parts:
                result["findings"].append("empty_ole_directory")
            for part in parts:
                name = "/".join(part).lower()
                if HARD_OLE_PARTS.search(name):
                    result["findings"].append("embedded_or_macro_container")
                if POSSIBLE_MEDIA.search(name):
                    # Directory names alone cannot distinguish an empty PPT
                    # Pictures stream from an embedded image payload.
                    try:
                        if ole.get_type(part) != olefile.STGTY_STREAM:
                            result["informational_flags"].append(
                                "possible_media_storage_needs_manual_review"
                            )
                            continue
                        size = ole.get_size(part)
                        if size < 0 or size > MAX_MEDIA_INSPECTION_BYTES:
                            result["findings"].append(
                                "media_stream_size_uninspectable"
                            )
                            continue
                        data = ole.openstream(part).read(size + 1)
                        if len(data) != size:
                            result["findings"].append(
                                "media_stream_size_mismatch"
                            )
                            continue
                        result["possible_media_streams"].append({
                            "name": name,
                            "bytes": size,
                            "sha256": hashlib.sha256(data).hexdigest()
                            if size else None,
                        })
                        result["informational_flags"].append(
                            "nonempty_media_stream_needs_content_review"
                            if size else "empty_media_stream"
                        )
                    except (OSError, ValueError, IndexError, TypeError):
                        result["findings"].append("unreadable_media_stream")
            # OLE property-stream values may contain external/user metadata.
            # Record the *fields*, never their values in public CI output.
            try:
                metadata = ole.get_metadata()
                result["metadata_fields_present"] = sorted(
                    field for field in META_FIELDS
                    if getattr(metadata, field, None) not in (None, "", b"")
                )
                if any(field in result["metadata_fields_present"] for field in
                       ("author", "last_saved_by", "template", "company", "manager")):
                    result["informational_flags"].append(
                        "creator_or_template_attribution_requires_notice_review"
                    )
                if any(field in result["metadata_fields_present"] for field in
                       ("create_time", "last_saved_time")):
                    result["informational_flags"].append(
                        "document_creation_or_save_timestamps_present"
                    )
            except (OSError, ValueError, TypeError, UnicodeError):
                result["findings"].append("unreadable_ole_property_metadata")
    except (OSError, ValueError, IndexError, TypeError, EOFError):
        result["findings"].append("unreadable_or_corrupt_ole_directory")
    result["findings"] = sorted(set(result["findings"]))
    result["informational_flags"] = sorted(set(result["informational_flags"]))
    return result


def inspect_rtf(file: Path) -> dict:
    result = _base(file, "RTF")
    raw = _safe_file(file, result)
    if raw is None:
        return result
    if not raw.lstrip().startswith(b"{\\rtf"):
        result["findings"].append("invalid_rtf_header")
        return result
    if RTF_EMBEDDED.search(raw):
        result["findings"].append("rtf_embedded_picture_or_object_control")
    if RTF_EXTERNAL_FIELD.search(raw):
        result["findings"].append("rtf_external_field_instruction")
    if PRIVATE_PATH.search(raw) or PERSONAL_EMAIL.search(raw):
        result["findings"].append("potential_private_path_or_email")
    result["component_count"] = len(re.findall(rb"\\(?:fonttbl|colortbl|stylesheet)\b", raw))
    if RTF_METADATA.search(raw):
        result["informational_flags"].append(
            "rtf_generator_author_or_timestamp_control_present"
        )
    result["findings"] = sorted(set(result["findings"]))
    return result


def audit(folder: Path) -> dict:
    results = []
    for name in NAMES:
        file = folder / name
        result = inspect_rtf(file) if name.endswith(".rtf") else inspect_ole(file)
        results.append(result)
    return {
        "scope": "disposable_generated_legacy_candidates_only",
        "results": results,
        "pass_structural_checks": all(not r["findings"] for r in results),
        "copyright_and_redistribution_cleared": False,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: audit_generated_legacy_components.py FOLDER", file=sys.stderr)
        return 2
    report = audit(Path(argv[1]))
    print(json.dumps(report, indent=2, sort_keys=True))
    return int(not report["pass_structural_checks"])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
