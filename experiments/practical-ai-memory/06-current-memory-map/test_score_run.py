from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import patch

from score_run import main


class ScoreRunTest(unittest.TestCase):
    CRITERIA = (
        "correct-fact-state",
        "correct-current-action",
        "correct-boundary",
        "no-prohibited-conclusion",
        "correct-source-citation",
    )

    def make_run(self, root: Path, task: str = "active-decision") -> Path:
        run_dir = root / "formal-01-active-decision-source-only"
        run_dir.mkdir()
        metadata = {
            "run_name": run_dir.name,
            "task": task,
            "condition": "source-only",
            "purpose": "formal run",
        }
        (run_dir / "metadata.json").write_text(
            json.dumps(metadata) + "\n", encoding="utf-8"
        )
        return run_dir

    def write_criterion_scores(
        self, run_dir: Path, items: Optional[list[dict[str, object]]] = None
    ) -> Path:
        path = run_dir / "criterion-scores.json"
        if items is None:
            items = [
                {"criterion_id": criterion_id, "score": 1}
                for criterion_id in self.CRITERIA
            ]
        path.write_text(json.dumps(items) + "\n", encoding="utf-8")
        return path

    def args(
        self, run_dir: Path, items: Optional[list[dict[str, object]]] = None
    ) -> list[str]:
        criterion_path = self.write_criterion_scores(run_dir, items)
        return [
            "score_run.py",
            str(run_dir),
            "--score",
            "5",
            "--criterion-scores",
            str(criterion_path),
            "--protocol-valid",
            "no",
            "--unsupported-claims",
            "2",
            "--irrelevant-facts",
            "1",
            "--notes",
            "reviewed",
        ]

    def test_requires_real_review_minutes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self.make_run(Path(temporary))
            with patch("sys.argv", self.args(run_dir)):
                with self.assertRaisesRegex(SystemExit, "positive review-minutes"):
                    main()

            with patch(
                "sys.argv", self.args(run_dir) + ["--review-minutes", "0"]
            ):
                with self.assertRaisesRegex(SystemExit, "positive review-minutes"):
                    main()

            with patch(
                "sys.argv", self.args(run_dir) + ["--review-minutes", "nan"]
            ):
                with self.assertRaisesRegex(SystemExit, "positive review-minutes"):
                    main()

    def test_rejects_score_above_task_max(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self.make_run(Path(temporary))
            args = self.args(run_dir)
            args[args.index("5")] = "6"
            args += ["--review-minutes", "0.25"]
            with patch("sys.argv", args):
                with self.assertRaisesRegex(SystemExit, "task maximum"):
                    main()

    def test_preserves_protocol_and_claim_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self.make_run(Path(temporary))
            args = self.args(run_dir) + [
                "--review-minutes",
                "0.25",
                "--review-time-method",
                "batch_average",
                "--review-batch-size",
                "45",
            ]
            with patch("sys.argv", args):
                self.assertEqual(main(), 0)

            score = json.loads((run_dir / "score.json").read_text(encoding="utf-8"))
            self.assertFalse(score["protocol_valid"])
            self.assertEqual(score["unsupported_claims"], 2)
            self.assertEqual(score["irrelevant_facts"], 1)
            self.assertEqual(score["correctness_max"], 5)
            self.assertEqual(
                [item["criterion_id"] for item in score["rubric_items"]],
                list(self.CRITERIA),
            )
            self.assertTrue(all(item["passed"] for item in score["rubric_items"]))
            self.assertEqual(
                sum(item["score"] for item in score["rubric_items"]),
                score["correctness_score"],
            )
            self.assertEqual(score["manual_review_minutes"], 0.25)
            self.assertEqual(score["review_batch_size"], 45)
            self.assertNotIn("provider", json.dumps(score).lower())

    def test_rejects_incomplete_unknown_duplicate_or_reordered_criteria(self) -> None:
        valid = [
            {"criterion_id": criterion_id, "score": 1}
            for criterion_id in self.CRITERIA
        ]
        cases = {
            "missing": valid[:-1],
            "extra": valid + [{"criterion_id": "unknown", "score": 0}],
            "unknown": [{**valid[0], "criterion_id": "unknown"}] + valid[1:],
            "duplicate": [valid[0], valid[0]] + valid[2:],
            "reordered": [valid[1], valid[0]] + valid[2:],
            "unhashable-id": [{**valid[0], "criterion_id": ["bad"]}] + valid[1:],
        }
        for name, items in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                run_dir = self.make_run(Path(temporary))
                args = self.args(run_dir, items) + ["--review-minutes", "0.25"]
                with patch("sys.argv", args):
                    with self.assertRaisesRegex(SystemExit, "criterion IDs"):
                        main()

    def test_rejects_item_range_shape_and_total_mismatch(self) -> None:
        valid = [
            {"criterion_id": criterion_id, "score": 1}
            for criterion_id in self.CRITERIA
        ]
        cases = {
            "above-range": [{**valid[0], "score": 2}] + valid[1:],
            "negative": [{**valid[0], "score": -1}] + valid[1:],
            "extra-field": [{**valid[0], "passed": True}] + valid[1:],
            "total-mismatch": [{**valid[0], "score": 0}] + valid[1:],
        }
        for name, items in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                run_dir = self.make_run(Path(temporary))
                args = self.args(run_dir, items) + ["--review-minutes", "0.25"]
                with patch("sys.argv", args):
                    with self.assertRaisesRegex(SystemExit, "criterion score|criterion-scores"):
                        main()


if __name__ == "__main__":
    unittest.main()
