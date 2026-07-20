#!/usr/bin/env python3
"""Rerun the revised critical-boundary task across all three conditions."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONDITIONS = ("index-only", "selective-resident", "all-resident")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform-tag", choices=("macos", "win11"), default="macos")
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="medium")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for condition in CONDITIONS:
        run_name = f"pilot-02-critical-boundary-{condition}"
        run_dir = ROOT / "runs" / "private" / args.platform_tag / run_name
        metadata = run_dir / "metadata.json"
        if metadata.is_file():
            print(f"SKIP {run_name}", flush=True)
            continue
        if run_dir.exists():
            print(f"STOP incomplete run directory: {run_dir}", file=sys.stderr)
            return 1
        command = [
            sys.executable,
            str(ROOT / "run_experiment.py"),
            condition,
            "--label",
            "pilot-02",
            "--fixture-set",
            "pilot-01",
            "--task",
            "critical-boundary",
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
    print("Pilot 02 complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
