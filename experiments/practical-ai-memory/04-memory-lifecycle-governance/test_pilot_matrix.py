from __future__ import annotations

import unittest
from collections import Counter

from run_pilot_matrix import SCHEDULE


class PilotScheduleTest(unittest.TestCase):
    def test_has_one_run_per_task_condition(self) -> None:
        counts = Counter(
            (task, condition)
            for task, conditions in SCHEDULE
            for condition in conditions
        )
        self.assertEqual(len(counts), 15)
        self.assertEqual(set(counts.values()), {1})

    def test_run_names_are_unique(self) -> None:
        names = [
            f"pilot-01-{task}-{condition}"
            for task, conditions in SCHEDULE
            for condition in conditions
        ]
        self.assertEqual(len(names), len(set(names)))


if __name__ == "__main__":
    unittest.main()
