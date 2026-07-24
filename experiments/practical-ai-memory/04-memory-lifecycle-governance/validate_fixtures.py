#!/usr/bin/env python3
"""Validate shared lifecycle evidence, prompts, and condition boundaries."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONDITIONS = ("append-only", "latest-wins", "lifecycle-governed")
TASKS = (
    "explicit-supersession",
    "unresolved-conflict",
    "time-expiry",
    "scope-narrowing",
    "emergency-revocation",
)


def validate(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    fixture_root = root / "fixtures" / "pilot-01"
    common = fixture_root / "common"
    conditions = fixture_root / "conditions"

    answers_path = root / "expected" / "answers.json"
    rubric_path = root / "expected" / "rubric.json"
    checks_path = root / "expected" / "governance-checks.json"
    if not all(path.is_file() for path in (answers_path, rubric_path, checks_path)):
        return ["missing expected answers, rubric, or governance checks"]
    answers = json.loads(answers_path.read_text(encoding="utf-8"))
    rubric = json.loads(rubric_path.read_text(encoding="utf-8"))
    checks = json.loads(checks_path.read_text(encoding="utf-8"))

    if set(answers) != set(TASKS):
        errors.append("answers must cover every frozen task exactly once")
    if set(rubric) != set(TASKS):
        errors.append("rubric must cover every frozen task exactly once")
    if set(checks) != set(CONDITIONS):
        errors.append("governance checks must cover every condition exactly once")

    for task in TASKS:
        prompt = root / "prompts" / f"{task}.md"
        record = common / "records" / f"{task}.md"
        if not prompt.is_file():
            errors.append(f"missing prompt: {task}")
        if not record.is_file():
            errors.append(f"missing record: {task}")

    required_markers = {
        "append-only": "当前采用只追加机制",
        "latest-wins": "当前采用最新记录优先机制",
        "lifecycle-governed": "当前采用显式生命周期治理机制",
    }
    for condition in CONDITIONS:
        path = conditions / condition / "AGENTS.md"
        if not path.is_file():
            errors.append(f"missing condition instructions: {condition}")
            continue
        text = path.read_text(encoding="utf-8")
        if required_markers[condition] not in text:
            errors.append(f"missing policy marker: {condition}")
        for other, marker in required_markers.items():
            if other != condition and marker in text:
                errors.append(f"{condition} leaks policy marker from {other}")
        for forbidden in ("MEM-201", "MEM-202", "MEM-203", "MEM-204", "MEM-205"):
            if forbidden in text:
                errors.append(f"{condition} copies evidence id {forbidden}")

    prompt_text = "\n".join(
        (root / "prompts" / f"{task}.md").read_text(encoding="utf-8")
        for task in TASKS
        if (root / "prompts" / f"{task}.md").is_file()
    )
    for leaked in (
        "全量重建 Wiki 导航并执行远端检查",
        "控制网络出口、服务配额和请求频率变量后复验",
    ):
        if leaked in prompt_text:
            errors.append("expected answer leaked into prompts")

    common_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(
            (item for item in common.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(common).as_posix(),
        )
    )
    for marker in ("/Users/", "C:\\Users\\", "thread_id", "api_key", "provider"):
        if marker in common_text:
            errors.append(f"fixture contains private-data marker: {marker}")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR {error}")
        return 1
    print(f"fixture validation passed: conditions={len(CONDITIONS)}, tasks={len(TASKS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
