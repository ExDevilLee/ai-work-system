#!/usr/bin/env python3
"""Aggregate POC 08 Pilot results into a public-facing summary.

Reads the mechanical summary produced by ``run_pilot_matrix.py score`` and
generates ``data/pilot-01-macos-glm-5.2.csv`` and ``.json`` with per-cell
pass/fail status.
"""

from __future__ import annotations

import csv
import json
from typing import Any

from fixture_model import ROOT
from run_experiment import CONDITIONS, TASKS

LABEL = "pilot-01"
PLATFORM = "macos"


def aggregate() -> dict[str, Any]:
    summary_path = (
        ROOT / "runs" / "aggregates" / PLATFORM / f"{LABEL}-mechanical-summary.json"
    )
    if not summary_path.is_file():
        raise FileNotFoundError("run `run_pilot_matrix.py score` first")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    results = {f"{r['task']}/{r['condition']}": r for r in summary["results"]}

    # Build CSV rows.
    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    csv_path = data_dir / f"{LABEL}-{PLATFORM}-glm-5.2.csv"
    json_path = data_dir / f"{LABEL}-{PLATFORM}-glm-5.2.json"

    fieldnames = [
        "task", "condition", "status", "overall_pass", "score", "max_score",
        "forbidden_violation",
    ]
    rows: list[dict[str, Any]] = []
    for task in TASKS:
        for condition in CONDITIONS:
            key = f"{task}/{condition}"
            r = results.get(key, {})
            row = {
                "task": task,
                "condition": condition,
                "status": r.get("status", "missing"),
                "overall_pass": r.get("overall_pass", False),
                "score": r.get("score", 0),
                "max_score": r.get("max_score", 0),
                "forbidden_violation": r.get("forbidden_violation", False),
            }
            rows.append(row)

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    aggregate_data = {
        "label": LABEL,
        "platform": PLATFORM,
        "requested_model": "glm-5.2",
        "requested_effort": "unknown",
        "observed_model": "unknown",
        "observed_effort": "unknown",
        "execution_path": "session",
        "total_cells": len(rows),
        "passed": sum(1 for r in rows if r["overall_pass"]),
        "failed": sum(1 for r in rows if not r["overall_pass"]),
        "cells": rows,
    }
    json_path.write_text(
        json.dumps(aggregate_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"aggregate: {csv_path.name} ({len(rows)} rows)")
    print(f"aggregate: {json_path.name}")
    print(f"passed: {aggregate_data['passed']}/{aggregate_data['total_cells']}")
    return aggregate_data


if __name__ == "__main__":
    aggregate()
