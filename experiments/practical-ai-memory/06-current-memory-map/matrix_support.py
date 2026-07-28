#!/usr/bin/env python3
"""Shared resume guards for experiment matrices."""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from run_experiment import assemble_fixture, tree_checksum


REQUIRED_FILES = (
    "metadata.json",
    "final.md",
    "raw.jsonl",
    "stderr.log",
    "prompt.md",
)


@dataclass(frozen=True)
class ExpectedRun:
    run_name: str
    fixture_set: str
    task: str
    condition: str
    platform: str
    model: str
    reasoning_effort: str
    fixture_sha256: str
    prompt_sha256: str


def expected_run_contract(
    root: Path,
    *,
    run_name: str,
    fixture_set: str,
    task: str,
    condition: str,
    platform: str,
    model: str,
    reasoning_effort: str,
) -> ExpectedRun:
    """Derive resume identity from the current frozen fixture and prompt bytes."""
    fixture_root = root / "fixtures" / fixture_set
    prompt_path = root / "prompts" / f"{task}.md"
    if not prompt_path.is_file():
        raise FileNotFoundError(f"missing frozen prompt for task: {task}")
    with tempfile.TemporaryDirectory(prefix="current-map-expected-") as temporary:
        snapshot = Path(temporary) / "fixture-snapshot"
        assemble_fixture(fixture_root, condition, snapshot)
        fixture_sha256 = tree_checksum(snapshot)
    return ExpectedRun(
        run_name=run_name,
        fixture_set=fixture_set,
        task=task,
        condition=condition,
        platform=platform,
        model=model,
        reasoning_effort=reasoning_effort,
        fixture_sha256=fixture_sha256,
        prompt_sha256=hashlib.sha256(prompt_path.read_bytes()).hexdigest(),
    )


def is_complete_successful_run(run_dir: Path, expected: ExpectedRun) -> bool:
    if not all((run_dir / name).is_file() for name in REQUIRED_FILES):
        return False
    if not (run_dir / "fixture-snapshot").is_dir():
        return False
    try:
        if not (run_dir / "final.md").read_text(encoding="utf-8").strip():
            return False
        metadata = json.loads(
            (run_dir / "metadata.json").read_text(encoding="utf-8")
        )
        if not isinstance(metadata, dict):
            return False
        prompt_sha256 = hashlib.sha256(
            (run_dir / "prompt.md").read_bytes()
        ).hexdigest()
        fixture_sha256 = tree_checksum(run_dir / "fixture-snapshot")
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return False
    identity_matches = (
        metadata.get("run_name") == expected.run_name
        and metadata.get("fixture_set") == expected.fixture_set
        and metadata.get("task") == expected.task
        and metadata.get("condition") == expected.condition
        and metadata.get("platform_tag") == expected.platform
        and metadata.get("requested_model") == expected.model
        and metadata.get("reasoning_effort") == expected.reasoning_effort
        and metadata.get("fixture_sha256") == expected.fixture_sha256
        and metadata.get("prompt_sha256") == expected.prompt_sha256
        and fixture_sha256 == expected.fixture_sha256
        and prompt_sha256 == expected.prompt_sha256
    )
    return (
        identity_matches
        and metadata.get("exit_code") == 0
        and isinstance(metadata.get("usage"), dict)
        and metadata.get("protocol_environment_isolated") is True
        and metadata.get("workspace_metric_coverage_complete") is True
        and metadata.get("workspace_output_bytes_reliable") is True
    )
