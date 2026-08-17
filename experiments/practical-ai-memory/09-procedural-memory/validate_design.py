#!/usr/bin/env python3
"""Validate the first procedural-memory POC design without model calls."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent
REQUIRED = {
    "prompt-only",
    "guide-assisted",
    "skill-workflow",
}
TASKS = {
    "classify-change",
    "prepare-review",
    "apply-scope",
    "recover-failure",
    "distill-candidate",
}
FORBIDDEN = ("自动晋升", "真实密钥", "真实会话 ID", "跨平台复现")


def main() -> int:
    design = (ROOT / "DESIGN.md").read_text(encoding="utf-8")
    experiment = (ROOT / "EXPERIMENT.md").read_text(encoding="utf-8")
    for condition in REQUIRED:
        if f"`{condition}`" not in design:
            raise SystemExit(f"missing condition: {condition}")
    for task in TASKS:
        if f"`{task}`" not in design:
            raise SystemExit(f"missing task: {task}")
    for phrase in FORBIDDEN:
        if phrase not in design and phrase not in experiment:
            raise SystemExit(f"missing safety boundary: {phrase}")
    if "人工 Review" not in design or "来源" not in design:
        raise SystemExit("missing review or traceability gate")
    print("procedural-memory design validation passed")
    print(f"conditions={len(REQUIRED)} tasks={len(TASKS)} variants=3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
