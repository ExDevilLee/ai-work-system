from __future__ import annotations

import hashlib
import json
import unittest
from argparse import Namespace
from collections import Counter
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest.mock import patch

from matrix_support import ExpectedRun
from run_pilot_matrix import SCHEDULE, main


TASKS = {
    "active-decision",
    "superseded-rule",
    "unresolved-conflict",
    "scope-boundary",
    "pending-observation",
}
CONDITIONS = {"source-only", "flat-index", "state-projection"}


class PilotScheduleTest(unittest.TestCase):
    def test_has_one_run_per_task_condition(self) -> None:
        counts = Counter(
            (task, condition)
            for task, conditions in SCHEDULE
            for condition in conditions
        )
        self.assertEqual(len(counts), 15)
        self.assertEqual(set(counts.values()), {1})
        self.assertEqual({task for task, _ in counts}, TASKS)
        self.assertEqual({condition for _, condition in counts}, CONDITIONS)

    def test_run_names_are_unique(self) -> None:
        names = [
            f"pilot-01-{task}-{condition}"
            for task, conditions in SCHEDULE
            for condition in conditions
        ]
        self.assertEqual(len(names), len(set(names)))

    def test_zero_exit_without_complete_evidence_stops_matrix(self) -> None:
        args = Namespace(
            label="pilot-01",
            fixture_set="pilot-01",
            platform_tag="macos",
            model="synthetic-model",
            reasoning_effort="medium",
        )
        with TemporaryDirectory() as temporary_directory:
            with (
                patch("run_pilot_matrix.ROOT", Path(temporary_directory)),
                patch(
                    "run_pilot_matrix.SCHEDULE",
                    (("active-decision", ("source-only",)),),
                ),
                patch("run_pilot_matrix.parse_args", return_value=args),
                patch(
                    "run_pilot_matrix.expected_run_contract",
                    return_value=ExpectedRun(
                        run_name="pilot-01-active-decision-source-only",
                        fixture_set="pilot-01",
                        task="active-decision",
                        condition="source-only",
                        platform="macos",
                        model="synthetic-model",
                        reasoning_effort="medium",
                        fixture_sha256=hashlib.sha256().hexdigest(),
                        prompt_sha256=hashlib.sha256(b"prompt").hexdigest(),
                    ),
                ),
                patch(
                    "run_pilot_matrix.subprocess.run",
                    return_value=CompletedProcess([], 0),
                ),
            ):
                self.assertEqual(main(), 1)

    def test_complete_run_with_wrong_condition_is_not_skipped(self) -> None:
        args = Namespace(
            label="pilot-01",
            fixture_set="pilot-01",
            platform_tag="macos",
            model="synthetic-model",
            reasoning_effort="medium",
        )
        expected = ExpectedRun(
            run_name="pilot-01-active-decision-source-only",
            fixture_set="pilot-01",
            task="active-decision",
            condition="source-only",
            platform="macos",
            model="synthetic-model",
            reasoning_effort="medium",
            fixture_sha256=hashlib.sha256().hexdigest(),
            prompt_sha256=hashlib.sha256(b"prompt").hexdigest(),
        )
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run_dir = root / "runs/private/macos" / expected.run_name
            run_dir.mkdir(parents=True)
            metadata = {
                "run_name": expected.run_name,
                "fixture_set": expected.fixture_set,
                "task": expected.task,
                "condition": "flat-index",
                "platform_tag": expected.platform,
                "requested_model": expected.model,
                "reasoning_effort": expected.reasoning_effort,
                "fixture_sha256": expected.fixture_sha256,
                "prompt_sha256": expected.prompt_sha256,
                "exit_code": 0,
                "usage": {"input_tokens": 1},
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

            with (
                patch("run_pilot_matrix.ROOT", root),
                patch(
                    "run_pilot_matrix.SCHEDULE",
                    (("active-decision", ("source-only",)),),
                ),
                patch("run_pilot_matrix.parse_args", return_value=args),
                patch(
                    "run_pilot_matrix.expected_run_contract",
                    return_value=expected,
                ),
                patch("run_pilot_matrix.subprocess.run") as run,
            ):
                self.assertEqual(main(), 1)
                run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
