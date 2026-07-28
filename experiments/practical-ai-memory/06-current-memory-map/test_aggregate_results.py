from __future__ import annotations

import csv
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aggregate_results import aggregate_runs, summarize
from matrix_support import expected_run_contract
from run_experiment import assemble_fixture


TASKS = (
    "active-decision",
    "superseded-rule",
    "unresolved-conflict",
    "scope-boundary",
    "pending-observation",
)
CONDITIONS = ("source-only", "flat-index", "state-projection")
RUBRIC = json.loads(
    (Path(__file__).resolve().parent / "expected" / "rubric.json").read_text(
        encoding="utf-8"
    )
)
SOURCE_ROOT = Path(__file__).resolve().parent


class AggregateResultsTest(unittest.TestCase):
    def rubric_items(self, task: str) -> list[dict[str, object]]:
        return [
            {
                "criterion_id": criterion["id"],
                "score": criterion["points"],
                "max_score": criterion["points"],
                "passed": True,
            }
            for criterion in RUBRIC["tasks"][task]["criteria"]
        ]

    def make_matrix(self, root: Path) -> Path:
        shutil.copytree(
            SOURCE_ROOT / "fixtures" / "pilot-01",
            root / "fixtures" / "pilot-01",
        )
        shutil.copytree(SOURCE_ROOT / "prompts", root / "prompts")
        private = root / "runs" / "private" / "macos"
        for repeat in range(1, 4):
            for task in TASKS:
                for condition in CONDITIONS:
                    run_name = f"formal-{repeat:02d}-{task}-{condition}"
                    run_dir = private / run_name
                    run_dir.mkdir(parents=True)
                    expected = expected_run_contract(
                        root,
                        run_name=run_name,
                        fixture_set="pilot-01",
                        task=task,
                        condition=condition,
                        platform="macos",
                        model="gpt-test",
                        reasoning_effort="medium",
                    )
                    assemble_fixture(
                        root / "fixtures" / "pilot-01",
                        condition,
                        run_dir / "fixture-snapshot",
                    )
                    shutil.copy2(
                        root / "prompts" / f"{task}.md", run_dir / "prompt.md"
                    )
                    (run_dir / "final.md").write_text("complete answer\n", encoding="utf-8")
                    (run_dir / "raw.jsonl").write_text("{}\n", encoding="utf-8")
                    (run_dir / "stderr.log").write_text("", encoding="utf-8")
                    metadata = {
                        "run_name": run_name,
                        "purpose": "formal run",
                        "task": task,
                        "condition": condition,
                        "fixture_set": "pilot-01",
                        "platform_tag": "macos",
                        "requested_model": "gpt-test",
                        "reasoning_effort": "medium",
                        "codex_version": "codex-cli 1.2.3",
                        "fixture_sha256": expected.fixture_sha256,
                        "prompt_sha256": expected.prompt_sha256,
                        "exit_code": 0,
                        "protocol_environment_isolated": True,
                        "resident_instruction_bytes": 100,
                        "project_context_bytes": 600,
                        "workspace_command_calls": 2,
                        "workspace_output_bytes": 500,
                        "workspace_metric_coverage_complete": True,
                        "workspace_output_bytes_reliable": True,
                        "elapsed_seconds": 2.5,
                        "usage": {
                            "input_tokens": 1000,
                            "cached_input_tokens": 100,
                            "output_tokens": 200,
                            "reasoning_output_tokens": 50,
                        },
                    }
                    score = {
                        "run_name": run_name,
                        "task": task,
                        "condition": condition,
                        "fixture_set": "pilot-01",
                        "platform_tag": "macos",
                        "requested_model": "gpt-test",
                        "reasoning_effort": "medium",
                        "fixture_sha256": expected.fixture_sha256,
                        "prompt_sha256": expected.prompt_sha256,
                        "correctness_score": 5,
                        "correctness_max": 5,
                        "rubric_items": self.rubric_items(task),
                        "protocol_valid": True,
                        "unsupported_claims": 0,
                        "irrelevant_facts": 0,
                        "manual_review_minutes": 0.1,
                        "review_time_method": "batch_average",
                        "review_batch_size": 45,
                    }
                    (run_dir / "metadata.json").write_text(
                        json.dumps(metadata) + "\n", encoding="utf-8"
                    )
                    (run_dir / "score.json").write_text(
                        json.dumps(score) + "\n", encoding="utf-8"
                    )
        return private

    def aggregate(self, root: Path) -> tuple[Path, Path]:
        return aggregate_runs(
            root=root,
            prefix="formal-",
            platform_tag="macos",
            model="gpt-test",
            reasoning_effort="medium",
            output_stem="formal-macos-gpt-test-medium",
        )

    def test_summarize_reports_stable_statistics(self) -> None:
        self.assertEqual(
            summarize([1.0, 2.0, 5.0]),
            {"min": 1.0, "median": 2.0, "mean": 2.667, "max": 5.0},
        )

    def test_creates_fifteen_groups_of_three(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_matrix(root)
            csv_path, json_path = self.aggregate(root)

            summary = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["run_count"], 45)
            self.assertEqual(len(summary["groups"]), 15)
            for group in summary["groups"].values():
                self.assertEqual(group["n"], 3)
                self.assertEqual(group["workspace_metrics_n"], 3)
                self.assertEqual(group["correctness"], {"score": 15, "max_score": 15})
            self.assertEqual(summary["platform_tag"], "macos")
            self.assertEqual(summary["model_configuration"], {
                "model": "gpt-test",
                "reasoning_effort": "medium",
                "codex_version": "codex-cli 1.2.3",
            })
            self.assertNotIn(b"\r\n", csv_path.read_bytes())
            rows = list(csv.DictReader(io.StringIO(csv_path.read_text(encoding="utf-8"))))
            self.assertEqual(len(rows), 45)

    def test_rejects_incomplete_workspace_metric_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = self.make_matrix(root)
            run_dir = private / "formal-01-active-decision-source-only"
            metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
            metadata["workspace_metric_coverage_complete"] = False
            metadata["workspace_output_bytes_reliable"] = False
            (run_dir / "metadata.json").write_text(json.dumps(metadata) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "complete and successful"):
                self.aggregate(root)

    def test_does_not_mix_model_effort_platform_or_cli(self) -> None:
        fields = (
            ("requested_model", "gpt-other"),
            ("reasoning_effort", "high"),
            ("platform_tag", "win11"),
            ("codex_version", "codex-cli 9.9.9"),
        )
        for field, value in fields:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                private = self.make_matrix(root)
                run_dir = private / "formal-01-active-decision-source-only"
                metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
                metadata[field] = value
                (run_dir / "metadata.json").write_text(json.dumps(metadata) + "\n", encoding="utf-8")
                with self.assertRaisesRegex(
                    SystemExit, "complete and successful|requested batch|mixed batch"
                ):
                    self.aggregate(root)

    def test_private_fields_cannot_enter_public_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = self.make_matrix(root)
            run_dir = private / "formal-01-active-decision-source-only"
            metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
            metadata.update({
                "provider": "forbidden-provider",
                "thread_id": "thread-secret",
                "user_name": "private-user",
                "raw_path": "/Users/private-user/secret",
            })
            (run_dir / "metadata.json").write_text(json.dumps(metadata) + "\n", encoding="utf-8")

            csv_path, json_path = self.aggregate(root)
            public_text = csv_path.read_text(encoding="utf-8") + json_path.read_text(encoding="utf-8")
            for forbidden in ("provider", "thread-secret", "private-user", "/Users/"):
                self.assertNotIn(forbidden, public_text)

    def test_rejects_non_finite_metrics_and_fractional_claim_counts(self) -> None:
        mutations = (
            ("metadata", "elapsed_seconds", float("nan")),
            ("score", "unsupported_claims", 0.5),
        )
        for target, field, value in mutations:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                private = self.make_matrix(root)
                run_dir = private / "formal-01-active-decision-source-only"
                path = run_dir / f"{target}.json"
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload[field] = value
                path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
                with self.assertRaisesRegex(SystemExit, "finite|integer"):
                    self.aggregate(root)

    @unittest.skipIf(os.name == "nt", "symlink creation requires extra Windows privileges")
    def test_rejects_symlinked_private_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = self.make_matrix(root)
            run_dir = private / "formal-01-active-decision-source-only"
            metadata = run_dir / "metadata.json"
            target = root / "external-metadata.json"
            target.write_bytes(metadata.read_bytes())
            metadata.unlink()
            metadata.symlink_to(target)
            with self.assertRaisesRegex(SystemExit, "complete and successful"):
                self.aggregate(root)

    def test_rejects_metadata_score_shell_and_hash_drift(self) -> None:
        mutations = ("remove-evidence", "change-prompt")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                private = self.make_matrix(root)
                run_dir = private / "formal-01-active-decision-source-only"
                if mutation == "remove-evidence":
                    for name in (
                        "final.md",
                        "raw.jsonl",
                        "prompt.md",
                        "stderr.log",
                    ):
                        (run_dir / name).unlink()
                    shutil.rmtree(run_dir / "fixture-snapshot")
                else:
                    (run_dir / "prompt.md").write_text("drift\n", encoding="utf-8")
                with self.assertRaisesRegex(SystemExit, "complete and successful"):
                    self.aggregate(root)

    def test_score_identity_must_match_the_same_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = self.make_matrix(root)
            run_dir = private / "formal-01-active-decision-source-only"
            score_path = run_dir / "score.json"
            original = json.loads(score_path.read_text(encoding="utf-8"))
            for field, value in (
                ("run_name", "formal-02-active-decision-source-only"),
                ("task", "pending-observation"),
                ("condition", "flat-index"),
                ("fixture_set", "pilot-02"),
                ("platform_tag", "win11"),
                ("requested_model", "gpt-other"),
                ("reasoning_effort", "high"),
                ("fixture_sha256", "0" * 64),
                ("prompt_sha256", "1" * 64),
            ):
                with self.subTest(field=field):
                    score = dict(original)
                    score[field] = value
                    score_path.write_text(json.dumps(score) + "\n", encoding="utf-8")
                    with self.assertRaisesRegex(SystemExit, "score identity"):
                        self.aggregate(root)
            score_path.write_text(json.dumps(original) + "\n", encoding="utf-8")

    def test_independently_rejects_tampered_saved_rubric_items(self) -> None:
        def missing(score: dict[str, object]) -> None:
            score["rubric_items"] = score["rubric_items"][:-1]  # type: ignore[index]

        def duplicate(score: dict[str, object]) -> None:
            items = score["rubric_items"]  # type: ignore[assignment]
            items[1] = dict(items[0])  # type: ignore[index]

        def reordered(score: dict[str, object]) -> None:
            items = score["rubric_items"]  # type: ignore[assignment]
            items[0], items[1] = items[1], items[0]  # type: ignore[index]

        def range_error(score: dict[str, object]) -> None:
            score["rubric_items"][0]["score"] = 2  # type: ignore[index]

        def total_mismatch(score: dict[str, object]) -> None:
            score["rubric_items"][0]["score"] = 0  # type: ignore[index]
            score["rubric_items"][0]["passed"] = False  # type: ignore[index]

        def max_mismatch(score: dict[str, object]) -> None:
            score["rubric_items"][0]["max_score"] = 2  # type: ignore[index]

        def passed_mismatch(score: dict[str, object]) -> None:
            score["rubric_items"][0]["passed"] = False  # type: ignore[index]

        def unhashable_id(score: dict[str, object]) -> None:
            score["rubric_items"][0]["criterion_id"] = ["bad"]  # type: ignore[index]

        mutations = (
            missing,
            duplicate,
            reordered,
            range_error,
            total_mismatch,
            max_mismatch,
            passed_mismatch,
            unhashable_id,
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate.__name__), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                private = self.make_matrix(root)
                run_dir = private / "formal-01-active-decision-source-only"
                score_path = run_dir / "score.json"
                score = json.loads(score_path.read_text(encoding="utf-8"))
                mutate(score)
                score_path.write_text(json.dumps(score) + "\n", encoding="utf-8")
                with self.assertRaisesRegex(SystemExit, "rubric"):
                    self.aggregate(root)

    def test_discrete_metrics_require_nonnegative_integers(self) -> None:
        mutations = (
            ("metadata", "workspace_command_calls", 2.0),
            ("metadata", "workspace_output_bytes", True),
            ("metadata", "resident_instruction_bytes", 100.5),
            ("score", "unsupported_claims", 0.5),
            ("score", "irrelevant_facts", True),
        )
        for target, field, value in mutations:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                private = self.make_matrix(root)
                run_dir = private / "formal-01-active-decision-source-only"
                path = run_dir / f"{target}.json"
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload[field] = value
                path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
                with self.assertRaisesRegex(SystemExit, "integer"):
                    self.aggregate(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = self.make_matrix(root)
            run_dir = private / "formal-01-active-decision-source-only"
            metadata_path = run_dir / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["usage"]["input_tokens"] = 1000.0
            metadata_path.write_text(json.dumps(metadata) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "integer"):
                self.aggregate(root)

    def test_aggregate_pair_rolls_back_old_and_absent_outputs(self) -> None:
        for existing in (True, False):
            with self.subTest(existing=existing), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.make_matrix(root)
                data = root / "data"
                data.mkdir()
                csv_path = data / "formal-macos-gpt-test-medium.csv"
                json_path = data / "formal-macos-gpt-test-medium.json"
                if existing:
                    csv_path.write_bytes(b"old-csv\n")
                    json_path.write_bytes(b"old-json\n")
                real_replace = os.replace
                failed = False

                def fail_second_install(source: object, destination: object) -> None:
                    nonlocal failed
                    source_path = Path(source)
                    if (
                        not failed
                        and Path(destination) == json_path
                        and source_path.name.startswith(".aggregate-json-")
                    ):
                        failed = True
                        raise OSError("injected replace failure")
                    real_replace(source, destination)

                with patch("aggregate_results.os.replace", side_effect=fail_second_install):
                    with self.assertRaisesRegex(SystemExit, "transaction failed"):
                        self.aggregate(root)
                if existing:
                    self.assertEqual(csv_path.read_bytes(), b"old-csv\n")
                    self.assertEqual(json_path.read_bytes(), b"old-json\n")
                else:
                    self.assertFalse(csv_path.exists())
                    self.assertFalse(json_path.exists())
                leftovers = [
                    path.name
                    for path in data.iterdir()
                    if path.name.startswith(".aggregate-")
                ]
                self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
