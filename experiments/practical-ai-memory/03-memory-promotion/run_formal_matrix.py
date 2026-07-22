#!/usr/bin/env python3
"""Run the frozen 5 x 3 x 3 formal matrix with resume support."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from matrix_support import is_complete_successful_run


ROOT = Path(__file__).resolve().parent
MODEL = "gpt-5.6-sol"
REASONING_EFFORT = "medium"
TASKS = (
    "repeated-evidence",
    "one-off-success",
    "conflicting-evidence",
    "expired-scope",
    "sensitive-record",
)
CONDITIONS = ("direct-promotion", "rule-gated", "staged-human-gate")


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
    parser.add_argument("--platform-tag", choices=("macos", "win11"), default="macos")
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
            if is_complete_successful_run(run_dir):
                print(f"SKIP {run_name}", flush=True)
                skipped += 1
                continue
            if run_dir.exists():
                print(f"STOP incomplete run directory: {run_dir}", file=sys.stderr)
                return 1
            command = [
                sys.executable,
                str(ROOT / "run_experiment.py"),
                condition,
                "--label",
                label,
                "--fixture-set",
                "pilot-01",
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
            completed += 1
    print(f"formal matrix complete: completed={completed}, skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
