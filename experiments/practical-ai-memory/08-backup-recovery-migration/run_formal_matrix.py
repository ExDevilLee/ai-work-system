#!/usr/bin/env python3
"""Run one frozen POC 08 formal matrix with strict resume semantics."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from fixture_model import ROOT
from matrix_support import (
    expected_run_contract,
    is_complete_successful_run,
    is_recorded_execution_failure,
)
from run_experiment import CONDITIONS, TASKS, execute_cli_run
from score_run import score_formal_run


FORMAL_PREFIX = re.compile(r"^formal(?:-[A-Za-z0-9._]+)*-$")


def rotated_runs(offset: int) -> tuple[tuple[str, str], ...]:
    runs: list[tuple[str, str]] = []
    for task_index, task in enumerate(TASKS):
        start = (task_index + offset) % len(CONDITIONS)
        for condition_index in range(len(CONDITIONS)):
            runs.append((task, CONDITIONS[(start + condition_index) % len(CONDITIONS)]))
    return tuple(runs)


def formal_schedule(prefix: str) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    if not FORMAL_PREFIX.fullmatch(prefix):
        raise ValueError("formal run prefix must start with formal- and end with -")
    return tuple(
        (f"{prefix}{repeat:02d}", rotated_runs(repeat - 1))
        for repeat in range(1, 4)
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-model", required=True)
    parser.add_argument("--cli-model", required=True, help="private runtime selector; never persisted")
    parser.add_argument("--reasoning-effort", default="max")
    parser.add_argument("--run-prefix", required=True)
    parser.add_argument("--platform-tag", default="macos")
    parser.add_argument("--max-time", type=int, default=180)
    parser.add_argument(
        "--continue-on-evaluation-failure",
        action="store_true",
        help="preserve reviewed semantic failures and finish remaining cells",
    )
    parser.add_argument(
        "--continue-on-execution-failure",
        action="store_true",
        help="preserve identity-matched nonzero runs and finish remaining cells",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        schedule = formal_schedule(args.run_prefix)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    completed = 0
    skipped = 0
    evaluation_failed = 0
    execution_failed = 0
    for label, cells in schedule:
        for task, condition in cells:
            run_name = f"{label}-{task}-{condition}"
            run_dir = ROOT / "runs" / "private" / args.platform_tag / run_name
            expected = expected_run_contract(
                ROOT,
                run_name=run_name,
                fixture_set="pilot-01",
                task=task,
                condition=condition,
                platform=args.platform_tag,
                model=args.public_model,
                reasoning_effort=args.reasoning_effort,
            )
            if is_complete_successful_run(run_dir, expected):
                if not score_formal_run(run_dir)["overall_pass"]:
                    if args.continue_on_evaluation_failure:
                        print(f"KEEP evaluation failure: {run_name}", flush=True)
                        evaluation_failed += 1
                        continue
                    print(f"STOP mechanically failed completed run: {run_name}", file=sys.stderr)
                    return 1
                print(f"SKIP {run_name}", flush=True)
                skipped += 1
                continue
            if run_dir.exists():
                if args.continue_on_execution_failure and is_recorded_execution_failure(run_dir, expected):
                    print(f"KEEP execution failure: {run_name}", flush=True)
                    execution_failed += 1
                    continue
                print(f"STOP incomplete run directory: {run_name}", file=sys.stderr)
                return 1
            print(f"RUN  {run_name}", flush=True)
            execute_cli_run(
                label=label,
                task=task,
                condition=condition,
                cli_model=args.cli_model,
                requested_model=args.public_model,
                requested_effort=args.reasoning_effort,
                platform_tag=args.platform_tag,
                max_time_seconds=args.max_time,
            )
            if not is_complete_successful_run(run_dir, expected):
                if args.continue_on_execution_failure and is_recorded_execution_failure(run_dir, expected):
                    print(f"KEEP execution failure: {run_name}", flush=True)
                    execution_failed += 1
                    continue
                print(f"STOP failed or incomplete run: {run_name}", file=sys.stderr)
                return 1
            if not score_formal_run(run_dir)["overall_pass"]:
                if args.continue_on_evaluation_failure:
                    print(f"KEEP evaluation failure: {run_name}", flush=True)
                    evaluation_failed += 1
                    continue
                print(f"STOP mechanical rubric failed: {run_name}", file=sys.stderr)
                return 1
            completed += 1
    print(
        "formal matrix complete: "
        f"completed={completed}, skipped={skipped}, "
        f"evaluation_failed={evaluation_failed}, execution_failed={execution_failed}"
    )
    return 1 if evaluation_failed or execution_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
