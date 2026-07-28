#!/usr/bin/env python3
"""Shared resume guards for experiment matrices."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from run_experiment import assemble_fixture, ensure_contained_path, tree_checksum


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
    evidence_root: Optional[Path] = None


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
    root = ensure_contained_path(root, root, allow_missing=False)
    fixture_root = ensure_contained_path(
        root / "fixtures" / fixture_set, root, allow_missing=False
    )
    prompt_path = ensure_contained_path(
        root / "prompts" / f"{task}.md", root, allow_missing=False
    )
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
        evidence_root=root,
    )


def _is_regular_file(path: Path) -> bool:
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except OSError:
        return False


def _is_real_directory(path: Path) -> bool:
    try:
        return stat.S_ISDIR(path.lstat().st_mode)
    except OSError:
        return False


def _tree_has_only_real_files(root: Path) -> bool:
    if not _is_real_directory(root):
        return False
    try:
        for directory, names, files in os.walk(root, followlinks=False):
            directory_path = Path(directory)
            if not _is_real_directory(directory_path):
                return False
            for name in names:
                if not _is_real_directory(directory_path / name):
                    return False
            for name in files:
                if not _is_regular_file(directory_path / name):
                    return False
    except OSError:
        return False
    return True


def _run_location_is_safe(run_dir: Path, expected: ExpectedRun) -> bool:
    if expected.evidence_root is None:
        return True
    expected_dir = (
        expected.evidence_root
        / "runs"
        / "private"
        / expected.platform
        / expected.run_name
    )
    if Path(os.path.abspath(run_dir)) != Path(os.path.abspath(expected_dir)):
        return False
    try:
        ensure_contained_path(run_dir, expected.evidence_root, allow_missing=False)
    except ValueError:
        return False
    return True


def is_complete_successful_run(run_dir: Path, expected: ExpectedRun) -> bool:
    if not _run_location_is_safe(run_dir, expected):
        return False
    if not all(_is_regular_file(run_dir / name) for name in REQUIRED_FILES):
        return False
    if not _tree_has_only_real_files(run_dir / "fixture-snapshot"):
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
