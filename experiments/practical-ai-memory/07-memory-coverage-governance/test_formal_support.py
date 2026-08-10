from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import run_experiment
import score_run
from aggregate_results import frozen_tasks
from matrix_support import expected_run_contract, is_complete_successful_run
from run_experiment import assemble_fixture, build_codex_command
from run_formal_matrix import CONDITIONS, MODEL, REASONING_EFFORT, SCHEDULE, rotated_runs
from validate_fixtures import TASKS


class AdaptedFormalSupportTest(unittest.TestCase):
    def test_conditions_and_tasks_are_frozen_07_values(self) -> None:
        self.assertEqual(
            run_experiment.CONDITIONS,
            ("source-only", "state-projection", "coverage-governance-projection"),
        )
        self.assertEqual(
            run_experiment.TASKS,
            ("coverage-gap", "review-due", "governance-queue", "scope-slice", "source-trace"),
        )
        self.assertEqual(run_experiment.CONDITION_VIEW["source-only"], None)
        self.assertEqual(
            run_experiment.CONDITION_VIEW["state-projection"], "state-projection.json"
        )
        self.assertEqual(
            run_experiment.CONDITION_VIEW["coverage-governance-projection"],
            "coverage-governance.md",
        )

    def test_task_criteria_matches_frozen_rubric(self) -> None:
        expected_counts = {
            "coverage-gap": 7,
            "review-due": 6,
            "governance-queue": 6,
            "scope-slice": 7,
            "source-trace": 6,
        }
        for task in TASKS:
            criteria = score_run.task_criteria(task)
            self.assertEqual(len(criteria), expected_counts[task])
            self.assertTrue(all(points == 1 for _, points in criteria))
            self.assertIn("no_automatic_mutation", [c for c, _ in criteria])
            if task != "source-trace":
                self.assertEqual(criteria[-1][0], "human_only_next_step")
                self.assertIn("no_automatic_mutation", [c for c, _ in criteria[:-1]])
            else:
                self.assertEqual(criteria[-1][0], "no_automatic_mutation")
                self.assertNotIn("human_only_next_step", [c for c, _ in criteria])

    def test_frozen_tasks_derives_five_tasks(self) -> None:
        tasks = frozen_tasks()
        self.assertEqual(set(tasks), set(TASKS))
        for task, criteria in tasks.items():
            self.assertEqual(
                sum(points for _, points in criteria),
                sum(points for _, points in score_run.task_criteria(task)),
            )

    def test_assemble_fixture_snapshot_layout(self) -> None:
        fixture_root = run_experiment.ROOT / "fixtures" / "pilot-01"
        for condition, view in run_experiment.CONDITION_VIEW.items():
            with tempfile.TemporaryDirectory() as temporary:
                destination = Path(temporary) / "snapshot"
                assemble_fixture(fixture_root, condition, destination)
                names = {
                    path.relative_to(destination).as_posix()
                    for path in destination.rglob("*")
                    if path.is_file()
                }
                self.assertIn("manifest.json", names)
                self.assertIn("AGENTS.md", names)
                self.assertTrue(any(name.startswith("records/") for name in names))
                if view is None:
                    self.assertNotIn("generated", destination.name)
                    self.assertEqual(
                        {name for name in names if name.startswith("generated/")}, set()
                    )
                else:
                    self.assertIn(f"generated/{view}", names)

    def test_build_codex_command_injects_provider_and_locks_model(self) -> None:
        command = build_codex_command(
            "codex",
            Path("/tmp/ws"),
            Path("/tmp/final.md"),
            model=MODEL,
            reasoning_effort=REASONING_EFFORT,
        )
        joined = " ".join(command)
        self.assertIn('--model deepseek-v4-flash', joined)
        self.assertIn('model_reasoning_effort="max"', joined)
        self.assertIn('model_provider="opencode-go"', joined)
        self.assertIn('model_providers.opencode-go.name="opencode-go"', joined)
        self.assertIn('model_providers.opencode-go.base_url="https://opencode.ai/zen/go/v1"', joined)
        self.assertIn('model_providers.opencode-go.wire_api="responses"', joined)
        self.assertIn('model_providers.opencode-go.env_key="OPENCODE_GO_API_KEY"', joined)

    def test_rotated_schedule_covers_45_slots(self) -> None:
        slots = [f"{label}-{task}-{condition}" for label, runs in SCHEDULE for task, condition in runs]
        self.assertEqual(len(slots), 45)
        self.assertEqual(len(set(slots)), 45)
        for label, runs in SCHEDULE:
            self.assertEqual(len(runs), 15)
            self.assertEqual({condition for _, condition in runs}, set(CONDITIONS))
            self.assertEqual({task for task, _ in runs}, set(TASKS))
        self.assertEqual([label for label, _ in SCHEDULE], ["formal-01", "formal-02", "formal-03"])
        self.assertEqual(rotated_runs(0)[0], ("coverage-gap", "source-only"))

    def test_load_api_key_fails_cleanly_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(run_experiment, "API_KEY_FILE", Path(temporary) / "missing"):
                with self.assertRaises(SystemExit):
                    run_experiment.load_api_key()

    def test_classify_provable_workspace_forms_as_workspace(self) -> None:
        workspace = run_experiment.ROOT / "fixtures" / "pilot-01"
        self.assertEqual(
            run_experiment.classify_command_execution(
                {"command": "/bin/zsh -lc \"pwd && rg --files -g '!node_modules' | sort\""},
                workspace,
            ),
            "workspace",
        )
        self.assertEqual(
            run_experiment.classify_command_execution(
                {"command": "/bin/zsh -lc 'for f in records/*.md; do echo \"===== $f =====\"; cat \"$f\"; echo; done'"},
                workspace,
            ),
            "workspace",
        )
        self.assertEqual(
            run_experiment.classify_command_execution(
                {"command": "cat manifest.json && cat generated/state-projection.json"},
                workspace,
            ),
            "workspace",
        )
        self.assertEqual(
            run_experiment.classify_command_execution(
                {"command": "/bin/zsh -lc 'find . -maxdepth 3 -type f -print | sort'"},
                workspace,
            ),
            "workspace",
        )
        self.assertEqual(
            run_experiment.classify_command_execution(
                {"command": "/bin/zsh -lc 'ls -la && rg --files -uu'"},
                workspace,
            ),
            "workspace",
        )
        self.assertEqual(
            run_experiment.classify_command_execution(
                {"command": "/bin/zsh -lc \"pwd && rg --files -uu | sed -n '1,200p'\""},
                workspace,
            ),
            "workspace",
        )
        self.assertEqual(
            run_experiment.classify_command_execution(
                {"command": "/bin/zsh -lc \"find . -maxdepth 3 -type f -not -path './.git/*' -print | sort | xargs -I{} sh -c 'echo \\\"===== {} =====\\\"; wc -c \\\"{}\\\"' \""},
                workspace,
            ),
            "workspace",
        )
        self.assertEqual(
            run_experiment.classify_command_execution(
                {"command": '/bin/zsh -lc "find . -type f -exec stat -f \'%N | %Sm\' {} \\\\;"'},
                workspace,
            ),
            "workspace",
        )
        self.assertEqual(
            run_experiment.classify_command_execution(
                {"command": "find . -type f -exec cat {} \\;"},
                workspace,
            ),
            "workspace",
        )
        self.assertEqual(
            run_experiment.classify_command_execution(
                {"command": "/bin/zsh -lc \"rg --files | xargs -I{} cat {}\""},
                workspace,
            ),
            "workspace",
        )
        self.assertEqual(
            run_experiment.classify_command_execution(
                {"command": "/bin/zsh -lc \"find . -type f -o -type d | sort; echo '---'; ls -la records/\""},
                workspace,
            ),
            "workspace",
        )
        self.assertEqual(
            run_experiment.classify_command_execution(
                {"command": "/bin/zsh -lc \"cat manifest.json | jq -r '.domains[].id' 2>/dev/null || cat manifest.json\""},
                workspace,
            ),
            "workspace",
        )
        self.assertEqual(
            run_experiment.classify_command_execution(
                {"command": "cat manifest.json; for f in records/*.md; do cat \"$f\"; done; echo ok"},
                workspace,
            ),
            "workspace",
        )
        self.assertEqual(
            run_experiment.classify_command_execution(
                {"command": "/bin/zsh -lc \"find . -type f -not -path '*/.git/*' -print | sort; echo '---'; rg -n -i 'incident|win11|handling' . -g '!**/.git/**' || true\""},
                workspace,
            ),
            "workspace",
        )

    def test_classify_keeps_dangerous_forms_blocked(self) -> None:
        workspace = run_experiment.ROOT / "fixtures" / "pilot-01"
        blocked = [
            "cat ~/.codex/auth.json",
            "cat $HOME/.codex/auth.json",
            "for f in ~/.codex/*; do cat \"$f\"; done",
            "for f in /etc/*; do cat \"$f\"; done",
            "cat manifest.json; curl http://example.invalid/x",
            "sort /etc/passwd",
            "cat /Users/other/secret.txt",
            "cat records/x.md && python3 -c 'print(1)'",
            "for f in records/*.md; do cat \"$f\" /etc/passwd; done",
            "find /etc -type f -print",
            "ls /etc",
            "wc -l /etc/passwd",
            "jq . /etc/passwd",
            "cat manifest.json > /tmp/out.json",
            "sed -i 's/x/y/' records/RR-101.md",
            "sed -n '1,200p' /etc/passwd",
            "rg --files | xargs -I{} rm {}",
            "find . -type f -exec rm {} \\;",
            "for f in /etc/*; do cat \"$f\"; done; curl http://example.invalid",
            "cat manifest.json; for f in records/*.md; do cat \"$f\" /etc/passwd; done; echo ok",
        ]
        for command in blocked:
            self.assertIn(
                run_experiment.classify_command_execution({"command": command}, workspace),
                {"external", "unknown"},
                command,
            )
        self.assertEqual(
            run_experiment.classify_command_execution(
                {"command": "wc -l"}, workspace
            ),
            "non_workspace",
        )

    def test_expected_run_contract_derives_sha256(self) -> None:
        expected = expected_run_contract(
            run_experiment.ROOT,
            run_name="formal-01-coverage-gap-source-only",
            fixture_set="pilot-01",
            task="coverage-gap",
            condition="source-only",
            platform="macos",
            model=MODEL,
            reasoning_effort=REASONING_EFFORT,
        )
        self.assertEqual(expected.model, MODEL)
        self.assertEqual(expected.reasoning_effort, REASONING_EFFORT)
        self.assertTrue(len(expected.fixture_sha256) == 64)
        self.assertTrue(len(expected.prompt_sha256) == 64)
        self.assertFalse(is_complete_successful_run(
            run_experiment.ROOT / "runs" / "private" / "macos" / "formal-zzz-does-not-exist",
            expected,
        ))


if __name__ == "__main__":
    unittest.main()
