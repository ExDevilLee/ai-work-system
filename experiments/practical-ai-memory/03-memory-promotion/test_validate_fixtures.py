from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from validate_fixtures import ROOT, validate


class FixtureValidationTest(unittest.TestCase):
    def copy_fixture(self, destination: Path) -> None:
        for name in ("expected", "fixtures", "prompts"):
            shutil.copytree(ROOT / name, destination / name)

    def test_frozen_fixture_passes(self) -> None:
        self.assertEqual(validate(), [])

    def test_rejects_policy_cross_contamination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.copy_fixture(root)
            path = root / "fixtures/pilot-01/conditions/direct-promotion/AGENTS.md"
            path.write_text(
                path.read_text(encoding="utf-8") + "\n当前采用规则门禁机制。\n",
                encoding="utf-8",
            )
            self.assertTrue(any("leaks policy marker" in item for item in validate(root)))

    def test_rejects_evidence_copied_into_condition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.copy_fixture(root)
            path = root / "fixtures/pilot-01/conditions/rule-gated/AGENTS.md"
            path.write_text(
                path.read_text(encoding="utf-8") + "\nOBS-102\n",
                encoding="utf-8",
            )
            self.assertTrue(any("copies evidence id" in item for item in validate(root)))


if __name__ == "__main__":
    unittest.main()
