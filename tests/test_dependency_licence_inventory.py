"""Offline consistency check of the 21 Viewer pinned dependency licence rows.

Checks table coverage, not the correctness of upstream licence terms or
whether redistribution of the application is legally authorised.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "requirements.lock.txt"
REGISTER = ROOT / "DEPENDENCY_LICENSES.md"


class PinnedDependencyLicenceInventoryTests(unittest.TestCase):
    def test_all_exact_pins_covered_once(self):
        pins = [line.strip() for line in LOCK.read_text().splitlines()
                if line.strip() and not line.startswith("#")]
        self.assertEqual(len(pins), 21)
        self.assertTrue(all(re.fullmatch(r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.+-]+", pin)
                            for pin in pins))
        documented = re.findall(
            r"(?m)^\| ([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+) \|", REGISTER.read_text()
        )
        names = [name + "==" + version for name, version in documented]
        self.assertEqual(sorted(names), sorted(pins))
        self.assertEqual(len(set(names)), 21)

    def test_every_pin_links_to_its_published_version(self):
        text = REGISTER.read_text(encoding="utf-8")
        for pin in LOCK.read_text().splitlines():
            if not pin.strip() or pin.startswith("#"):
                continue
            package, version = pin.split("==", 1)
            with self.subTest(package=package):
                self.assertIn(
                    "https://pypi.org/project/" + package + "/" + version + "/", text
                )

    def test_copyleft_and_uncleared_boundaries_are_explicit(self):
        rows = REGISTER.read_text(encoding="utf-8")
        self.assertRegex(rows, r"\| mutagen==1\.48\.1 \| GPL-2\.0-or-later \|")
        for item in ["inflate64", "multivolumefile", "py7zr", "pybcj", "pyppmd"]:
            with self.subTest(package=item):
                self.assertRegex(rows, r"\| " + item
                                 + r"==[0-9.]+ \| LGPL-2\.1-or-later \|")
        self.assertIn("odfpy==1.4.1 | Apache / GPL / LGPL (terms unresolved)", rows)
        self.assertIn("creates no new licence grant", rows)
        self.assertIn("not source-code licence verification", rows)


if __name__ == "__main__":
    unittest.main()
