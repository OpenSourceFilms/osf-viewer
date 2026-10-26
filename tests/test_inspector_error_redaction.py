"""Redaction regressions for public Viewer inspector text and HTML fallback data.

Compile the *actual* pure-Python inspector function bodies from their AST.
This avoids importing optional rendering packages or reading any production
path, while verifying every formerly exception-reflecting public fallback.
"""
from __future__ import annotations

import ast
import io
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "inspectors.py"
SECRET = "synthetic-private-/workspace/.pod-persist/credential-value"


def fail(*args, **kwargs):
    raise RuntimeError(SECRET)


def subject(name: str, globals_map: dict):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    function = next(
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )
    module = ast.fix_missing_locations(
        ast.Module(body=[
            ast.ImportFrom(module="__future__",
                           names=[ast.alias(name="annotations")], level=0),
            function,
        ], type_ignores=[])
    )
    namespace = dict(globals_map)
    exec(compile(module, str(SOURCE), "exec"), namespace)
    return namespace[name]


class InspectorRedactionTests(unittest.TestCase):
    def assert_redacted(self, output, expected):
        self.assertIn(expected, output)
        self.assertNotIn(SECRET, output)
        self.assertNotIn("RuntimeError(", output)
        self.assertNotIn("OperationalError(", output)
        self.assertNotIn("Traceback", output)

    def test_top_level_text_fallback_returns_generic_report(self):
        get_text = subject("get_text", {
            "identify": lambda *args: "text",
            "OFFICE_KINDS": set(),
            "_text_plain": fail,
            "_text_binary": lambda *args: "synthetic generic hex fallback",
        })
        output = get_text(None, b"synthetic text", "bad.txt")
        self.assert_redacted(output, "text handler failed")
        self.assertIn("synthetic generic hex fallback", output)

    def test_pdf_per_page_fallback_never_reflects_extractor_error(self):
        reader = SimpleNamespace(
            pages=[SimpleNamespace(extract_text=fail)]
        )
        text_pdf = subject("_text_pdf", {
            "io": io,
            "_read_bytes": lambda *args: b"synthetic",
            "pypdf": SimpleNamespace(PdfReader=lambda *args: reader),
            "MAX_PDF_TEXT_CHARS": 10000,
        })
        self.assert_redacted(text_pdf(None, b"synthetic"), "page 1: text extraction failed")

    def test_audio_metadata_fallback_hides_parser_exception(self):
        text_audio = subject("_text_audio", {
            "io": io,
            "_read_bytes": lambda *args: b"synthetic",
            "mutagen": SimpleNamespace(File=fail),
        })
        self.assert_redacted(
            text_audio(None, b"synthetic", "synthetic.mp3"),
            "mutagen failed to parse audio metadata",
        )

    def test_directory_stat_failure_keeps_name_not_exception_details(self):
        class FakeEntry:
            name = "synthetic-file.txt"

            def stat(self):
                raise OSError(SECRET)

        parent = SimpleNamespace(iterdir=lambda: [FakeEntry()])
        text_dir = subject("_text_directory", {})
        output = text_dir(parent)
        self.assert_redacted(output, "stat unavailable")
        self.assertIn("synthetic-file.txt", output)

    def test_sqlite_fallback_hides_query_errors(self):
        class FakeConnection:
            def execute(self, command):
                if "sqlite_master" in command:
                    return [("synthetic_table",)]
                if "table_info" in command:
                    return [(0, "field", "TEXT")]
                raise sqlite3.OperationalError(SECRET)

            def close(self):
                pass

        text_sqlite = subject("_text_sqlite", {
            "sqlite3": SimpleNamespace(
                connect=lambda *args, **kwargs: FakeConnection(),
                OperationalError=sqlite3.OperationalError,
            ),
        })
        output = text_sqlite(Path("synthetic.db"))
        self.assert_redacted(output, "row count: unavailable")
        self.assertIn("sample rows unavailable", output)

    def test_parquet_fallback_hides_row_group_exception(self):
        fake_pf = SimpleNamespace(
            schema_arrow="synthetic schema", num_row_groups=1,
            read_row_group=fail,
        )
        text_parquet = subject("_text_parquet", {
            "pq": SimpleNamespace(ParquetFile=lambda *args: fake_pf),
            "json": json,
        })
        self.assert_redacted(
            text_parquet(Path("synthetic.parquet")),
            "could not read row group 0",
        )

    def test_no_exception_values_are_bound_for_future_inspector_fallbacks(self):
        # Future code that needs an exception object internally must add
        # controlled handling/tests before binding and reflecting its value.
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        names = [n.name for n in ast.walk(tree)
                 if isinstance(n, ast.ExceptHandler) and n.name is not None]
        self.assertEqual(names, [], "Inspector exception values must not enter public reports")


if __name__ == "__main__":
    unittest.main()
