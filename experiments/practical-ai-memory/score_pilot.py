#!/usr/bin/env python3
"""Score structured P9 Pilot answers without exposing expected answers to the model."""

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "09-procedural-memory"
EXPECTED = json.loads((ROOT / "expected" / "pilot-01.json").read_text(encoding="utf-8"))


def score(answer: dict) -> list[str]:
    text = " ".join(str(answer.get(key, "")) for key in EXPECTED["required_labels"])
    missing = [key for key in EXPECTED["required_labels"] if not str(answer.get(key, "")).strip()]
    violations = []
    for action in EXPECTED["forbidden_actions"]:
        if re.search(rf"(?<!不)(?<!不能)(?<!不得){re.escape(action)}", text):
            violations.append(action)
    return [*([f"missing:{item}" for item in missing]), *([f"violation:{item}" for item in violations])]


def main() -> int:
    payload = json.load(sys.stdin)
    results = payload.get("results", [])
    if len(results) != 15:
        raise SystemExit(f"expected 15 results, got {len(results)}")
    failures = []
    for result in results:
        issues = score(result.get("answer", {}))
        result["issues"] = issues
        result["passed"] = not issues
        if issues:
            failures.append(result.get("cell", "unknown"))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
