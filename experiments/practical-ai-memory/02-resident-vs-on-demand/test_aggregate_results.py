from __future__ import annotations

import unittest

from aggregate_results import summarize


class AggregateResultsTest(unittest.TestCase):
    def test_summarize_reports_stable_statistics(self) -> None:
        self.assertEqual(
            summarize([1.0, 2.0, 5.0]),
            {"min": 1.0, "median": 2.0, "mean": 2.667, "max": 5.0},
        )


if __name__ == "__main__":
    unittest.main()
