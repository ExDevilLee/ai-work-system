#!/usr/bin/env python3
"""Tests for the static fixture validator — verifies it catches real problems."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from validate_fixtures import validate


class TestValidatorPasses(unittest.TestCase):
    def test_validator_passes_on_current_fixtures(self) -> None:
        errors = validate()
        self.assertEqual(errors, [], f"unexpected validation errors: {errors}")


class TestValidatorDetectsProblems(unittest.TestCase):
    """Each test temporarily corrupts a fixture and checks that validate() catches it."""

    def setUp(self) -> None:
        from fixture_model import FIXTURE
        self._fixture = FIXTURE
        self._backups: dict[Path, bytes] = {}

    def _backup(self, rel: str) -> None:
        path = self._fixture / rel
        self._backups[path] = path.read_bytes()

    def tearDown(self) -> None:
        for path, data in self._backups.items():
            path.write_bytes(data)

    def test_detects_hash_mismatch_in_source_manifest(self) -> None:
        self._backup("source-manifest.json")
        manifest = json.loads((self._fixture / "source-manifest.json").read_text("utf-8"))
        manifest["records"][0]["content_sha256"] = "0" * 64
        (self._fixture / "source-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", "utf-8"
        )
        errors = validate()
        self.assertTrue(any("content_sha256" in e for e in errors))

    def test_detects_derived_in_backup_files(self) -> None:
        self._backup("backup-manifest.json")
        backup = json.loads((self._fixture / "backup-manifest.json").read_text("utf-8"))
        backup["files"].append({
            "id": "DI-805-index",
            "path": "derived/retention-index.md",
            "stored_sha256": "0" * 64,
            "logical_version": 1,
        })
        (self._fixture / "backup-manifest.json").write_text(
            json.dumps(backup, indent=2) + "\n", "utf-8"
        )
        errors = validate()
        self.assertTrue(any("derived artifact" in e and "backup files" in e for e in errors))

    def test_detects_stale_source_manifest_hash(self) -> None:
        self._backup("backup-manifest.json")
        backup = json.loads((self._fixture / "backup-manifest.json").read_text("utf-8"))
        backup["source_manifest_sha256"] = "0" * 64
        (self._fixture / "backup-manifest.json").write_text(
            json.dumps(backup, indent=2) + "\n", "utf-8"
        )
        errors = validate()
        self.assertTrue(any("source_manifest_sha256" in e for e in errors))

    def test_detects_generated_drift(self) -> None:
        self._backup("generated/integrity-report.json")
        (self._fixture / "generated/integrity-report.json").write_text(
            '{"drifted": true}\n', "utf-8"
        )
        errors = validate()
        self.assertTrue(any("drift" in e for e in errors))


class TestRubricStructure(unittest.TestCase):
    def test_rubric_has_all_tasks(self) -> None:
        from fixture_model import ROOT, TASKS
        rubric = json.loads((ROOT / "rubrics" / "pilot-01.json").read_text("utf-8"))
        self.assertEqual(set(rubric), set(TASKS))

    def test_rubric_has_required_any_and_forbidden(self) -> None:
        from fixture_model import ROOT
        rubric = json.loads((ROOT / "rubrics" / "pilot-01.json").read_text("utf-8"))
        for task, entry in rubric.items():
            self.assertIn("required_any", entry, f"{task} missing required_any")
            self.assertIn("forbidden", entry, f"{task} missing forbidden")
            self.assertIsInstance(entry["required_any"], dict)
            self.assertIsInstance(entry["forbidden"], list)

    def test_answers_have_all_tasks(self) -> None:
        from fixture_model import ROOT, TASKS
        answers = json.loads((ROOT / "expected" / "answers.json").read_text("utf-8"))
        self.assertEqual(set(answers), set(TASKS))


if __name__ == "__main__":
    unittest.main()
