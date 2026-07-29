from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import patch

from matrix_support import expected_run_contract
from run_experiment import assemble_fixture
import score_run as score_run_module
from score_run import atomic_write_score, main


SOURCE_ROOT = Path(__file__).resolve().parent


class ScoreRunTest(unittest.TestCase):
    CRITERIA = (
        "correct-fact-state",
        "correct-current-action",
        "correct-boundary",
        "no-prohibited-conclusion",
        "correct-source-citation",
    )

    def make_run(self, root: Path) -> Path:
        task = "active-decision"
        condition = "source-only"
        run_name = "formal-01-active-decision-source-only"
        shutil.copytree(
            SOURCE_ROOT / "fixtures" / "pilot-01",
            root / "fixtures" / "pilot-01",
        )
        shutil.copytree(SOURCE_ROOT / "prompts", root / "prompts")
        run_dir = root / "runs" / "private" / "macos" / run_name
        run_dir.mkdir(parents=True)
        expected = expected_run_contract(
            root,
            run_name=run_name,
            fixture_set="pilot-01",
            task=task,
            condition=condition,
            platform="macos",
            model="gpt-test",
            reasoning_effort="medium",
        )
        assemble_fixture(
            root / "fixtures" / "pilot-01",
            condition,
            run_dir / "fixture-snapshot",
        )
        shutil.copy2(root / "prompts" / f"{task}.md", run_dir / "prompt.md")
        (run_dir / "final.md").write_text("complete answer\n", encoding="utf-8")
        (run_dir / "raw.jsonl").write_text("{}\n", encoding="utf-8")
        (run_dir / "stderr.log").write_text("", encoding="utf-8")
        metadata = {
            "run_name": run_name,
            "task": task,
            "condition": condition,
            "purpose": "formal run",
            "fixture_set": "pilot-01",
            "platform_tag": "macos",
            "requested_model": "gpt-test",
            "reasoning_effort": "medium",
            "fixture_sha256": expected.fixture_sha256,
            "prompt_sha256": expected.prompt_sha256,
            "exit_code": 0,
            "usage": {},
            "protocol_environment_isolated": True,
            "workspace_metric_coverage_complete": True,
            "workspace_output_bytes_reliable": True,
        }
        (run_dir / "metadata.json").write_text(
            json.dumps(metadata) + "\n", encoding="utf-8"
        )
        return run_dir

    def invoke(self, root: Path, args: list[str]) -> int:
        with patch("score_run.ROOT", root), patch("sys.argv", args):
            return main()

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
            with self.assertRaisesRegex(SystemExit, "positive review-minutes"):
                self.invoke(Path(temporary), self.args(run_dir))

            with self.assertRaisesRegex(SystemExit, "positive review-minutes"):
                self.invoke(
                    Path(temporary),
                    self.args(run_dir) + ["--review-minutes", "0"],
                )

            with self.assertRaisesRegex(SystemExit, "positive review-minutes"):
                self.invoke(
                    Path(temporary),
                    self.args(run_dir) + ["--review-minutes", "nan"],
                )

    def test_rejects_score_above_task_max(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self.make_run(Path(temporary))
            args = self.args(run_dir)
            args[args.index("5")] = "6"
            args += ["--review-minutes", "0.25"]
            with self.assertRaisesRegex(SystemExit, "task maximum"):
                self.invoke(Path(temporary), args)

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
            self.assertEqual(self.invoke(Path(temporary), args), 0)

            score = json.loads((run_dir / "score.json").read_text(encoding="utf-8"))
            self.assertFalse(score["protocol_valid"])
            self.assertEqual(score["unsupported_claims"], 2)
            self.assertEqual(score["irrelevant_facts"], 1)
            self.assertEqual(score["correctness_max"], 5)
            self.assertEqual(score["fixture_set"], "pilot-01")
            self.assertEqual(score["platform_tag"], "macos")
            self.assertEqual(score["requested_model"], "gpt-test")
            self.assertEqual(score["reasoning_effort"], "medium")
            metadata = json.loads(
                (run_dir / "metadata.json").read_text(encoding="utf-8")
            )
            self.assertEqual(score["fixture_sha256"], metadata["fixture_sha256"])
            self.assertEqual(score["prompt_sha256"], metadata["prompt_sha256"])
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
                with self.assertRaisesRegex(SystemExit, "criterion IDs"):
                    self.invoke(Path(temporary), args)

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
                with self.assertRaisesRegex(SystemExit, "criterion score|criterion-scores"):
                    self.invoke(Path(temporary), args)

    def test_rejects_metadata_score_shell(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = self.make_run(root)
            for name in ("final.md", "raw.jsonl", "prompt.md", "stderr.log"):
                (run_dir / name).unlink()
            shutil.rmtree(run_dir / "fixture-snapshot")
            args = self.args(run_dir) + ["--review-minutes", "0.25"]
            with self.assertRaisesRegex(SystemExit, "complete and successful"):
                self.invoke(root, args)

    @unittest.skipIf(os.name == "nt", "symlink creation requires extra Windows privileges")
    def test_rejects_outside_path_symlink_ancestor_and_unsafe_score_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "root"
            root.mkdir()
            outside = Path(temporary) / "outside"
            outside.mkdir()
            with self.assertRaisesRegex(SystemExit, "outside the private evidence root") as caught:
                self.invoke(root, self.args(outside) + ["--review-minutes", "0.25"])
            self.assertNotIn(str(temporary), str(caught.exception))

        for target_kind in ("symlink", "directory"):
            with self.subTest(target_kind=target_kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                run_dir = self.make_run(root)
                score_target = run_dir / "score.json"
                if target_kind == "symlink":
                    external = root / "external-score.json"
                    external.write_text("old\n", encoding="utf-8")
                    score_target.symlink_to(external)
                else:
                    score_target.mkdir()
                args = self.args(run_dir) + ["--review-minutes", "0.25"]
                with self.assertRaisesRegex(SystemExit, "unsafe target"):
                    self.invoke(root, args)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_platform = root / "real-platform"
            real_platform.mkdir(parents=True)
            (root / "runs" / "private").mkdir(parents=True)
            (root / "runs" / "private" / "macos").symlink_to(
                real_platform, target_is_directory=True
            )
            run_dir = real_platform / "formal-01-active-decision-source-only"
            run_dir.mkdir()
            lexical_run_dir = (
                root
                / "runs"
                / "private"
                / "macos"
                / "formal-01-active-decision-source-only"
            )
            with self.assertRaisesRegex(SystemExit, "unsafe ancestor"):
                self.invoke(
                    root,
                    self.args(lexical_run_dir) + ["--review-minutes", "0.25"],
                )

    def test_atomic_score_write_preserves_old_file_and_cleans_temp_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = self.make_run(root)
            score_path = run_dir / "score.json"
            score_path.write_bytes(b"old-score\n")
            args = self.args(run_dir) + ["--review-minutes", "0.25"]
            real_replace = os.replace

            def fail_score_install(source, destination):
                if Path(destination) == score_path:
                    raise OSError("injected")
                return real_replace(source, destination)

            with patch("score_run.os.replace", side_effect=fail_score_install):
                with self.assertRaisesRegex(SystemExit, "score write failed: OSError"):
                    self.invoke(root, args)
            self.assertEqual(score_path.read_bytes(), b"old-score\n")
            self.assertEqual(list(run_dir.glob(".score-*")), [])

    def test_atomic_score_write_skips_posix_operations_when_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = root / "runs" / "private" / "macos" / "formal-01-active-decision-source-only"
            run_dir.mkdir(parents=True)
            payload = b'{"score":1}\n'
            with (
                patch.object(score_run_module, "ROOT", root),
                patch.object(
                    score_run_module,
                    "_supports_posix_file_modes",
                    return_value=False,
                ),
                patch.object(score_run_module.os, "fchmod", create=True) as fchmod,
            ):
                atomic_write_score(run_dir, payload)
            self.assertEqual((run_dir / "score.json").read_bytes(), payload)
            fchmod.assert_not_called()

            with (
                patch.object(
                    score_run_module,
                    "_supports_posix_file_modes",
                    return_value=False,
                ),
                patch.object(score_run_module.os, "open") as open_directory,
            ):
                score_run_module._fsync_directory(run_dir)
            open_directory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
