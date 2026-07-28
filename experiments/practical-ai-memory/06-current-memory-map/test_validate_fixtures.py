from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from validate_fixtures import ROOT, validate


CONDITIONS = ("source-only", "flat-index", "state-projection")
TASKS = (
    "active-decision",
    "superseded-rule",
    "unresolved-conflict",
    "scope-boundary",
    "pending-observation",
)


class FixtureValidationTest(unittest.TestCase):
    def write_json(self, path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def create_valid_fixture(self, root: Path) -> None:
        fixture_root = root / "fixtures" / "pilot-01"
        records = []
        for task_index, task in enumerate(TASKS, start=1):
            first_id = f"SYN-{task_index:02d}-A"
            second_id = f"SYN-{task_index:02d}-B"
            first_source = f"records/{task}-a.md"
            second_source = f"records/{task}-b.md"
            first_status = "active"
            second_status = "pending-validation"
            relations: list[dict[str, str]] = []
            if task == "superseded-rule":
                first_status = "superseded"
                second_status = "active"
                relations = [{"type": "supersedes", "target": first_id}]
            elif task == "unresolved-conflict":
                first_status = "conflict"
                second_status = "conflict"
                relations = [{"type": "conflicts-with", "target": first_id}]
            elif task == "scope-boundary":
                first_status = "active"
            records.extend(
                [
                    {
                        "id": first_id,
                        "task_id": task,
                        "title": f"Synthetic note {task_index}A",
                        "status": first_status,
                        "scope": "macos" if task == "scope-boundary" else "project",
                        "source": first_source,
                        "relations": [],
                    },
                    {
                        "id": second_id,
                        "task_id": task,
                        "title": f"Synthetic note {task_index}B",
                        "status": second_status,
                        "scope": "project",
                        "source": second_source,
                        "relations": relations,
                    },
                ]
            )
            for suffix, label in (("a", "first"), ("b", "second")):
                path = fixture_root / "records" / f"{task}-{suffix}.md"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    f"# Synthetic note {task_index}{suffix.upper()}\n\n"
                    f"This is the {label} synthetic fact for topic {task_index}.\n",
                    encoding="utf-8",
                )

        self.write_json(
            fixture_root / "manifest.json",
            {
                "schema_version": 1,
                "condition_ids": list(CONDITIONS),
                "task_ids": list(TASKS),
                "records": records,
            },
        )

        for condition in CONDITIONS:
            path = fixture_root / "conditions" / condition / "AGENTS.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "# Synthetic workspace instructions\n\n"
                "Read the available navigation aid, verify evidence, and cite "
                "the relative sources used.\n",
                encoding="utf-8",
            )

        for task in TASKS:
            prompt = root / "prompts" / f"{task}.md"
            prompt.parent.mkdir(parents=True, exist_ok=True)
            prompt.write_text(
                "# Task\n\n"
                "1. What fact is currently supported for this topic?\n"
                "2. What action should be taken now?\n"
                "3. What boundary must remain explicit?\n"
                "4. Which relative sources did you actually use?\n",
                encoding="utf-8",
            )

        answers = {}
        rubric = {}
        for task_index, task in enumerate(TASKS, start=1):
            answers[task] = {
                "fact_state": f"Frozen fact {task_index}",
                "current_action": f"Frozen action {task_index}",
                "boundary": f"Frozen boundary {task_index}",
                "prohibited": [f"Forbidden conclusion {task_index}"],
                "expected_sources": [
                    f"records/{task}-a.md",
                    f"records/{task}-b.md",
                ],
            }
            rubric[task] = {
                "max_score": 5,
                "criteria": [
                    {
                        "id": "correct-fact-state",
                        "points": 1,
                        "description": "Correct fact and state",
                    },
                    {
                        "id": "correct-current-action",
                        "points": 1,
                        "description": "Correct current action",
                    },
                    {
                        "id": "correct-boundary",
                        "points": 1,
                        "description": "Correct relation, scope, or uncertainty boundary",
                    },
                    {
                        "id": "no-prohibited-conclusion",
                        "points": 1,
                        "description": "No prohibited promotion, selection, or generalization",
                    },
                    {
                        "id": "correct-source-citation",
                        "points": 1,
                        "description": "Correct source citation actually used",
                    },
                ],
            }
        self.write_json(root / "expected" / "answers.json", answers)
        self.write_json(
            root / "expected" / "rubric.json",
            {
                "per_task_max_score": 5,
                "single_round_max_score": 25,
                "formal_repeats": 3,
                "formal_max_score": 75,
                "tasks": rubric,
            },
        )

    def validate_temporary(self, mutation=None, require_generated: bool = False):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.create_valid_fixture(root)
            if mutation is not None:
                mutation(root)
            return validate(root, require_generated=require_generated)

    def test_fully_valid_temporary_fixture(self) -> None:
        self.assertEqual(self.validate_temporary(), [])

    def test_rejects_prompt_condition_leak(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "prompts" / "active-decision.md"
            path.write_text(
                path.read_text(encoding="utf-8") + "\nUse the flat-index condition.\n",
                encoding="utf-8",
            )

        errors = self.validate_temporary(mutate)
        self.assertTrue(any("prompt leaks condition name" in error for error in errors))

    def test_rejects_flat_index_status_leak(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "fixtures" / "pilot-01" / "generated" / "flat-index.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# Index\n\nStatus: superseded\n", encoding="utf-8")
            projection = path.with_name("state-projection.json")
            self.write_json(projection, {"records": []})

        errors = self.validate_temporary(mutate, require_generated=True)
        self.assertIn("flat index leaks status", errors)

    def test_rejects_projection_body_copy(self) -> None:
        def mutate(root: Path) -> None:
            generated = root / "fixtures" / "pilot-01" / "generated"
            generated.mkdir(parents=True, exist_ok=True)
            (generated / "flat-index.md").write_text("# Synthetic index\n", encoding="utf-8")
            record = (
                root
                / "fixtures"
                / "pilot-01"
                / "records"
                / "active-decision-a.md"
            ).read_text(encoding="utf-8")
            self.write_json(generated / "state-projection.json", {"copied": record})

        errors = self.validate_temporary(mutate, require_generated=True)
        self.assertIn("projection copies body", errors)

    def test_rejects_missing_expected_source(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "expected" / "answers.json"
            answers = json.loads(path.read_text(encoding="utf-8"))
            answers["active-decision"]["expected_sources"] = ["records/missing.md"]
            self.write_json(path, answers)

        errors = self.validate_temporary(mutate)
        self.assertTrue(any("expected source does not exist" in error for error in errors))

    def test_rejects_private_marker(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "fixtures" / "pilot-01" / "records" / "active-decision-a.md"
            path.write_text(
                path.read_text(encoding="utf-8") + "\n/Users/example/private\n",
                encoding="utf-8",
            )

        errors = self.validate_temporary(mutate)
        self.assertTrue(any("private-data marker" in error for error in errors))

    def test_rejects_missing_task_and_condition(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "fixtures" / "pilot-01" / "manifest.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["task_ids"].pop()
            manifest["condition_ids"].pop()
            self.write_json(path, manifest)

        errors = self.validate_temporary(mutate)
        self.assertTrue(any("exactly 5 task IDs" in error for error in errors))
        self.assertTrue(any("exactly 3 condition IDs" in error for error in errors))

    def test_rejects_rubric_total_mismatch(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "expected" / "rubric.json"
            rubric = json.loads(path.read_text(encoding="utf-8"))
            rubric["formal_max_score"] = 74
            self.write_json(path, rubric)

        errors = self.validate_temporary(mutate)
        self.assertTrue(any("rubric totals are inconsistent" in error for error in errors))

    def test_rejects_wrong_rubric_criterion_set(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "expected" / "rubric.json"
            rubric = json.loads(path.read_text(encoding="utf-8"))
            rubric["tasks"]["active-decision"]["criteria"][0]["id"] = "extra-style"
            self.write_json(path, rubric)

        errors = self.validate_temporary(mutate)
        self.assertTrue(any("five frozen criterion IDs" in error for error in errors))

    def test_require_generated_reports_both_missing_files(self) -> None:
        errors = self.validate_temporary(require_generated=True)
        self.assertIn("missing generated flat index: generated/flat-index.md", errors)
        self.assertIn(
            "missing generated state projection: generated/state-projection.json",
            errors,
        )

    def test_real_committed_fixture_validates(self) -> None:
        self.assertEqual(validate(ROOT), [])


if __name__ == "__main__":
    unittest.main()
