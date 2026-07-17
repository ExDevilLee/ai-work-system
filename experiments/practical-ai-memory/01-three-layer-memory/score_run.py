#!/usr/bin/env python3
"""Attach a human-reviewed score to one preserved experiment run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--score", type=int, required=True)
    parser.add_argument("--max-score", type=int, required=True)
    parser.add_argument("--protocol-valid", choices=("yes", "no"), required=True)
    parser.add_argument("--notes", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 0 <= args.score <= args.max_score:
        raise SystemExit("score must be between zero and max-score")

    metadata = json.loads((args.run_dir / "metadata.json").read_text(encoding="utf-8"))
    score = {
        "run_name": metadata["run_name"],
        "task": metadata.get("task"),
        "condition": metadata["condition"],
        "correctness_score": args.score,
        "correctness_max": args.max_score,
        "protocol_valid": args.protocol_valid == "yes",
        "unsupported_claims": 0,
        "manual_review_status": "reviewed",
        "notes": args.notes,
    }
    (args.run_dir / "score.json").write_text(
        json.dumps(score, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.run_dir / "score.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
