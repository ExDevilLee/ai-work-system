from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from argparse import Namespace
from collections import Counter
from dataclasses import replace
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from matrix_support import (
    ExpectedRun,
    expected_run_contract,
    is_complete_successful_run,
)
from run_formal_matrix import SCHEDULE, main


TASKS = {
    "active-decision",
    "superseded-rule",
    "unresolved-conflict",
    "scope-boundary",
    "pending-observation",
}
CONDITIONS = {"source-only", "flat-index", "state-projection"}


class FormalScheduleTest(unittest.TestCase):
    EXPECTED = ExpectedRun(
        run_name="formal-01-active-decision-source-only",
        fixture_set="pilot-01",
        task="active-decision",
        condition="source-only",
        platform="macos",
        model="synthetic-model",
        reasoning_effort="medium",
        fixture_sha256=hashlib.sha256().hexdigest(),
        prompt_sha256=hashlib.sha256(b"prompt").hexdigest(),
    )

    def test_has_three_runs_per_task_condition(self) -> None:
        counts = Counter(pair for _, runs in SCHEDULE for pair in runs)
        self.assertEqual(len(counts), 15)
        self.assertEqual(set(counts.values()), {3})
        self.assertEqual({task for task, _ in counts}, TASKS)
        self.assertEqual({condition for _, condition in counts}, CONDITIONS)

    def test_run_names_are_unique(self) -> None:
        names = [
            f"{label}-{task}-{condition}"
            for label, runs in SCHEDULE
            for task, condition in runs
        ]
        self.assertEqual(len(names), 45)
        self.assertEqual(len(names), len(set(names)))

    def test_zero_exit_without_complete_evidence_stops_matrix(self) -> None:
        args = Namespace(
            fixture_set="pilot-01",
            platform_tag="macos",
            model="synthetic-model",
            reasoning_effort="medium",
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            with (
                patch("run_formal_matrix.ROOT", Path(temporary_directory)),
                patch(
                    "run_formal_matrix.SCHEDULE",
                    (("formal-01", (("active-decision", "source-only"),)),),
                ),
                patch("run_formal_matrix.parse_args", return_value=args),
                patch(
                    "run_formal_matrix.expected_run_contract",
                    return_value=self.EXPECTED,
                ),
                patch(
                    "run_formal_matrix.subprocess.run",
                    return_value=CompletedProcess([], 0),
                ),
            ):
                self.assertEqual(main(), 1)

    def test_complete_run_with_wrong_model_is_not_skipped(self) -> None:
        args = Namespace(
            fixture_set="pilot-01",
            platform_tag="macos",
            model="synthetic-model",
            reasoning_effort="medium",
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run_dir = root / "runs/private/macos" / self.EXPECTED.run_name
            run_dir.mkdir(parents=True)
            self.write_complete_run(
                run_dir,
                replace(self.EXPECTED, model="other-model"),
                exit_code=0,
                usage={"input_tokens": 1},
            )
            with (
                patch("run_formal_matrix.ROOT", root),
                patch(
                    "run_formal_matrix.SCHEDULE",
                    (("formal-01", (("active-decision", "source-only"),)),),
                ),
                patch("run_formal_matrix.parse_args", return_value=args),
                patch(
                    "run_formal_matrix.expected_run_contract",
                    return_value=self.EXPECTED,
                ),
                patch("run_formal_matrix.subprocess.run") as run,
            ):
                self.assertEqual(main(), 1)
                run.assert_not_called()

    def test_complete_successful_run_can_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory)
            self.write_complete_run(
                run_dir, self.EXPECTED, exit_code=0, usage={"input_tokens": 1}
            )

            self.assertTrue(is_complete_successful_run(run_dir, self.EXPECTED))

    def test_identity_mismatches_cannot_resume(self) -> None:
        mismatches = {
            "run_name": "formal-99-active-decision-source-only",
            "fixture_set": "pilot-02",
            "task": "superseded-rule",
            "condition": "flat-index",
            "platform": "win11",
            "model": "other-model",
            "reasoning_effort": "high",
            "fixture_sha256": "other-fixture-hash",
            "prompt_sha256": "other-prompt-hash",
        }
        for field, value in mismatches.items():
            with self.subTest(
                field=field
            ), tempfile.TemporaryDirectory() as temporary_directory:
                run_dir = Path(temporary_directory)
                self.write_complete_run(
                    run_dir,
                    replace(self.EXPECTED, **{field: value}),
                    exit_code=0,
                    usage={"input_tokens": 1},
                )
                self.assertFalse(is_complete_successful_run(run_dir, self.EXPECTED))

    def test_evidence_hashes_are_recomputed_from_run_files(self) -> None:
        for relative_path, replacement in (
            ("prompt.md", "changed prompt"),
            ("fixture-snapshot/extra.md", "changed fixture"),
        ):
            with self.subTest(
                relative_path=relative_path
            ), tempfile.TemporaryDirectory() as temporary_directory:
                parent = Path(temporary_directory)
                run_dir = parent / self.EXPECTED.run_name
                run_dir.mkdir()
                self.write_complete_run(
                    run_dir,
                    self.EXPECTED,
                    exit_code=0,
                    usage={"input_tokens": 1},
                )
                target = run_dir / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(replacement, encoding="utf-8")
                self.assertFalse(is_complete_successful_run(run_dir, self.EXPECTED))

    def test_non_object_metadata_cannot_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory)
            self.write_complete_run(
                run_dir, self.EXPECTED, exit_code=0, usage={"input_tokens": 1}
            )
            (run_dir / "metadata.json").write_text("[]\n", encoding="utf-8")

            self.assertFalse(is_complete_successful_run(run_dir, self.EXPECTED))

    def test_expected_contract_hashes_current_frozen_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fixture_root = root / "fixtures/pilot-01"
            (fixture_root / "records").mkdir(parents=True)
            record = fixture_root / "records/item.md"
            record.write_text("record one\n", encoding="utf-8")
            condition_root = fixture_root / "conditions/source-only"
            condition_root.mkdir(parents=True)
            (condition_root / "AGENTS.md").write_text(
                "# Instructions\n", encoding="utf-8"
            )
            (root / "prompts").mkdir()
            prompt = root / "prompts/active-decision.md"
            prompt.write_text("prompt one\n", encoding="utf-8")

            first = expected_run_contract(
                root,
                run_name=self.EXPECTED.run_name,
                fixture_set="pilot-01",
                task="active-decision",
                condition="source-only",
                platform="macos",
                model="synthetic-model",
                reasoning_effort="medium",
            )
            prompt.write_text("prompt two\n", encoding="utf-8")
            record.write_text("record two\n", encoding="utf-8")
            second = expected_run_contract(
                root,
                run_name=self.EXPECTED.run_name,
                fixture_set="pilot-01",
                task="active-decision",
                condition="source-only",
                platform="macos",
                model="synthetic-model",
                reasoning_effort="medium",
            )

            self.assertNotEqual(first.prompt_sha256, second.prompt_sha256)
            self.assertNotEqual(first.fixture_sha256, second.fixture_sha256)

    def test_failed_run_metadata_cannot_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory)
            self.write_complete_run(run_dir, self.EXPECTED, exit_code=1, usage=None)

            self.assertFalse(is_complete_successful_run(run_dir, self.EXPECTED))

    def test_missing_final_answer_cannot_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory)
            self.write_complete_run(
                run_dir, self.EXPECTED, exit_code=0, usage={"input_tokens": 1}
            )
            (run_dir / "final.md").unlink()

            self.assertFalse(is_complete_successful_run(run_dir, self.EXPECTED))

    def test_empty_final_answer_cannot_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory)
            self.write_complete_run(
                run_dir, self.EXPECTED, exit_code=0, usage={"input_tokens": 1}
            )
            (run_dir / "final.md").write_text(" \n", encoding="utf-8")

            self.assertFalse(is_complete_successful_run(run_dir, self.EXPECTED))

    def test_failed_protocol_gates_cannot_resume(self) -> None:
        for failed_key in (
            "protocol_environment_isolated",
            "workspace_metric_coverage_complete",
            "workspace_output_bytes_reliable",
        ):
            with self.subTest(
                failed_key=failed_key
            ), tempfile.TemporaryDirectory() as temporary_directory:
                run_dir = Path(temporary_directory)
                self.write_complete_run(
                    run_dir, self.EXPECTED, exit_code=0, usage={"input_tokens": 1}
                )
                metadata_path = run_dir / "metadata.json"
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                metadata[failed_key] = False
                metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

                self.assertFalse(is_complete_successful_run(run_dir, self.EXPECTED))

    @staticmethod
    def write_complete_run(
        run_dir: Path,
        identity: ExpectedRun,
        *,
        exit_code: int,
        usage: object,
    ) -> None:
        metadata = {
            "run_name": identity.run_name,
            "fixture_set": identity.fixture_set,
            "task": identity.task,
            "condition": identity.condition,
            "platform_tag": identity.platform,
            "requested_model": identity.model,
            "reasoning_effort": identity.reasoning_effort,
            "fixture_sha256": identity.fixture_sha256,
            "prompt_sha256": identity.prompt_sha256,
            "exit_code": exit_code,
            "usage": usage,
            "protocol_environment_isolated": True,
            "workspace_metric_coverage_complete": True,
            "workspace_output_bytes_reliable": True,
        }
        (run_dir / "metadata.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )
        (run_dir / "final.md").write_text("answer", encoding="utf-8")
        (run_dir / "raw.jsonl").write_text("event", encoding="utf-8")
        (run_dir / "stderr.log").write_text("", encoding="utf-8")
        (run_dir / "prompt.md").write_text("prompt", encoding="utf-8")
        (run_dir / "fixture-snapshot").mkdir()


if __name__ == "__main__":
    unittest.main()
