from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from score_run import main


class ScoreRunTest(unittest.TestCase):
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

    def args(self, run_dir: Path) -> list[str]:
        return [
            "score_run.py",
            str(run_dir),
            "--score",
            "5",
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
            self.assertEqual(score["manual_review_minutes"], 0.25)
            self.assertEqual(score["review_batch_size"], 45)
            self.assertNotIn("provider", json.dumps(score).lower())


if __name__ == "__main__":
    unittest.main()
