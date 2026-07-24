from __future__ import annotations

import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from matrix_support import is_complete_successful_run
from run_formal_matrix import SCHEDULE


class FormalScheduleTest(unittest.TestCase):
    def test_has_three_runs_per_task_condition(self) -> None:
        counts = Counter(pair for _, runs in SCHEDULE for pair in runs)
        self.assertEqual(len(counts), 15)
        self.assertEqual(set(counts.values()), {3})

    def test_run_names_are_unique(self) -> None:
        names = [
            f"{label}-{task}-{condition}"
            for label, runs in SCHEDULE
            for task, condition in runs
        ]
        self.assertEqual(len(names), 45)
        self.assertEqual(len(names), len(set(names)))

    def test_complete_successful_run_can_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory)
            self.write_complete_run(run_dir, exit_code=0, usage={"input_tokens": 1})

            self.assertTrue(is_complete_successful_run(run_dir))

    def test_failed_run_metadata_cannot_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory)
            self.write_complete_run(run_dir, exit_code=1, usage=None)

            self.assertFalse(is_complete_successful_run(run_dir))

    def test_missing_final_answer_cannot_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory)
            self.write_complete_run(run_dir, exit_code=0, usage={"input_tokens": 1})
            (run_dir / "final.md").unlink()

            self.assertFalse(is_complete_successful_run(run_dir))

    @staticmethod
    def write_complete_run(
        run_dir: Path, *, exit_code: int, usage: object
    ) -> None:
        metadata = {
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
