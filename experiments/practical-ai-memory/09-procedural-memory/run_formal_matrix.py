#!/usr/bin/env python3
"""Run one P9 formal matrix as isolated 15-cell condition batches."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "formal-01"
MATERIALS = ROOT / "fixtures" / "pilot-01" / "materials"
CONDITIONS = ("prompt-only", "guide-assisted", "skill-workflow")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prompt_for(condition: str) -> str:
    tasks = json.loads((FIXTURE / "tasks.json").read_text(encoding="utf-8"))
    material = (MATERIALS / f"{condition}.md").read_text(encoding="utf-8")
    return f'''You are evaluating one isolated synthetic procedural-memory condition.
Condition: {condition}

<condition_material>
{material}
</condition_material>

<tasks_json>
{json.dumps(tasks, ensure_ascii=False, sort_keys=True)}
</tasks_json>

Return only one valid JSON object with a "results" array in the exact task and variant order.
Return exactly 15 results. Each result must be {{"cell":"task-id｜variant text","answer":{{"scope":"...","source":"...","human_review":"...","refuse_automatic":"..."}}}}.
Use Chinese. Every scope must start with one of 仅限、仅覆盖、限定、只处理、仅形成 and stay at the task's smallest stated boundary. Every source must identify the current synthetic task/condition evidence without inventing files. Every human_review must start with 人工 Review and name the decision a person still owns. Every refusal must explicitly say it does not automatically modify facts, promote a rule, or expand scope.
For recover-failure, stop on missing dependency/evidence or conflict and leave the decision to human Review; do not claim recovery succeeded. For distill-candidate, produce only a candidate and never an approved rule. Do not perform actions, use tools, infer hidden condition material, or mention local paths, credentials, sessions, providers, expected answers, or rubric text.'''


def valid_payload(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    results = payload.get("results")
    return isinstance(results, list) and len(results) == 15


def extract_omp_final(events_text: str) -> str:
    """Extract the last assistant text from OMP JSONL without guessing braces."""
    final = ""
    for line in events_text.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") not in {"message_end", "turn_end"}:
            continue
        message = event.get("message") or {}
        if message.get("role") != "assistant":
            continue
        text_parts = [part.get("text", "") for part in message.get("content", []) if part.get("type") == "text"]
        if text_parts:
            final = "".join(text_parts)
    return final


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-model", required=True)
    parser.add_argument("--cli-model", required=True, help="runtime selector; never persisted")
    parser.add_argument("--reasoning-effort", required=True)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--executor", choices=("omp", "codex"), default="omp")
    parser.add_argument("--max-time", type=int, default=300)
    args = parser.parse_args()
    tasks_sha = sha256(FIXTURE / "tasks.json")
    failures = 0
    for repeat in range(1, 4):
        order = CONDITIONS[repeat - 1:] + CONDITIONS[:repeat - 1]
        for condition in order:
            run_name = f"{args.run_label}-{repeat:02d}-{condition}"
            run_dir = ROOT / "runs" / "private" / "formal" / run_name
            final_path = run_dir / "final.json"
            metadata_path = run_dir / "metadata.json"
            if metadata_path.is_file() and valid_payload(final_path):
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                if (metadata.get("requested_model"), metadata.get("requested_effort"), metadata.get("tasks_sha256")) != (args.public_model, args.reasoning_effort, tasks_sha):
                    raise SystemExit(f"identity mismatch: {run_name}")
                print(f"SKIP {run_name}", flush=True)
                continue
            if run_dir.exists():
                raise SystemExit(f"incomplete run directory: {run_name}")
            run_dir.mkdir(parents=True)
            prompt = prompt_for(condition)
            (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
            if args.executor == "omp":
                command = ["omp", "-p", "--mode", "json", "--model", args.cli_model, "--thinking", args.reasoning_effort, "--no-session", "--no-skills", "--no-rules", "--no-tools", "--max-time", str(args.max_time), prompt]
            else:
                command = ["codex", "exec", "-C", str(run_dir), "-m", args.cli_model, "-c", f"model_reasoning_effort={args.reasoning_effort}", "-s", "read-only", "--ephemeral", "--skip-git-repo-check", "--output-last-message", str(run_dir / "codex-final.json"), prompt]
            started = datetime.now(timezone.utc)
            before = time.monotonic()
            try:
                result = subprocess.run(command, cwd=run_dir, text=True, encoding="utf-8", capture_output=True, timeout=args.max_time + 30, check=False)
                exit_code, stdout, stderr = result.returncode, result.stdout, result.stderr
            except subprocess.TimeoutExpired as error:
                exit_code, stdout, stderr = 124, error.stdout or "", error.stderr or ""
                if isinstance(stdout, bytes): stdout = stdout.decode("utf-8", errors="replace")
                if isinstance(stderr, bytes): stderr = stderr.decode("utf-8", errors="replace")
                stderr += "\nrunner timeout\n"
            elapsed = round(time.monotonic() - before, 6)
            (run_dir / "stderr.txt").write_text(stderr, encoding="utf-8")
            if args.executor == "omp":
                (run_dir / "events.jsonl").write_text(stdout, encoding="utf-8")
                stdout = extract_omp_final(stdout)
            elif (run_dir / "codex-final.json").is_file():
                stdout = (run_dir / "codex-final.json").read_text(encoding="utf-8")
            final_path.write_text(stdout.strip() + ("\n" if stdout.strip() else ""), encoding="utf-8")
            metadata = {
                "run_name": run_name, "fixture_set": "formal-01", "repeat": repeat,
                "condition": condition, "requested_model": args.public_model,
                "requested_effort": args.reasoning_effort, "observed_model": "unknown",
                "observed_effort": "unknown", "execution_path": f"{args.executor}-cli",
                "platform": platform.platform(), "platform_tag": "macos",
                "protocol_environment_isolated": True, "exit_code": exit_code,
                "final_answer_present": bool(stdout.strip()), "elapsed_seconds": elapsed,
                "started_at_utc": started.isoformat(), "tasks_sha256": tasks_sha,
                "material_sha256": sha256(MATERIALS / f"{condition}.md"),
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "command_shape": ("omp JSONL events; final extracted from assistant event; no session, skills, rules, or tools; private selector omitted" if args.executor == "omp" else "codex exec; read-only, ephemeral, isolated run directory; private selector omitted")
            }
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            ok = exit_code == 0 and valid_payload(final_path)
            print(f"{'PASS' if ok else 'FAIL'} {run_name} elapsed={elapsed}", flush=True)
            failures += 0 if ok else 1
    print(f"formal condition batches complete: failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
