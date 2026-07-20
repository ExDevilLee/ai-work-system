#!/usr/bin/env python3
"""Run the frozen 4 x 3 Pilot 01 matrix with failure and resume guards."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MODEL = "gpt-5.6-sol"
REASONING_EFFORT = "medium"

SCHEDULE = (
    ("critical-boundary", ("all-resident", "selective-resident", "index-only")),
    ("reference-detail", ("selective-resident", "index-only", "all-resident")),
    ("volatile-state", ("index-only", "all-resident", "selective-resident")),
    ("status-conflict", ("all-resident", "index-only", "selective-resident")),
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
    for task, conditions in SCHEDULE:
        for condition in conditions:
            run_name = f"pilot-01-{task}-{condition}"
            run_dir = ROOT / "runs" / "private" / args.platform_tag / run_name
            metadata = run_dir / "metadata.json"
            if metadata.is_file():
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
                "pilot-01",
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

    print(f"pilot matrix complete: completed={completed}, skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
