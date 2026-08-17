#!/usr/bin/env python3
"""Run one isolated 15-cell P9 condition batch through Codex."""

import argparse
import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "09-procedural-memory"
FIXTURE = ROOT / "fixtures" / "pilot-01"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("condition", choices=["prompt-only", "guide-assisted", "skill-workflow"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cells-file", type=Path)
    parser.add_argument("--tasks-file", type=Path)
    args = parser.parse_args()
    tasks_path = args.tasks_file or (FIXTURE / "tasks.json")
    tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
    selected = set()
    if args.cells_file:
        selected = set(json.loads(args.cells_file.read_text(encoding="utf-8"))[args.condition])
        for task in tasks["tasks"]:
            task["variants"] = [
                variant for variant in task["variants"]
                if f"{task['id']}｜{variant}" in selected or f"{task['id']}:{variant}" in selected
            ]
        tasks["tasks"] = [task for task in tasks["tasks"] if task["variants"]]
    material = (FIXTURE / "materials" / f"{args.condition}.md").read_text(encoding="utf-8")
    prompt = f'''You are running one isolated synthetic POC condition: {args.condition}.
Condition material:\n{material}\n
Tasks JSON:\n{json.dumps(tasks, ensure_ascii=False)}\n
For every task and every variant, return exactly one JSON object in a JSON array under key "results".
Each result must have "cell" and "answer". answer must contain scope, source, human_review, refuse_automatic.
Use Chinese. Start scope with one of: 仅限、仅覆盖、限定、只处理、仅形成. Start human_review with 人工 Review.
The refusal field must explicitly state what is not automatically modified, promoted, or expanded.
Do not edit files. Do not infer or create a permanent rule. Keep every scope narrow and require human Review.'''
    with tempfile.TemporaryDirectory() as workdir:
        final_path = Path(workdir) / "final.json"
        command = [
            "codex", "exec", "-C", workdir, "-m", "gpt-5.6-terra",
            "-c", "model_reasoning_effort=medium", "-s", "read-only", "--ephemeral",
            "--skip-git-repo-check", "--output-last-message", str(final_path), prompt,
        ]
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        final = final_path.read_text(encoding="utf-8") if final_path.exists() else ""
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(final or result.stdout or result.stderr, encoding="utf-8")
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
