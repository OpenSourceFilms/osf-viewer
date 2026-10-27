#!/usr/bin/env python3
"""Read-only component and metadata inventory for GENERATED Office candidates.

This identifies inherited XML templates/themes and refuses binary media,
attachments, external OOXML relationships and unsafe ZIP members. It does not
prove ownership or licence compliance of source software or generated output.
"""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import xml.etree.ElementTree as ET
import zipfile

NAMES = (
    "sample.docx", "sample.xlsx", "sample.pptx",
    "sample.odt", "sample.ods", "sample.odp",
)
MAX_MEMBER = 2_000_000
MAX_TOTAL = 8_000_000
BANNED_PATH = re.compile(
    r"(?:^|/)(?:media|embeddings|activex|customxml|printersettings|"
    r"_xmlsignatures|vbaProject\.bin)(?:/|$)", re.I,
)
PRIVATE_TEXT = re.compile(
    r"(?:[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/]|"
    r"/home/[^/]+/|/Users/[^/]+/|"
    r"\b[^\s<>\"']+@(?:gmail|hotmail|outlook|yahoo|icloud)\.com\b)", re.I,
)


def _is_inherited_template_part(name: str) -> bool:
    return (
        name in ("word/styles.xml", "word/stylesWithEffects.xml",
                 "word/fontTable.xml", "word/numbering.xml",
                 "word/settings.xml", "word/webSettings.xml",
                 "xl/styles.xml", "styles.xml")
        or name.startswith(("word/theme/", "xl/theme/", "ppt/theme/",
                             "ppt/slideMasters/", "ppt/slideLayouts/",
                             "ppt/notesMasters/"))
    )


def inspect_package(path: Path) -> dict:
    findings: list[str] = []
    inherited: list[str] = []
    names: list[str] = []
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            if not infos:
                findings.append("empty_package")
            if sum(item.file_size for item in infos) > MAX_TOTAL:
                findings.append("total_uncompressed_bytes_exceeded")
            seen: set[str] = set()
            for entry in infos:
                name = entry.filename
                names.append(name)
                parts = PurePosixPath(name)
                if name in seen:
                    findings.append("duplicate_part:" + name)
                seen.add(name)
                if (parts.is_absolute() or ".." in parts.parts
                        or "\\" in name or not name
                        or name.startswith("/")):
                    findings.append("unsafe_part:" + name)
                    continue
                if (entry.flag_bits & 0x1 or entry.file_size > MAX_MEMBER
                        or stat.S_ISLNK(entry.external_attr >> 16)):
                    findings.append("encrypted_oversize_or_symlink:" + name)
                    continue
                if BANNED_PATH.search(name):
                    findings.append("embedded_or_unreviewed_part:" + name)
                    continue
                if name != "mimetype" and not name.endswith((".xml", ".rels")):
                    findings.append("non_xml_or_media_part:" + name)
                    continue
                if _is_inherited_template_part(name):
                    inherited.append(name)
                if name.endswith(".rels"):
                    try:
                        root = ET.fromstring(archive.read(entry))
                        if any(
                            element.attrib.get("TargetMode", "").lower()
                            == "external" for element in root.iter()
                        ):
                            findings.append("external_relationship:" + name)
                    except (ET.ParseError, OSError, RuntimeError, ValueError):
                        findings.append("invalid_relationships:" + name)
                if name in ("docProps/core.xml", "meta.xml"):
                    try:
                        text = archive.read(entry).decode("utf-8", "replace")
                        if PRIVATE_TEXT.search(text):
                            findings.append("private_metadata:" + name)
                    except (OSError, RuntimeError):
                        findings.append("invalid_metadata:" + name)
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
        findings.append("unreadable_package")
    return {
        "file": path.name,
        "parts_count": len(names),
        "template_and_formatting_parts": sorted(inherited),
        "findings": sorted(set(findings)),
    }


def audit_directory(folder: Path) -> dict:
    results = [inspect_package(folder / name) for name in NAMES]
    return {
        "classification": "generated_source_candidates_not_copyright_clearance",
        "packages": results,
        "safe_from_unreviewed_binary_components": all(
            not item["findings"] for item in results
        ),
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: audit_generated_office_components.py DIRECTORY", file=sys.stderr)
        return 2
    result = audit_directory(Path(argv[1]))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["safe_from_unreviewed_binary_components"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
