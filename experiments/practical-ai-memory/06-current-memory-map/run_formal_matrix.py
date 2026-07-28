#!/usr/bin/env python3
"""Run the frozen 5 x 3 x 3 current-memory-map matrix with resume support."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from matrix_support import expected_run_contract, is_complete_successful_run
from run_experiment import argparse_path_identifier


ROOT = Path(__file__).resolve().parent
MODEL = "gpt-5.6-sol"
REASONING_EFFORT = "medium"
TASKS = (
    "active-decision",
    "superseded-rule",
    "unresolved-conflict",
    "scope-boundary",
    "pending-observation",
)
CONDITIONS = ("source-only", "flat-index", "state-projection")


def rotated_runs(offset: int) -> tuple[tuple[str, str], ...]:
    runs = []
    for task_index, task in enumerate(TASKS):
        start = (task_index + offset) % len(CONDITIONS)
        for condition_index in range(len(CONDITIONS)):
            runs.append((task, CONDITIONS[(start + condition_index) % len(CONDITIONS)]))
    return tuple(runs)


SCHEDULE = tuple(
    (f"formal-{repeat:02d}", rotated_runs(repeat - 1))
    for repeat in range(1, 4)
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixture-set", type=argparse_path_identifier, default="pilot-01"
    )
    parser.add_argument(
        "--platform-tag",
        type=argparse_path_identifier,
        choices=("macos", "win11"),
        default="macos",
    )
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--reasoning-effort", default=REASONING_EFFORT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    completed = 0
    skipped = 0
    for label, runs in SCHEDULE:
        for task, condition in runs:
            run_name = f"{label}-{task}-{condition}"
            run_dir = ROOT / "runs" / "private" / args.platform_tag / run_name
            try:
                expected = expected_run_contract(
                    ROOT,
                    run_name=run_name,
                    fixture_set=args.fixture_set,
                    task=task,
                    condition=condition,
                    platform=args.platform_tag,
                    model=args.model,
                    reasoning_effort=args.reasoning_effort,
                )
            except (OSError, ValueError) as error:
                print(
                    f"STOP expected-run contract failed: {run_name}: "
                    f"{type(error).__name__}",
                    file=sys.stderr,
                )
                return 1
            if is_complete_successful_run(run_dir, expected):
                print(f"SKIP {run_name}", flush=True)
                skipped += 1
                continue
            if run_dir.exists():
                print(f"STOP incomplete run directory: {run_name}", file=sys.stderr)
                return 1
            command = [
                sys.executable,
                str(ROOT / "run_experiment.py"),
                condition,
                "--label",
                label,
                "--fixture-set",
                args.fixture_set,
                "--task",
                task,
                "--model",
                args.model,
                "--reasoning-effort",
                args.reasoning_effort,
                "--platform-tag",
                args.platform_tag,
            ]
            print(f"RUN  {run_name}", flush=True)
            result = subprocess.run(command)
            if result.returncode != 0:
                print(f"STOP failed run: {run_name}", file=sys.stderr)
                return result.returncode
            if not is_complete_successful_run(run_dir, expected):
                print(f"STOP incomplete successful run: {run_name}", file=sys.stderr)
                return 1
            completed += 1
    print(f"formal matrix complete: completed={completed}, skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
