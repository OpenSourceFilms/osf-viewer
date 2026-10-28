#!/usr/bin/env python3
"""Full Viewer Office fixture acceptance against disposable generated candidates.

Reuses the existing unmodified semantic/legacy/fallback/preview unittest
classes by redirecting only their FIXTURES constant in this test process.
Never writes to tests/fixtures or modifies the published fixture manifest.

Requires the pinned Viewer Python libraries and LibreOffice; this is NOT a
stdlib-only CI test or a substitute for checking redistribution rights.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
EXPECTED = {
    "sample.doc", "sample.docx", "sample.xls", "sample.xlsx",
    "sample.ppt", "sample.pptx", "sample.rtf",
    "sample.odt", "sample.ods", "sample.odp",
    "corrupt.docx", "corrupt.xls",
}
CLASSES = (
    "DocxTests", "XlsxTests", "PptxTests", "OdfTests",
    "LegacyOfficeConversionTests", "CorruptFileFallbackTests",
    "TruncationCapTests", "PreviewPdfCacheTests",
)


def main() -> int:
    from scripts.verify_fixture_manifest import verify
    if verify(ROOT):
        raise SystemExit("Existing published fixture inventory failed before test")
    with tempfile.TemporaryDirectory(prefix="osf_office_compat_") as tmp:
        base = Path(tmp)
        generated = base / "generated"
        cmd = [
            sys.executable, str(ROOT / "scripts" / "generate_clean_office_candidates.py"),
            "--out", str(generated), "--with-legacy",
        ]
        subprocess.run(cmd, cwd=ROOT, check=True, timeout=240)
        actual = {path.name for path in generated.iterdir()}
        if actual != EXPECTED:
            raise SystemExit(
                "Candidate set mismatch: missing="
                + str(sorted(EXPECTED - actual))
                + "; extra=" + str(sorted(actual - EXPECTED))
            )
        # The Viewer imports cache.CACHE_DIR as a global. Redirect it before
        # running any conversion or preview, to avoid /workspace writes.
        import cache
        cache.CACHE_DIR = base / "cache"
        import office_extract
        office_extract._LO_PROFILE_TEMPLATE = None
        from tests import test_office_extract as original
        original.FIXTURES = generated

        # Record inherited formatting and fail closed on media, attachments,
        # external OOXML relationships or sensitive metadata in new candidates.
        from scripts.audit_generated_office_components import audit_directory
        import json
        provenance = audit_directory(generated)
        print(json.dumps(provenance, indent=2, sort_keys=True), flush=True)
        if not provenance["safe_from_unreviewed_binary_components"]:
            raise SystemExit("Generated package component audit failed")
        # The four legacy formats are OLE2/RTF, not ZIP. Inspect their
        # container/metadata structure separately without logging raw values.
        from scripts.audit_generated_legacy_components import audit as audit_legacy
        legacy = audit_legacy(generated)
        print(json.dumps(legacy, indent=2, sort_keys=True), flush=True)
        if not legacy["pass_structural_checks"]:
            raise SystemExit("Generated legacy Office component audit failed")
        # These structural checks do not certify embedded legacy objects or
        # copyright/redistribution rights.
        # The package scanner's old-fixture expectations include inherited
        # thumbnails; its scanner itself must find none in the new candidates.
        from scripts.audit_fixture_packages import scan_package, ARCHIVES
        for filename in ARCHIVES:
            result = scan_package(generated / filename)
            if result["issues"] or result["embedded_preview"] or result["printer_settings"] or result["custom_xml_parts"]:
                raise SystemExit("Candidate package safety failure: " + repr(result))

        suite = unittest.TestSuite(
            unittest.defaultTestLoader.loadTestsFromTestCase(
                getattr(original, name)
            )
            for name in CLASSES
        )
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        if verify(ROOT):
            raise SystemExit("Existing published fixture inventory changed during tests")
        if not result.wasSuccessful() or result.testsRun != 26:
            return 1
        from scripts.record_generated_office_evidence import build, publish_record
        evidence = build(
            generated, provenance, legacy, checkout_sha=os.environ.get("GITHUB_SHA")
        )
        destination = os.environ.get("OSF_OFFICE_EVIDENCE_PATH")
        if destination:
            publish_record(Path(destination), evidence, repo_root=ROOT)
            print("Published provenance record for all 12 disposable candidates.")
        else:
            print(
                "Generated and validated 12 SHA-256 candidate records "
                "(no output path requested)."
            )
        print(
            f"PASS: {result.testsRun} unchanged Viewer Office assertions "
            "against 12 disposable generated candidates"
        )
        print("Existing rights-pending binary fixtures remain untouched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
