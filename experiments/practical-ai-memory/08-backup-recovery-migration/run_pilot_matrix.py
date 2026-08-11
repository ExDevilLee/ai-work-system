#!/usr/bin/env python3
"""Prepare and score the POC 08 Pilot matrix: 6 tasks × 3 conditions × 1 = 18 cells.

Usage::

    python3 run_pilot_matrix.py prepare     # create 18 run directories
    python3 run_pilot_matrix.py score       # score all prepared runs
    python3 run_pilot_matrix.py status      # show completion status
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from fixture_model import ROOT
from run_experiment import CONDITIONS, TASKS
from score_run import load_rubric, score_run

LABEL = "pilot-01"
PLATFORM = "macos"


def _run_dir(task: str, condition: str) -> Path:
    return ROOT / "runs" / "private" / PLATFORM / f"{LABEL}-{task}-{condition}"


def prepare_all() -> None:
    """Create all 18 run directories with assembled fixture snapshots and prompts."""
    from run_experiment import prepare_run

    created = 0
    skipped = 0
    for task in TASKS:
        for condition in CONDITIONS:
            rd = _run_dir(task, condition)
            if rd.exists():
                skipped += 1
                continue
            prepare_run(
                label=LABEL,
                task=task,
                condition=condition,
                platform_tag=PLATFORM,
            )
            created += 1
    print(f"prepared: {created} created, {skipped} skipped (already exist)")


def score_all() -> dict[str, Any]:
    """Score all 18 runs and return a summary."""
    rubric = load_rubric()
    results: list[dict[str, Any]] = []
    for task in TASKS:
        for condition in CONDITIONS:
            rd = _run_dir(task, condition)
            if not rd.is_dir():
                results.append({
                    "task": task,
                    "condition": condition,
                    "status": "missing",
                    "overall_pass": False,
                })
                continue
            final_path = rd / "final.md"
            meta_path = rd / "metadata.json"
            if not final_path.is_file() or not meta_path.is_file():
                results.append({
                    "task": task,
                    "condition": condition,
                    "status": "incomplete",
                    "overall_pass": False,
                })
                continue
            result = score_run(rd, rubric)
            result["status"] = "scored"
            results.append(result)

    total = len(results)
    passed = sum(1 for r in results if r.get("overall_pass"))
    failed = total - passed
    summary = {
        "label": LABEL,
        "total_cells": total,
        "passed": passed,
        "failed": failed,
        "results": results,
    }

    output_path = ROOT / "runs" / "aggregates" / PLATFORM / f"{LABEL}-mechanical-summary.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def status() -> None:
    """Print the current completion status of all 18 cells."""
    for task in TASKS:
        for condition in CONDITIONS:
            rd = _run_dir(task, condition)
            has_final = (rd / "final.md").is_file() if rd.is_dir() else False
            has_meta = (rd / "metadata.json").is_file() if rd.is_dir() else False
            mark = "✓" if has_final and has_meta else "✗"
            print(f"  {mark} {task:25s} {condition:25s}")


def main() -> int:
    parser = argparse.ArgumentParser(description="POC 08 Pilot matrix orchestrator.")
    parser.add_argument("action", choices=["prepare", "score", "status"])
    args = parser.parse_args()

    if args.action == "prepare":
        prepare_all()
    elif args.action == "score":
        summary = score_all()
        print(f"\nPilot mechanical scoring: {summary['passed']}/{summary['total_cells']} passed")
        if summary["failed"]:
            print("Failed cells:")
            for r in summary["results"]:
                if not r.get("overall_pass"):
                    print(f"  - {r['task']}/{r['condition']}: {r.get('status', 'scored')}")
                    if "groups" in r:
                        for g in r["groups"]:
                            if not g["passed"]:
                                print(f"      missing: {g['group']}")
                    if r.get("forbidden_violation"):
                        print(f"      forbidden hits: {r['forbidden_hits']}")
        return 0 if summary["failed"] == 0 else 1
    elif args.action == "status":
        status()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
