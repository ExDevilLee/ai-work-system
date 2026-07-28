from __future__ import annotations

import unittest
from argparse import Namespace
from collections import Counter
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

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
                    "run_pilot_matrix.subprocess.run",
                    return_value=CompletedProcess([], 0),
                ),
            ):
                self.assertEqual(main(), 1)


if __name__ == "__main__":
    unittest.main()
