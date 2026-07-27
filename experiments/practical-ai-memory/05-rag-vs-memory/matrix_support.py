#!/usr/bin/env python3
"""Shared resume guards for experiment matrices."""

from __future__ import annotations

import json
from pathlib import Path


REQUIRED_FILES = (
    "metadata.json",
    "final.md",
    "raw.jsonl",
    "stderr.log",
    "prompt.md",
)


def is_complete_successful_run(run_dir: Path) -> bool:
    if not all((run_dir / name).is_file() for name in REQUIRED_FILES):
        return False
    if not (run_dir / "fixture-snapshot").is_dir():
        return False
    if not (run_dir / "final.md").read_text(encoding="utf-8").strip():
        return False
    try:
        metadata = json.loads(
            (run_dir / "metadata.json").read_text(encoding="utf-8")
        )
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False
    return (
        metadata.get("exit_code") == 0
        and isinstance(metadata.get("usage"), dict)
        and metadata.get("protocol_environment_isolated") is True
        and metadata.get("workspace_metric_coverage_complete") is True
        and metadata.get("workspace_output_bytes_reliable") is True
    )
