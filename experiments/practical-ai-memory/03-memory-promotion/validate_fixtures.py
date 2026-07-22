#!/usr/bin/env python3
"""Validate shared evidence, prompts, and condition boundaries."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONDITIONS = ("direct-promotion", "rule-gated", "staged-human-gate")
TASKS = (
    "repeated-evidence",
    "one-off-success",
    "conflicting-evidence",
    "expired-scope",
    "sensitive-record",
)


def validate(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    fixture_root = root / "fixtures" / "pilot-01"
    common = fixture_root / "common"
    conditions = fixture_root / "conditions"

    answers_path = root / "expected" / "answers.json"
    rubric_path = root / "expected" / "rubric.json"
    if not answers_path.is_file() or not rubric_path.is_file():
        return ["missing expected answers or rubric"]
    answers = json.loads(answers_path.read_text(encoding="utf-8"))
    rubric = json.loads(rubric_path.read_text(encoding="utf-8"))

    if set(answers) != set(TASKS):
        errors.append("answers must cover every frozen task exactly once")
    if set(rubric) != set(TASKS):
        errors.append("rubric must cover every frozen task exactly once")

    common_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(
            (item for item in common.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(common).as_posix(),
        )
    )
    for task in TASKS:
        prompt = root / "prompts" / f"{task}.md"
        observation = common / "observations" / f"{task}.md"
        if not prompt.is_file():
            errors.append(f"missing prompt: {task}")
        if not observation.is_file():
            errors.append(f"missing observation: {task}")

    required_markers = {
        "direct-promotion": "当前采用直接晋升机制",
        "rule-gated": "当前采用规则门禁机制",
        "staged-human-gate": "当前采用分阶段人工门禁机制",
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
        for forbidden in ("OBS-101", "OBS-102", "OBS-103", "OBS-104", "OBS-105"):
            if forbidden in text:
                errors.append(f"{condition} copies evidence id {forbidden}")

    prompt_text = "\n".join(
        (root / "prompts" / f"{task}.md").read_text(encoding="utf-8")
        for task in TASKS
        if (root / "prompts" / f"{task}.md").is_file()
    )
    for leaked in (
        "公开 Wiki 前先运行 Markdown 兼容性与导航检查。",
        "控制平台缓存、账号设置、发布时间和客户端展示等变量后重新验证",
    ):
        if leaked in prompt_text:
            errors.append("expected answer leaked into prompts")
    if "真实" in common_text and any(
        marker in common_text
        for marker in ("/Users/", "C:\\Users\\", "thread_id", "api_key")
    ):
        errors.append("fixture contains a private-data marker")

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
