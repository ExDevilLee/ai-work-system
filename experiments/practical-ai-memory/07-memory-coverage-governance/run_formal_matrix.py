#!/usr/bin/env python3
"""Run the frozen 5 x 3 x 3 memory-coverage-governance matrix with resume support."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
import re

from matrix_support import expected_run_contract, is_complete_successful_run
from run_experiment import argparse_path_identifier


ROOT = Path(__file__).resolve().parent
MODEL = "deepseek-v4-flash"
REASONING_EFFORT = "max"
TASKS = (
    "coverage-gap",
    "review-due",
    "governance-queue",
    "scope-slice",
    "source-trace",
)
CONDITIONS = ("source-only", "state-projection", "coverage-governance-projection")
USAGE_LIMIT_MARKER = "You've hit your usage limit"


def rotated_runs(offset: int) -> tuple[tuple[str, str], ...]:
    runs = []
    for task_index, task in enumerate(TASKS):
        start = (task_index + offset) % len(CONDITIONS)
        for condition_index in range(len(CONDITIONS)):
            runs.append((task, CONDITIONS[(start + condition_index) % len(CONDITIONS)]))
    return tuple(runs)


FORMAL_PREFIX = re.compile(r"^formal(?:-[A-Za-z0-9._]+)*-$")


def formal_schedule(prefix: str) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    if not FORMAL_PREFIX.fullmatch(prefix):
        raise ValueError("formal run prefix must start with formal- and end with -")
    return tuple(
        (f"{prefix}{repeat:02d}", rotated_runs(repeat - 1))
        for repeat in range(1, 4)
    )


SCHEDULE = formal_schedule("formal-")


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
    parser.add_argument("--run-prefix", default="formal-")
    parser.add_argument(
        "--continue-on-usage-limit",
        action="store_true",
        help="preserve and skip only cells rejected for direct Codex usage limits",
    )
    return parser.parse_args()


def is_usage_limited_run(run_dir: Path) -> bool:
    try:
        return USAGE_LIMIT_MARKER in (run_dir / "raw.jsonl").read_text(
            encoding="utf-8"
        )
    except (OSError, UnicodeDecodeError):
        return False


def main() -> int:
    args = parse_args()
    try:
        schedule = formal_schedule(args.run_prefix)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    completed = 0
    skipped = 0
    usage_limited = 0
    for label, runs in schedule:
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
                if args.continue_on_usage_limit and is_usage_limited_run(run_dir):
                    print(f"SKIP usage-limited {run_name}", flush=True)
                    usage_limited += 1
                    continue
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
                if args.continue_on_usage_limit and is_usage_limited_run(run_dir):
                    print(f"SKIP usage-limited {run_name}", flush=True)
                    usage_limited += 1
                    continue
                print(f"STOP failed run: {run_name}", file=sys.stderr)
                return result.returncode
            if not is_complete_successful_run(run_dir, expected):
                print(f"STOP incomplete successful run: {run_name}", file=sys.stderr)
                return 1
            completed += 1
    print(
        "formal matrix complete: "
        f"completed={completed}, skipped={skipped}, usage_limited={usage_limited}"
    )
    return 1 if usage_limited else 0


if __name__ == "__main__":
    raise SystemExit(main())
