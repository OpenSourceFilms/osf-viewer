#!/usr/bin/env python3
"""Read-only safety inventory for Viewer synthetic Office ZIP fixtures.

This checks package structure and avoidable redistribution/privacy hazards,
not copyright ownership. Legacy OLE .doc/.xls/.ppt and .rtf need separate
provenance review, and the intentionally corrupt .docx is excluded.
"""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
ARCHIVES = (
    "sample.docx", "sample.xlsx", "sample.pptx",
    "sample.odt", "sample.ods", "sample.odp",
)
MAX_ENTRY_BYTES = 2_000_000
MAX_TOTAL_BYTES = 8_000_000
PRIVATE_PATH = re.compile(r"(?:[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/]|/home/[^/]+/|/Users/[^/]+/)")
PERSONAL_EMAIL = re.compile(r"(?<![\w.])[^\s<>@\"']+@(?:gmail|outlook|hotmail|yahoo|icloud)\.com\b", re.I)
RESTRICTED_PART = re.compile(r"(?:^|/)(?:vbaProject\.bin|activeX|embeddings|_xmlsignatures)(?:/|$)", re.I)


XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def _is_external_odf_reference(value: str) -> bool:
    """Allow package-local paths and fragments, reject URLs and escapes."""
    target = value.strip()
    return bool(target and (
        URI_SCHEME.match(target)
        or target.startswith("/")
        or chr(92) in target
        or ".." in PurePosixPath(target).parts
    ))


def _xml_visible_values(root: ET.Element) -> str:
    """Check text and attributes after XML entity/encoding decoding."""
    return "\n".join(
        ["".join(root.itertext())] +
        [value for element in root.iter() for value in element.attrib.values()]
    )


def scan_package(path: Path) -> dict:
    issues: list[str] = []
    previews: list[str] = []
    settings: list[str] = []
    custom_parts: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if not infos:
                issues.append("empty_archive")
            total = sum(info.file_size for info in infos)
            if total > MAX_TOTAL_BYTES:
                issues.append("archive_uncompressed_size_limit")
            for info in infos:
                name = info.filename
                posix = PurePosixPath(name)
                if (posix.is_absolute() or any(p in ("..", ".") for p in posix.parts)
                        or "\\" in name or name.startswith("/")):
                    issues.append("unsafe_member_path")
                    continue
                if info.flag_bits & 0x1:
                    issues.append("encrypted_member")
                if info.file_size > MAX_ENTRY_BYTES:
                    issues.append("oversize_member")
                    continue
                if RESTRICTED_PART.search(name):
                    issues.append("embedded_executable_or_attachment")
                if name in ("docProps/thumbnail.jpeg", "docProps/thumbnail.png"):
                    previews.append(name)
                if "printerSettings/" in name:
                    settings.append(name)
                if name.startswith("customXml/"):
                    custom_parts.append(name)
                if name.endswith(".rels"):
                    try:
                        root = ET.fromstring(archive.read(info))
                        for item in root.iter():
                            if item.attrib.get("TargetMode", "").lower() == "external":
                                issues.append("external_relationship")
                    except (ET.ParseError, RuntimeError, OSError, ValueError):
                        issues.append("invalid_relationship_xml")
                metadata_part = name in ("docProps/core.xml", "meta.xml")
                odf_xml = path.suffix.lower() in (".odt", ".ods", ".odp") and name.endswith(".xml")
                if metadata_part or odf_xml:
                    try:
                        # Parse bytes directly to respect declared XML encodings
                        # and expand character references before privacy checks.
                        root = ET.fromstring(archive.read(info))
                        if metadata_part:
                            meta = _xml_visible_values(root)
                            if PRIVATE_PATH.search(meta):
                                issues.append("personal_file_path_metadata")
                            if PERSONAL_EMAIL.search(meta):
                                issues.append("personal_email_metadata")
                        if odf_xml:
                            for element in root.iter():
                                href = element.attrib.get(XLINK_HREF)
                                if href is not None and _is_external_odf_reference(href):
                                    issues.append("external_odf_reference")
                    except (ET.ParseError, OSError, ValueError, RuntimeError):
                        issues.append("invalid_package_xml")
    except (zipfile.BadZipFile, OSError):
        issues.append("bad_archive")
    return {
        "file": path.name,
        "issues": sorted(set(issues)),
        "embedded_preview": sorted(previews),
        "printer_settings": sorted(settings),
        "custom_xml_parts": len(custom_parts),
    }


def main() -> int:
    results = [scan_package(FIXTURES / name) for name in ARCHIVES]
    print(json.dumps({"results": results}, indent=2, sort_keys=True))
    return int(any(result["issues"] for result in results))


if __name__ == "__main__":
    sys.exit(main())
