"""Offline bounded directory listing acceptance with synthetic filesystem data.

No server sockets, production workspace, external credentials or renderers.
Uses the real directory helper, the actual inspector function body, and a
stubbed HTML request handler.
"""
from __future__ import annotations

import ast
import html
import io
from pathlib import Path
import runpy
import sys
import tempfile
import time
import tracemalloc
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import directory_listing  # noqa: E402
import security  # noqa: E402


def actual_text_directory():
    source = ROOT / "inspectors.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "_text_directory")
    module = ast.fix_missing_locations(ast.Module(body=[
        ast.ImportFrom(module="__future__",
                       names=[ast.alias(name="annotations")], level=0),
        function,
    ], type_ignores=[]))
    env = {
        "Path": Path,
        "time": time,
        "bounded_visible_entries": directory_listing.bounded_visible_entries,
        "MAX_DISPLAY": directory_listing.MAX_DISPLAY,
    }
    exec(compile(module, str(source), "exec"), env)
    return env["_text_directory"]


def stubbed_viewer_handler():
    inspectors = types.ModuleType("inspectors")
    inspectors.identify = lambda *args: "directory"
    inspectors.get_text = lambda *args, **kwargs: "synthetic text"
    with mock.patch.dict(sys.modules, {"inspectors": inspectors}):
        env = runpy.run_path(str(ROOT / "app.py"), run_name="bounded_listing_test")
    return env["ViewerHandler"]


class FakeScandir:
    """Virtual 25,000-entry directory without creating an enormous directory."""
    def __init__(self, count=25000):
        self.count = count
        self.seen = 0
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def __iter__(self):
        return self

    def __next__(self):
        if self.seen >= self.count:
            raise StopIteration
        n = self.count - self.seen - 1
        self.seen += 1
        label = ("denied_" if n % 7 == 0 else "frame_") + ("%06d" % n)
        return types.SimpleNamespace(path="/synthetic/" + label)


class BoundedDirectoryTests(unittest.TestCase):
    def test_virtual_directory_scans_all_but_retains_only_2000(self):
        scan = FakeScandir()
        with mock.patch.object(directory_listing.os, "scandir", return_value=scan):
            with mock.patch.object(directory_listing.os, "listdir",
                                   side_effect=AssertionError("no full os.listdir")):
                tracemalloc.start()
                try:
                    selected, count = directory_listing.bounded_visible_entries(
                        Path("/synthetic"), lambda p: p.name.startswith("denied_")
                    )
                    _current, peak = tracemalloc.get_traced_memory()
                finally:
                    tracemalloc.stop()
        self.assertTrue(scan.closed)
        self.assertEqual(scan.seen, 25000)
        self.assertEqual(count, 25000 - len(range(0, 25000, 7)))
        self.assertEqual(len(selected), 2000)
        names = [p.name for p in selected]
        self.assertEqual(names, sorted(names))
        self.assertEqual(names[0], "frame_000001")
        self.assertTrue(all(not name.startswith("denied_") for name in names))
        self.assertLess(peak, 12 * 1024 * 1024, "retained directory metadata must be bounded")

    def test_scandir_closes_on_deny_predicate_failure(self):
        scan = FakeScandir(count=3)
        def failure(_path):
            raise RuntimeError("synthetic failure")
        with mock.patch.object(directory_listing.os, "scandir", return_value=scan):
            with self.assertRaises(RuntimeError):
                directory_listing.bounded_visible_entries(Path("/synthetic"), failure)
        self.assertTrue(scan.closed)

    def test_rejects_out_of_range_or_nonnumeric_caps(self):
        for value in (0, -1, True, 2001, 2.5, "2000"):
            with self.subTest(limit=value), self.assertRaises(ValueError):
                directory_listing.bounded_visible_entries(Path("/synthetic"), limit=value)


class RealSyntheticDirectoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="osfv_directory_")
        cls.base = Path(cls.tmp.name)
        cls.root = cls.base / "published"
        cls.root.mkdir()
        cls.source = cls.root / "frames"
        cls.source.mkdir()
        for n in range(2007):
            (cls.source / ("frame_%05d.png" % n)).touch()
        (cls.source / ".claude").mkdir()
        (cls.source / ".claude" / "synthetic.txt").write_text("not public")
        (cls.source / "outbound").symlink_to(cls.base, target_is_directory=True)
        cls.denylist = [cls.root / ".claude"]
        cls.predicate = staticmethod(lambda p: security.is_denied(p, cls.denylist, cls.root))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_directory_text_has_exact_visible_count_and_truncation(self):
        text_dir = actual_text_directory()
        output = text_dir(self.source, self.predicate)
        self.assertIn("entries: 2007", output)
        self.assertIn("truncated, 7 more entries not shown", output)
        self.assertEqual(output.count(".png"), 2000)
        self.assertIn("frame_00000.png", output)
        self.assertIn("frame_01999.png", output)
        self.assertNotIn("frame_02000.png", output)
        self.assertNotIn(".claude", output)
        self.assertNotIn("outbound", output)

    def test_html_hub_shows_same_2000_visible_names_without_unsafe_links(self):
        Handler = stubbed_viewer_handler()
        h = object.__new__(Handler)
        captured = []
        h._send_text = lambda status, body, content_type=None: captured.append(
            (status, body, content_type)
        )
        with mock.patch.dict(Handler._handle_hub.__globals__,
                             {"_denied_predicate": lambda: self.predicate}):
            h._handle_hub(self.source, "frames")
        self.assertEqual(captured[0][0], 200)
        body = captured[0][1]
        self.assertEqual(body.count("<li><a "), 2000)
        self.assertIn("frame_01999.png", body)
        self.assertNotIn("frame_02000.png", body)
        self.assertNotIn(".claude", body)
        self.assertNotIn("outbound", body)

    def test_html_and_text_use_shared_bounded_helper(self):
        html_source = (ROOT / "app.py").read_text(encoding="utf-8")
        text_source = (ROOT / "inspectors.py").read_text(encoding="utf-8")
        helper_source = (ROOT / "directory_listing.py").read_text(encoding="utf-8")
        self.assertIn("bounded_visible_entries(real, pred)", html_source)
        self.assertIn("bounded_visible_entries(path, is_denied)", text_source)
        self.assertIn("os.scandir(directory)", helper_source)
        self.assertIn("heapq.nsmallest(limit", helper_source)
        self.assertNotIn("sorted(real.iterdir()", html_source)
        self.assertNotIn("sorted(path.iterdir()", text_source)


if __name__ == "__main__":
    unittest.main()
