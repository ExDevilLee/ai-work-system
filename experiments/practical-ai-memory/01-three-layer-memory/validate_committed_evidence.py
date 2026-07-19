#!/usr/bin/env python3
"""Validate the compact evidence package intended for Git."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from run_experiment import tree_checksum


ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence"
SENSITIVE_PATTERNS = (
    re.compile(r"/Users/"),
    re.compile(r"(?:/private)?/var/folders/"),
    re.compile(r"[A-Za-z]:(?:\\\\|\\|/)Users(?:\\\\|\\|/)"),
    re.compile(
        r"[A-Za-z]:(?:\\\\|\\|/)(?:Windows|ProgramData)(?:\\\\|\\|/)",
        re.IGNORECASE,
    ),
    re.compile(r'"thread_id"'),
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile("msu" + "tools", re.IGNORECASE),
    re.compile("pro" + "vider" + "_label", re.IGNORECASE),
)
REQUIRED_REPRESENTATIVE_FILES = (
    "REPRODUCE.md",
    "events-summary.json",
    "final.md",
    "metadata.json",
    "score.json",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    manifest_path = EVIDENCE / "manifest.jsonl"
    records = [
        json.loads(line)
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    failures = []
    names = [record["run_name"] for record in records]
    if len(records) != 36 or len(set(names)) != 36:
        failures.append("manifest must contain 36 unique runs")

    representative_records = [
        record for record in records if record["representative_path"] is not None
    ]
    if len(representative_records) != 10:
        failures.append("manifest must identify 10 representative runs")

    for record in representative_records:
        run_dir = EVIDENCE / record["representative_path"]
        for name in REQUIRED_REPRESENTATIVE_FILES:
            if not (run_dir / name).is_file():
                failures.append(f"{run_dir}: missing {name}")

        metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
        if record["run_name"] == "pilot-02-reference-retrieval-baseline":
            fixture = EVIDENCE / "fixtures" / "pilot-02-invalid-baseline"
        else:
            fixture = ROOT / "fixtures" / "pilot-02" / record["condition"]
        prompt = ROOT / "prompts" / f"{record['task']}.md"
        if tree_checksum(fixture) != metadata["fixture_sha256"]:
            failures.append(f"{run_dir}: fixture checksum mismatch")
        if sha256(prompt) != metadata["prompt_sha256"]:
            failures.append(f"{run_dir}: prompt checksum mismatch")

    for path in EVIDENCE.rglob("*"):
        if not path.is_file():
            continue
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
    total_bytes = sum(path.stat().st_size for path in EVIDENCE.rglob("*") if path.is_file())
    total_files = sum(1 for path in EVIDENCE.rglob("*") if path.is_file())
    print(
        f"validated records={len(records)}, representatives={len(representative_records)}, "
        f"files={total_files}, bytes={total_bytes}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
