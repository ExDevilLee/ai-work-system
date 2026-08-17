#!/usr/bin/env python3
"""Validate P9's committed public evidence package."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence"
CONDITIONS = ("prompt-only", "guide-assisted", "skill-workflow")
TASKS = (
    "classify-change",
    "prepare-review",
    "apply-scope",
    "recover-failure",
    "distill-candidate",
)
SENSITIVE_PATTERNS = (
    re.compile(r"/Users/"),
    re.compile(r"[A-Za-z]:[\\/]+Users[\\/]"),
    re.compile(r'"thread_id"\s*:'),
    re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"provider_label", re.IGNORECASE),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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
    names = [record.get("run_name") for record in records]
    if len(records) != 50 or len(set(names)) != 50:
        failures.append("manifest must contain 50 unique records")

    cells = [record for record in records if record.get("record_type") == "cell"]
    aggregates = [
        record for record in records if record.get("record_type") == "aggregate-review"
    ]
    if len(cells) != 45 or len(aggregates) != 5:
        failures.append("manifest must contain 45 cell and 5 aggregate-review records")

    groups = Counter((record.get("task"), record.get("condition")) for record in cells)
    expected_groups = {(task, condition) for task in TASKS for condition in CONDITIONS}
    if set(groups) != expected_groups or any(count != 3 for count in groups.values()):
        failures.append("cell records must cover 5 tasks x 3 conditions x 3 variants")

    tasks_path = EVIDENCE / "fixtures" / "tasks.json"
    expected_tasks_sha = sha256(tasks_path) if tasks_path.is_file() else None
    for record in cells:
        if record.get("review", {}).get("status") != "passed":
            failures.append(f"{record.get('run_name')}: boundary review did not pass")
        if record.get("condition_retries") != 0:
            failures.append(f"{record.get('run_name')}: unexpected condition retry")
        if record.get("tasks_sha256") != expected_tasks_sha:
            failures.append(f"{record.get('run_name')}: tasks checksum mismatch")
        material = EVIDENCE / "fixtures" / "materials" / f"{record['condition']}.md"
        if not material.is_file() or record.get("material_sha256") != sha256(material):
            failures.append(f"{record.get('run_name')}: material checksum mismatch")

    for record in aggregates:
        if record.get("source_record_status") != "aggregate-only":
            failures.append(f"{record.get('run_name')}: aggregate boundary is missing")
        evidence_path = EVIDENCE / str(record.get("evidence_path"))
        if not evidence_path.is_file():
            failures.append(f"{record.get('run_name')}: aggregate report is missing")
        elif sha256(evidence_path) != record.get("evidence_sha256"):
            failures.append(f"{record.get('run_name')}: aggregate checksum mismatch")

    representative_records = [
        record for record in cells if record.get("representative_path")
    ]
    if len(representative_records) != 9:
        failures.append("manifest must identify 9 representative cell records")
    for record in representative_records:
        run_dir = EVIDENCE / str(record["representative_path"])
        for filename in ("final.json", "metadata.json", "REPRODUCE.md"):
            if not (run_dir / filename).is_file():
                failures.append(f"{run_dir}: missing {filename}")
        final_path = run_dir / "final.json"
        if final_path.is_file():
            final = json.loads(final_path.read_text(encoding="utf-8"))
            if final.get("cell") != record.get("cell"):
                failures.append(f"{run_dir}: cell mismatch")
            if canonical_sha(final.get("answer")) != record.get("answer_sha256"):
                failures.append(f"{run_dir}: answer checksum mismatch")

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
    files = [path for path in EVIDENCE.rglob("*") if path.is_file()]
    print(
        f"validated records={len(records)} cell_records={len(cells)} "
        f"aggregate_records={len(aggregates)} representatives=9 "
        f"files={len(files)} bytes={sum(path.stat().st_size for path in files)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
