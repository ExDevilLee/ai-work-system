from __future__ import annotations

import csv
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from aggregate_results import aggregate_runs, summarize


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
        private = root / "runs" / "private" / "macos"
        for repeat in range(1, 4):
            for task in TASKS:
                for condition in CONDITIONS:
                    run_name = f"formal-{repeat:02d}-{task}-{condition}"
                    run_dir = private / run_name
                    run_dir.mkdir(parents=True)
                    metadata = {
                        "run_name": run_name,
                        "purpose": "formal run",
                        "task": task,
                        "condition": condition,
                        "platform_tag": "macos",
                        "requested_model": "gpt-test",
                        "reasoning_effort": "medium",
                        "codex_version": "codex-cli 1.2.3",
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

    def test_requires_workspace_metrics_n(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = self.make_matrix(root)
            run_dir = private / "formal-01-active-decision-source-only"
            metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
            metadata["workspace_metric_coverage_complete"] = False
            metadata["workspace_output_bytes_reliable"] = False
            (run_dir / "metadata.json").write_text(json.dumps(metadata) + "\n", encoding="utf-8")

            _, json_path = self.aggregate(root)
            summary = json.loads(json_path.read_text(encoding="utf-8"))
            group = summary["groups"]["active-decision:source-only"]
            self.assertEqual(group["n"], 3)
            self.assertEqual(group["workspace_metrics_n"], 2)

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
                with self.assertRaisesRegex(SystemExit, "mixed batch|platform"):
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
            with self.assertRaisesRegex(SystemExit, "regular file"):
                self.aggregate(root)

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


if __name__ == "__main__":
    unittest.main()
