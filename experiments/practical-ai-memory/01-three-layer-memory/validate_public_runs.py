#!/usr/bin/env python3
"""Validate checksums, required evidence, and sanitization of public runs."""

from __future__ import annotations

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
    re.compile(r"/Users/"),
    re.compile(r"/var/folders/"),
    re.compile(r'"thread_id"'),
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
)


def main() -> int:
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
    print(f"validated {checked} public runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
