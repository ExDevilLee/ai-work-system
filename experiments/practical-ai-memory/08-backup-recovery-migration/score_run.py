#!/usr/bin/env python3
"""Mechanical rubric scorer for POC 08 runs.

For each task the rubric defines ``required_any`` (groups of keyword alternatives
where at least one phrase per group must appear) and ``forbidden`` (phrases that
must NOT appear).  The scorer checks ``final.md`` case-insensitively.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
RUBRIC_PATH = ROOT / "rubrics" / "pilot-01.json"


def load_rubric() -> dict[str, Any]:
    return json.loads(RUBRIC_PATH.read_text(encoding="utf-8"))


def _phrase_present(text_lower: str, phrase: str) -> bool:
    """Case-insensitive substring or regex match."""
    try:
        return re.search(phrase, text_lower, re.IGNORECASE) is not None
    except re.error:
        return phrase.lower() in text_lower


NEGATION_MARKERS = (
    "not ", "must not", "do not", "should not", "shall not", "cannot",
    "forbidden", "no ", "never ", "without ",
    "must not be", "do not ", "prohibited",
)


def _forbidden_is_affirmative(text_lower: str, phrase: str) -> bool:
    """Return True only if *phrase* appears in a non-negated (affirmative) context.

    A match is considered negated (and thus NOT a violation) when a negation
    marker appears within 80 characters before it.  This prevents penalising
    correct answers that state an action is forbidden.
    """
    try:
        matches = list(re.finditer(phrase, text_lower, re.IGNORECASE))
    except re.error:
        matches = []
        idx = text_lower.find(phrase.lower())
        while idx != -1:
            matches.append(type("M", (), {"start": idx, "end": idx + len(phrase)})())
            idx = text_lower.find(phrase.lower(), idx + 1)
    for match in matches:
        before = text_lower[max(0, match.start() - 120):match.start()]
        after = text_lower[match.end():match.end() + 60]
        if not any(neg in before for neg in NEGATION_MARKERS) and not any(neg in after for neg in NEGATION_MARKERS):
            return True
    return False


def score_text(text: str, task: str, rubric: dict[str, Any] | None = None) -> dict[str, Any]:
    """Score *text* against the rubric for *task*. Returns detailed results."""
    if rubric is None:
        rubric = load_rubric()
    entry = rubric.get(task)
    if entry is None:
        return {"task": task, "error": f"no rubric entry for task {task}"}

    text_lower = text.lower()
    required_any = entry.get("required_any", {})
    forbidden = entry.get("forbidden", [])

    # Check each required_any group: at least one phrase must match.
    group_results: list[dict[str, Any]] = []
    all_groups_pass = True
    for group_key, phrases in required_any.items():
        matched = [p for p in phrases if _phrase_present(text_lower, p)]
        passed = len(matched) > 0
        if not passed:
            all_groups_pass = False
        group_results.append({
            "group": group_key,
            "passed": passed,
            "matched_phrases": matched,
        })

    # Check forbidden phrases: only affirmative (non-negated) occurrences count.
    forbidden_hits = [
        p for p in forbidden if _forbidden_is_affirmative(text_lower, p)
    ]
    no_forbidden = len(forbidden_hits) == 0

    overall_pass = all_groups_pass and no_forbidden
    max_score = len(required_any)
    achieved = sum(1 for g in group_results if g["passed"])
    return {
        "task": task,
        "overall_pass": overall_pass,
        "score": achieved,
        "max_score": max_score,
        "groups": group_results,
        "forbidden_hits": forbidden_hits,
        "forbidden_violation": not no_forbidden,
    }


def score_run(run_dir: Path, rubric: dict[str, Any] | None = None) -> dict[str, Any]:
    """Score a single run directory by reading metadata + final.md."""
    if rubric is None:
        rubric = load_rubric()
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    task = metadata["task"]
    final_text = (run_dir / "final.md").read_text(encoding="utf-8")
    result = score_text(final_text, task, rubric)
    result["run_name"] = metadata.get("run_name", "")
    result["condition"] = metadata.get("condition", "")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Score a POC 08 run against the rubric.")
    parser.add_argument("run_dir", type=Path, help="Path to the run directory")
    args = parser.parse_args()

    if not args.run_dir.is_dir():
        print(f"error: {args.run_dir} is not a directory", file=sys.stderr)
        return 1
    result = score_run(args.run_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
