"""Offline legacy OLE/RTF candidate-audit tests. Never opens real fixtures."""
from __future__ import annotations

import json
from pathlib import Path
import runpy
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCANNER = runpy.run_path(
    str(ROOT / "scripts" / "audit_generated_legacy_components.py"),
    run_name="legacy_audit_import",
)
scan_ole = SCANNER["inspect_ole"]
scan_rtf = SCANNER["inspect_rtf"]
audit = SCANNER["audit"]
OLE_MAGIC = SCANNER["OLE_MAGIC"]


class FakeOle:
    def __init__(self, filename, raise_defects):
        self.filename = filename

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def listdir(self, streams, storages):
        return [["WordDocument"], ["\x05SummaryInformation"]]

    def get_metadata(self):
        return types.SimpleNamespace(
            author="alice@icloud.com", template="Normal.dotm",
            title="synthetic", create_time=None, last_saved_time=None,
        )


class LegacyAuditTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="osf_legacy_audit_")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_valid_rtf_reports_metadata_controls_without_rejecting_them(self):
        path = self.root / "sample.rtf"
        path.write_bytes(b"{\\rtf1\\ansi{\\info{\\author Open Source Films}}Hello}")
        report = scan_rtf(path)
        self.assertEqual(report["findings"], [])
        self.assertTrue(report["sha256"])
        self.assertIn(
            "rtf_generator_author_or_timestamp_control_present",
            report["informational_flags"],
        )

    def test_embedded_rtf_object_picture_or_external_field_rejected(self):
        for name, payload in (
            ("object", b"{\\rtf1 {\\object\\objdata aabb}}"),
            ("picture", b"{\\rtf1 {\\pict\\pngblip deadbeef}}"),
            ("external", b"{\\rtf1 {\\field{\\*\\fldinst INCLUDEPICTURE https://example.test/p}}}"),
        ):
            with self.subTest(name=name):
                path = self.root / "sample.rtf"
                path.write_bytes(payload)
                self.assertTrue(scan_rtf(path)["findings"])

    def test_private_path_or_email_is_rejected(self):
        path = self.root / "sample.rtf"
        path.write_bytes(b"{\\rtf1 {\\info{\\author alice@gmail.com}}}")
        self.assertIn("potential_private_path_or_email", scan_rtf(path)["findings"])
        self.assertNotIn("alice@gmail.com", json.dumps(scan_rtf(path)))

    def test_missing_or_symlinked_input_fails_closed(self):
        path = self.root / "sample.rtf"
        self.assertIn("missing_or_symlinked_input", scan_rtf(path)["findings"])
        path.symlink_to(self.root / "does_not_exist")
        self.assertIn("missing_or_symlinked_input", scan_rtf(path)["findings"])

    def test_invalid_ole_magic_fails_closed(self):
        path = self.root / "sample.doc"
        path.write_bytes(b"not an OLE2 file")
        self.assertIn("invalid_ole_signature", scan_ole(path)["findings"])

    def test_ole_lists_streams_and_redacts_metadata_values(self):
        path = self.root / "sample.doc"
        path.write_bytes(OLE_MAGIC + b"\0" * 64)
        stub = types.SimpleNamespace(
            OleFileIO=FakeOle,
            DEFECT_INCORRECT=1,
        )
        with mock.patch.dict(sys.modules, {"olefile": stub}):
            result = scan_ole(path)
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["component_count"], 2)
        self.assertIn("author", result["metadata_fields_present"])
        self.assertIn("template", result["metadata_fields_present"])
        self.assertNotIn("alice@icloud.com", json.dumps(result))
        self.assertFalse(result["copyright_and_redistribution_cleared"])

    def test_nested_ole_object_storage_is_rejected(self):
        class EmbeddedOle(FakeOle):
            def listdir(self, streams, storages):
                return [["WordDocument"], ["ObjectPool", "Embedded1"]]
        path = self.root / "sample.doc"
        path.write_bytes(OLE_MAGIC + b"\0" * 64)
        stub = types.SimpleNamespace(OleFileIO=EmbeddedOle, DEFECT_INCORRECT=1)
        with mock.patch.dict(sys.modules, {"olefile": stub}):
            result = scan_ole(path)
        self.assertIn("embedded_or_macro_container", result["findings"])

    def test_directory_audit_requires_all_four_files(self):
        report = audit(self.root)
        self.assertEqual(len(report["results"]), 4)
        self.assertFalse(report["pass_structural_checks"])
        self.assertFalse(report["copyright_and_redistribution_cleared"])


if __name__ == "__main__":
    unittest.main()
