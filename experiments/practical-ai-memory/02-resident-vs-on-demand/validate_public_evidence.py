#!/usr/bin/env python3
"""Validate the compact public evidence package intended for Git."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from run_experiment import tree_checksum


ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence"
EXPECTED_TASKS = ("critical-boundary", "reference-detail", "volatile-state", "status-conflict")
EXPECTED_CONDITIONS = ("all-resident", "selective-resident", "index-only")
REQUIRED_REPRESENTATIVE_FILES = (
    "REPRODUCE.md",
    "events-summary.json",
    "final.md",
    "metadata.json",
    "score.json",
)
SENSITIVE_PATTERNS = (
    re.compile(r"/Users/"),
    re.compile(r"(?:/private)?/var/folders/"),
    re.compile(r"[A-Za-z]:(?:\\\\|\\|/)Users(?:\\\\|\\|/)"),
    re.compile(r'"thread_id"'),
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile("msu" + "tools", re.IGNORECASE),
    re.compile("pro" + "vider" + "_label", re.IGNORECASE),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_score(record: dict[str, object]) -> list[str]:
    run_name = str(record.get("run_name", "<unknown>"))
    score = record.get("score")
    if not isinstance(score, dict):
        return [f"{run_name}: score is missing or invalid"]

    failures = []
    if score.get("protocol_valid") is not True:
        failures.append(f"{run_name}: protocol invalid")
    correctness = score.get("correctness_score")
    maximum = score.get("correctness_max")
    if (
        not isinstance(correctness, int)
        or not isinstance(maximum, int)
        or maximum <= 0
        or not 0 <= correctness <= maximum
    ):
        failures.append(f"{run_name}: correctness score is out of range")
    if score.get("unsupported_claims") or score.get("irrelevant_project_facts"):
        failures.append(f"{run_name}: review issue count is nonzero")
    return failures


def main() -> int:
    failures = []
    manifest = EVIDENCE / "manifest.jsonl"
    if not manifest.is_file():
        print("missing evidence/manifest.jsonl")
        return 1
    records = [
        json.loads(line)
        for line in manifest.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    names = [record["run_name"] for record in records]
    if len(records) != 36 or len(set(names)) != 36:
        failures.append("manifest must contain 36 unique runs")

    group_counts = Counter((record["task"], record["condition"]) for record in records)
    expected_groups = {
        (task, condition) for task in EXPECTED_TASKS for condition in EXPECTED_CONDITIONS
    }
    if set(group_counts) != expected_groups or any(count != 3 for count in group_counts.values()):
        failures.append("manifest must contain 12 task/condition groups with n=3")

    representative_records = [
        record for record in records if record["representative_path"] is not None
    ]
    if len(representative_records) != 12:
        failures.append("manifest must identify 12 representative runs")

    fixture_hashes = {}
    for condition in EXPECTED_CONDITIONS:
        fixture = EVIDENCE / "fixtures" / condition
        if not fixture.is_dir():
            failures.append(f"missing fixture: {condition}")
            continue
        fixture_hashes[condition] = tree_checksum(fixture)

    for record in records:
        failures.extend(validate_score(record))
        if fixture_hashes.get(record["condition"]) != record["fixture_sha256"]:
            failures.append(f"{record['run_name']}: fixture checksum mismatch")
        prompt = ROOT / "prompts" / f"{record['task']}.md"
        if sha256(prompt) != record["prompt_sha256"]:
            failures.append(f"{record['run_name']}: prompt checksum mismatch")

    for record in representative_records:
        run_dir = EVIDENCE / record["representative_path"]
        for name in REQUIRED_REPRESENTATIVE_FILES:
            if not (run_dir / name).is_file():
                failures.append(f"{run_dir}: missing {name}")
        metadata_path = run_dir / "metadata.json"
        score_path = run_dir / "score.json"
        if metadata_path.is_file():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            for key in ("run_name", "task", "condition", "fixture_sha256", "prompt_sha256"):
                if metadata.get(key) != record.get(key):
                    failures.append(f"{run_dir}: metadata mismatch for {key}")
        if score_path.is_file():
            score = json.loads(score_path.read_text(encoding="utf-8"))
            if score != record["score"]:
                failures.append(f"{run_dir}: score does not match manifest")

    for path in EVIDENCE.rglob("*"):
        if not path.is_file():
            continue
        if path.name == "raw.jsonl":
            failures.append(f"{path}: raw events must not be public")
        text = path.read_text(encoding="utf-8")
        for pattern in SENSITIVE_PATTERNS:
            if pattern.search(text):
                failures.append(f"{path}: forbidden pattern {pattern.pattern}")
        if path.suffix == ".md":
            for target_text in re.findall(r"\[[^]]*\]\(([^)]+)\)", text):
                if target_text.startswith(("http://", "https://", "#")):
                    continue
                target = (path.parent / target_text).resolve()
                if not target.exists():
                    failures.append(f"{path}: broken relative link {target_text}")

    if failures:
        print("\n".join(failures))
        return 1
    total_files = sum(1 for path in EVIDENCE.rglob("*") if path.is_file())
    total_bytes = sum(path.stat().st_size for path in EVIDENCE.rglob("*") if path.is_file())
    print(
        f"validated records={len(records)}, representatives={len(representative_records)}, "
        f"files={total_files}, bytes={total_bytes}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
