from __future__ import annotations

import json
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

    def test_rejects_answer_leak_in_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.copy_fixture(root)
            facts = json.loads(
                (root / "expected" / "facts.json").read_text(encoding="utf-8")
            )
            leaked = next(
                fact["text"]
                for fact in facts["facts"]
                if not fact.get("prompt_exposed", False)
            )
            (root / "prompts" / "leaked.md").write_text(leaked, encoding="utf-8")

            self.assertTrue(
                any("leaked into a prompt" in error for error in validate(root))
            )

    def test_rejects_nonresident_fact_in_selective_condition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.copy_fixture(root)
            facts = json.loads(
                (root / "expected" / "facts.json").read_text(encoding="utf-8")
            )
            leaked = next(
                fact["text"] for fact in facts["facts"] if not fact["resident"]
            )
            path = (
                root
                / "fixtures"
                / "pilot-01"
                / "conditions"
                / "selective-resident"
                / "AGENTS.md"
            )
            path.write_text(path.read_text(encoding="utf-8") + leaked, encoding="utf-8")

            self.assertTrue(
                any("selective-resident presence=True" in error for error in validate(root))
            )


if __name__ == "__main__":
    unittest.main()
