#!/usr/bin/env python3
"""Run the frozen 4 x 3 x 3 formal matrix with resume support."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MODEL = "gpt-5.6-sol"
REASONING_EFFORT = "medium"

SCHEDULE = (
    (
        "formal-01",
        (
            ("critical-boundary", "all-resident"),
            ("reference-detail", "selective-resident"),
            ("volatile-state", "index-only"),
            ("status-conflict", "all-resident"),
            ("critical-boundary", "selective-resident"),
            ("reference-detail", "index-only"),
            ("volatile-state", "all-resident"),
            ("status-conflict", "selective-resident"),
            ("critical-boundary", "index-only"),
            ("reference-detail", "all-resident"),
            ("volatile-state", "selective-resident"),
            ("status-conflict", "index-only"),
        ),
    ),
    (
        "formal-02",
        (
            ("reference-detail", "index-only"),
            ("volatile-state", "all-resident"),
            ("status-conflict", "selective-resident"),
            ("critical-boundary", "selective-resident"),
            ("reference-detail", "all-resident"),
            ("volatile-state", "selective-resident"),
            ("status-conflict", "index-only"),
            ("critical-boundary", "index-only"),
            ("reference-detail", "selective-resident"),
            ("volatile-state", "index-only"),
            ("status-conflict", "all-resident"),
            ("critical-boundary", "all-resident"),
        ),
    ),
    (
        "formal-03",
        (
            ("volatile-state", "selective-resident"),
            ("status-conflict", "index-only"),
            ("critical-boundary", "index-only"),
            ("reference-detail", "all-resident"),
            ("volatile-state", "index-only"),
            ("status-conflict", "all-resident"),
            ("critical-boundary", "all-resident"),
            ("reference-detail", "selective-resident"),
            ("volatile-state", "all-resident"),
            ("status-conflict", "selective-resident"),
            ("critical-boundary", "selective-resident"),
            ("reference-detail", "index-only"),
        ),
    ),
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
