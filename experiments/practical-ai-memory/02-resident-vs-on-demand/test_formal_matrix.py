from __future__ import annotations

import unittest
from collections import Counter

from run_formal_matrix import SCHEDULE


class FormalScheduleTest(unittest.TestCase):
    def test_has_three_runs_per_task_condition(self) -> None:
        counts = Counter(pair for _, runs in SCHEDULE for pair in runs)
        self.assertEqual(len(counts), 12)
        self.assertEqual(set(counts.values()), {3})

    def test_run_names_are_unique(self) -> None:
        names = [
            f"{label}-{task}-{condition}"
            for label, runs in SCHEDULE
            for task, condition in runs
        ]
        self.assertEqual(len(names), 36)
        self.assertEqual(len(names), len(set(names)))


if __name__ == "__main__":
    unittest.main()
