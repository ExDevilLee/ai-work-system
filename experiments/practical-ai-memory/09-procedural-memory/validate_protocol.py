#!/usr/bin/env python3
"""Validate the synthetic Pilot protocol and matrix without model calls."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "pilot-01"
FORBIDDEN = ("ANSWER_LEAK=", "SCORE_LEAK=", "AUTO_WRITE_FACTS=")


def main() -> int:
    manifest = json.loads((FIXTURE / "manifest.json").read_text(encoding="utf-8"))
    conditions = manifest["conditions"]
    tasks = manifest["tasks"]
    variants = manifest["variants_per_task"]
    if len(conditions) != 3 or len(tasks) != 5 or variants != 3:
        raise SystemExit("unexpected Pilot dimensions")
    if len(set(conditions)) != len(conditions) or len(set(tasks)) != len(tasks):
        raise SystemExit("duplicate condition or task")
    if set(manifest["materials"]) != set(conditions):
        raise SystemExit("material mapping does not cover conditions")
    for condition, relative in manifest["materials"].items():
        path = FIXTURE / relative
        if not path.is_file():
            raise SystemExit(f"missing material: {relative}")
        text = path.read_text(encoding="utf-8").lower()
        for phrase in FORBIDDEN:
            if phrase.lower() in text:
                raise SystemExit(f"condition material leaks forbidden content: {condition}")
    cells = len(conditions) * len(tasks) * variants
    if cells != 45:
        raise SystemExit(f"unexpected matrix size: {cells}")
    required_gates = set(manifest["required_gates"])
    if required_gates != {"scope", "source-trace", "human-review", "no-auto-promotion"}:
        raise SystemExit("required gates changed")
    print("procedural-memory protocol validation passed")
    print(f"fixture={manifest['fixture_id']} cells={cells} conditions={len(conditions)} tasks={len(tasks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
