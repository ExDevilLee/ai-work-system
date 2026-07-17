#!/usr/bin/env python3
"""Aggregate reviewed experiment runs without mixing model configurations."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--output-stem", required=True)
    return parser.parse_args()


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "min": min(values),
        "median": statistics.median(values),
        "mean": round(statistics.mean(values), 3),
        "max": max(values),
    }


def main() -> int:
    args = parse_args()
    private = ROOT / "runs" / "private" / "macos"
    rows = []
    model_configs = set()

    for run_dir in sorted(private.glob(f"{args.prefix}*")):
        metadata_path = run_dir / "metadata.json"
        score_path = run_dir / "score.json"
        if not metadata_path.is_file() or not score_path.is_file():
            continue
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        score = json.loads(score_path.read_text(encoding="utf-8"))
        if not score["protocol_valid"]:
            continue
        model_config = (
            metadata.get("requested_model"),
            metadata.get("reasoning_effort"),
            metadata.get("codex_version"),
        )
        model_configs.add(model_config)
        usage = metadata.get("usage") or {}
        rows.append(
            {
                "run_name": metadata["run_name"],
                "purpose": metadata["purpose"],
                "task": metadata["task"],
                "condition": metadata["condition"],
                "model": metadata.get("requested_model"),
                "reasoning_effort": metadata.get("reasoning_effort"),
                "codex_version": metadata.get("codex_version"),
                "score": score["correctness_score"],
                "max_score": score["correctness_max"],
                "workspace_command_calls": metadata["workspace_command_calls"],
                "workspace_output_bytes": metadata["workspace_output_bytes"],
                "workspace_output_bytes_reliable": metadata[
                    "workspace_output_bytes_reliable"
                ],
                "elapsed_seconds": metadata["elapsed_seconds"],
                "input_tokens": usage.get("input_tokens"),
                "cached_input_tokens": usage.get("cached_input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "reasoning_output_tokens": usage.get("reasoning_output_tokens"),
            }
        )

    if not rows:
        raise SystemExit("no reviewed runs matched")
    if len(model_configs) != 1:
        raise SystemExit(f"refusing to mix model configurations: {model_configs}")

    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    csv_path = data_dir / f"{args.output_stem}.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["task"]), str(row["condition"]))].append(row)

    group_summary = {}
    for (task, condition), group in sorted(groups.items()):
        key = f"{task}:{condition}"
        group_summary[key] = {
            "n": len(group),
            "correctness": {
                "score": sum(int(row["score"]) for row in group),
                "max_score": sum(int(row["max_score"]) for row in group),
            },
            "workspace_command_calls": summarize(
                [float(row["workspace_command_calls"]) for row in group]
            ),
            "workspace_output_bytes": summarize(
                [float(row["workspace_output_bytes"]) for row in group]
            ),
            "elapsed_seconds": summarize(
                [float(row["elapsed_seconds"]) for row in group]
            ),
            "input_tokens": summarize(
                [float(row["input_tokens"]) for row in group]
            ),
            "output_tokens": summarize(
                [float(row["output_tokens"]) for row in group]
            ),
            "reasoning_output_tokens": summarize(
                [float(row["reasoning_output_tokens"]) for row in group]
            ),
        }

    model, effort, cli_version = next(iter(model_configs))
    summary = {
        "selection_prefix": args.prefix,
        "run_count": len(rows),
        "model_configuration": {
            "model": model,
            "reasoning_effort": effort,
            "codex_version": cli_version,
        },
        "groups": group_summary,
    }
    json_path = data_dir / f"{args.output_stem}.json"
    json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(csv_path)
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
