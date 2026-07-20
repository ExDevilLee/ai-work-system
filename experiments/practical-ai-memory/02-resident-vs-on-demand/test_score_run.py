from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from score_run import main


class ScoreRunTest(unittest.TestCase):
    def make_run(self, root: Path, purpose: str) -> Path:
        run_dir = root / "run"
        run_dir.mkdir()
        metadata = {
            "run_name": "example",
            "task": "critical-boundary",
            "condition": "index-only",
            "purpose": purpose,
        }
        (run_dir / "metadata.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )
        return run_dir

    def base_args(self, run_dir: Path) -> list[str]:
        return [
            "score_run.py",
            str(run_dir),
            "--score",
            "6",
            "--max-score",
            "6",
            "--protocol-valid",
            "yes",
            "--notes",
            "reviewed",
        ]

    def test_pilot_can_record_unmeasured_review_time(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = self.make_run(Path(temporary_directory), "protocol pilot")
            with patch("sys.argv", self.base_args(run_dir)):
                self.assertEqual(main(), 0)

            score = json.loads((run_dir / "score.json").read_text(encoding="utf-8"))
            self.assertIsNone(score["manual_review_minutes"])
            self.assertEqual(score["review_time_status"], "not individually timed")

    def test_formal_run_requires_review_time(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = self.make_run(Path(temporary_directory), "formal run")
            with patch("sys.argv", self.base_args(run_dir)):
                with self.assertRaisesRegex(SystemExit, "review-minutes"):
                    main()


if __name__ == "__main__":
    unittest.main()
