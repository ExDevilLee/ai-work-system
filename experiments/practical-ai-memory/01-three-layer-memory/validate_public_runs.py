#!/usr/bin/env python3
"""Validate checksums, required evidence, and sanitization of public runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from run_experiment import tree_checksum


ROOT = Path(__file__).resolve().parent
REQUIRED_FILES = (
    "PUBLICATION.md",
    "events-summary.json",
    "final.md",
    "metadata.json",
    "prompt.md",
    "score.json",
)
SENSITIVE_PATTERNS = (
    re.compile(r"/Users/|[A-Za-z]:(?:\\\\|\\|/)Users(?:\\\\|\\|/)"),
    re.compile(r"/var/folders/"),
    re.compile(
        r"[A-Za-z]:(?:\\\\|\\|/)(?:Windows|ProgramData)(?:\\\\|\\|/)",
        re.IGNORECASE,
    ),
    re.compile(r'"thread_id"'),
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile("msu" + "tools", re.IGNORECASE),
    re.compile("pro" + "vider" + "_label", re.IGNORECASE),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-runs",
        action="store_true",
        help="Fail when no local public runs exist",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    public_root = ROOT / "runs" / "public"
    failures = []
    checked = 0

    for run_dir in sorted(path for path in public_root.rglob("*") if path.is_dir()):
        if not (run_dir / "metadata.json").is_file():
            continue
        checked += 1
        for name in REQUIRED_FILES:
            if not (run_dir / name).is_file():
                failures.append(f"{run_dir}: missing {name}")

        metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
        fixture = run_dir / "fixture-snapshot"
        if tree_checksum(fixture) != metadata["fixture_sha256"]:
            failures.append(f"{run_dir}: fixture checksum mismatch")
        prompt_hash = hashlib.sha256((run_dir / "prompt.md").read_bytes()).hexdigest()
        if prompt_hash != metadata["prompt_sha256"]:
            failures.append(f"{run_dir}: prompt checksum mismatch")

        for path in run_dir.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            for pattern in SENSITIVE_PATTERNS:
                if pattern.search(text):
                    failures.append(f"{path}: sensitive pattern {pattern.pattern}")

    if failures:
        print("\n".join(failures))
        return 1
    if args.require_runs and checked == 0:
        print("no local public runs found")
        return 1
    if checked == 0:
        print("no local public runs; nothing to validate")
        return 0
    print(f"validated {checked} public runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
