#!/usr/bin/env python3
"""Score and export one de-identified POC 08 formal matrix."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from fixture_model import ROOT
from run_experiment import CONDITIONS, TASKS
from score_run import score_formal_run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-prefix", required=True)
    parser.add_argument("--output-label", required=True)
    parser.add_argument("--public-model", required=True)
    parser.add_argument("--reasoning-effort", default="max")
    parser.add_argument("--platform-tag", default="macos")
    return parser.parse_args()


def aggregate(args: argparse.Namespace) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    private_results: list[dict[str, Any]] = []
    for repeat in range(1, 4):
        label = f"{args.run_prefix}{repeat:02d}"
        for task in TASKS:
            for condition in CONDITIONS:
                run_name = f"{label}-{task}-{condition}"
                run_dir = ROOT / "runs" / "private" / args.platform_tag / run_name
                if not run_dir.is_dir():
                    raise FileNotFoundError(f"missing formal run: {run_name}")
                result = score_formal_run(run_dir)
                metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
                if metadata.get("requested_model") != args.public_model:
                    raise ValueError(f"model contract mismatch: {run_name}")
                if metadata.get("requested_effort") != args.reasoning_effort:
                    raise ValueError(f"effort contract mismatch: {run_name}")
                private_results.append(result)
                rows.append({
                    "repeat": repeat,
                    "task": task,
                    "condition": condition,
                    "overall_pass": result["overall_pass"],
                    "score": result["score"],
                    "max_score": result["max_score"],
                    "forbidden_violation": result["forbidden_violation"],
                    "exit_code": metadata["exit_code"],
                    "final_answer_present": metadata["final_answer_present"],
                })

    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    csv_path = data_dir / f"{args.output_label}.csv"
    json_path = data_dir / f"{args.output_label}.json"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "label": args.output_label,
        "platform": args.platform_tag,
        "requested_model": args.public_model,
        "requested_effort": args.reasoning_effort,
        "observed_model": "unknown",
        "observed_effort": "unknown",
        "execution_path": "omp-cli",
        "total_cells": len(rows),
        "passed": sum(1 for row in rows if row["overall_pass"]),
        "failed": sum(1 for row in rows if not row["overall_pass"]),
        "cells": rows,
    }
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    private_path = ROOT / "runs" / "aggregates" / args.platform_tag / f"{args.output_label}-mechanical-summary.json"
    private_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_text(
        json.dumps({**summary, "results": private_results}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"formal aggregate: {summary['passed']}/{summary['total_cells']} passed")
    return summary


def main() -> int:
    args = parse_args()
    summary = aggregate(args)
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
