#!/usr/bin/env python3
"""Identify exact byte-inherited parts from installed Office source templates.

For disposable candidates only. Compares ZIP entry bytes, never publishes
template/document payloads and never asserts copyright ownership.
"""
from __future__ import annotations

import hashlib
from importlib import resources
from pathlib import Path, PurePosixPath
import zipfile

TEMPLATES = {
    "sample.docx": ("docx", "templates/default.docx", "python-docx"),
    "sample.pptx": ("pptx", "templates/default.pptx", "python-pptx"),
}
MAX_ARCHIVE_BYTES = 4 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 8 * 1024 * 1024
MAX_MEMBER_BYTES = 2 * 1024 * 1024


def _safe_bytes(file: Path) -> bytes:
    file = Path(file)
    if file.is_symlink() or not file.is_file():
        raise ValueError("Missing or symlinked ZIP input")
    if file.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("ZIP input exceeds size cap")
    return file.read_bytes()


def _parts(path: Path) -> tuple[str, dict[str, tuple[int, str]]]:
    raw = _safe_bytes(path)
    out: dict[str, tuple[int, str]] = {}
    with zipfile.ZipFile(path, "r") as archive:
        infos = archive.infolist()
        if not infos or sum(x.file_size for x in infos) > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("Invalid or oversized ZIP parts")
        for member in infos:
            name = member.filename
            p = PurePosixPath(name)
            if (not name or name in out or p.is_absolute() or
                    ".." in p.parts or "\\" in name or
                    member.file_size > MAX_MEMBER_BYTES or
                    member.flag_bits & 1):
                raise ValueError("Unsafe or duplicate ZIP entry")
            content = archive.read(member)
            if len(content) != member.file_size:
                raise ValueError("ZIP member size mismatch")
            out[name] = (len(content), hashlib.sha256(content).hexdigest())
    return hashlib.sha256(raw).hexdigest(), out


def inspect_pair(template: Path, generated: Path, *,
                 candidate_name: str, source_dependency: str,
                 source_template: str) -> dict:
    source_hash, source = _parts(template)
    candidate_hash, target = _parts(generated)
    shared = sorted(source.keys() & target.keys())
    exact = [
        {"part": name, "bytes": source[name][0], "sha256": source[name][1]}
        for name in shared if source[name] == target[name]
    ]
    modified = [name for name in shared if source[name] != target[name]]
    return {
        "candidate": candidate_name,
        "candidate_sha256": candidate_hash,
        "source_dependency": source_dependency,
        "source_template": source_template,
        "source_template_sha256": source_hash,
        "source_template_part_count": len(source),
        "generated_part_count": len(target),
        "same_named_part_count": len(shared),
        "byte_identical_part_count": len(exact),
        "byte_identical_parts": exact,
        "modified_same_named_parts": modified,
        "source_only_parts": sorted(source.keys() - target.keys()),
        "generated_only_parts": sorted(target.keys() - source.keys()),
        "inherited_template_rights_cleared": False,
    }


def audit(folder: Path, *, template_paths: dict[str, Path] | None = None) -> dict:
    report = []
    for filename, (package, relative, dependency) in TEMPLATES.items():
        if template_paths is None:
            # Locate files inside the actual installed distribution, not
            # a separately downloaded or potentially different template.
            with resources.as_file(resources.files(package).joinpath(relative)) as src:
                row = inspect_pair(src, Path(folder) / filename,
                                   candidate_name=filename,
                                   source_dependency=dependency,
                                   source_template=relative)
        else:
            row = inspect_pair(template_paths[filename], Path(folder) / filename,
                               candidate_name=filename,
                               source_dependency=dependency,
                               source_template=relative)
        report.append(row)
    return {
        "scope": "disposable_generated_docx_pptx",
        "candidates": report,
        "template_content_copyright_cleared": False,
    }
