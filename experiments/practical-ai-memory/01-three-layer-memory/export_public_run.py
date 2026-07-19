#!/usr/bin/env python3
"""Export a sanitized, reviewable subset of one private experiment run."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SENSITIVE_PATTERNS = (
    re.compile(r"/Users/|[A-Za-z]:(?:\\\\|\\|/)Users(?:\\\\|\\|/)"),
    re.compile(r"/var/folders/"),
    re.compile(
        r"[A-Za-z]:(?:\\\\|\\|/)(?:Windows|Users|ProgramData)(?:\\\\|\\|/)",
        re.IGNORECASE,
    ),
    re.compile(r'"thread_id"'),
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile("msu" + "tools", re.IGNORECASE),
    re.compile("pro" + "vider" + "_label", re.IGNORECASE),
)


def is_runtime_command(value: object) -> bool:
    return "/.codex/" in str(value).replace("\\", "/")


def sanitize_text(value: str) -> str:
    value = re.sub(
        r"\]\([^)]*/workspace/([^)]*)\)",
        lambda match: f"](fixture-snapshot/{match.group(1)})",
        value,
    )
    windows_path = re.compile(
        r"[A-Za-z]:(?:\\\\|\\|/)Users(?:\\\\|\\|/)"
        r"[^\\/\s\"']+(?:(?:\\\\|\\|/)[^\s\"']*)?",
        re.IGNORECASE,
    )
    windows_system_path = re.compile(
        r"[A-Za-z]:(?:\\\\|\\|/)(?:Windows|ProgramData)"
        r"(?:\\\\|\\|/)[^\s\"']*",
        re.IGNORECASE,
    )
    value = windows_path.sub("<redacted-user-path>", value)
    value = windows_system_path.sub("<redacted-system-path>", value)
    value = re.sub(r"/Users/[^/\s]+/[^\s\"']*", "<redacted-user-path>", value)
    value = re.sub(r"/var/folders/[^\s\"')]+", "<redacted-temp-path>", value)
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--platform-tag", choices=("macos", "win11"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.run_dir.resolve()
    if not source.is_dir():
        raise SystemExit(f"run directory does not exist: {source}")

    metadata = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
    platform_tag = args.platform_tag or metadata.get("platform_tag", "macos")
    destination = ROOT / "runs" / "public" / platform_tag / metadata["run_name"]
    if destination.exists():
        raise SystemExit(f"public run already exists: {destination}")
    destination.mkdir(parents=True)

    shutil.copytree(source / "fixture-snapshot", destination / "fixture-snapshot")
    shutil.copy2(source / "prompt.md", destination / "prompt.md")
    if (source / "score.json").is_file():
        shutil.copy2(source / "score.json", destination / "score.json")

    final_text = sanitize_text((source / "final.md").read_text(encoding="utf-8"))
    (destination / "final.md").write_text(final_text, encoding="utf-8")

    public_metadata_keys = (
        "run_name",
        "condition",
        "fixture_set",
        "task",
        "purpose",
        "started_at_utc",
        "platform",
        "platform_tag",
        "python_version",
        "codex_version",
        "requested_model",
        "reasoning_effort",
        "model_record_status",
        "fixture_sha256",
        "prompt_sha256",
        "sandbox",
        "ephemeral",
        "exit_code",
        "elapsed_seconds",
        "usage",
        "completed_command_calls",
        "workspace_command_calls",
        "mixed_scope_command_calls",
        "workspace_output_bytes_reliable",
        "workspace_metric_coverage_complete",
        "workspace_metric_unmeasured_tool_calls",
        "mixed_scope_adjusted_bytes",
        "workspace_output_bytes",
        "command_shape",
    )
    public_metadata = {key: metadata.get(key) for key in public_metadata_keys}
    (destination / "metadata.json").write_text(
        json.dumps(public_metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    events = [
        json.loads(line)
        for line in (source / "raw.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    event_counts = Counter(event.get("type", "unknown") for event in events)
    commands = []
    for event in events:
        item = event.get("item", {})
        if event.get("type") != "item.completed" or item.get("type") != "command_execution":
            continue
        command = item.get("command", "")
        if is_runtime_command(command):
            commands.append({"scope": "global-runtime", "command": "<omitted>"})
        else:
            commands.append({"scope": "workspace", "command": sanitize_text(command)})

    summary = {
        "raw_event_count": len(events),
        "event_type_counts": dict(sorted(event_counts.items())),
        "completed_commands": commands,
        "raw_jsonl_publication": "withheld because it contains local paths, thread identifiers, and unrelated global runtime context",
    }
    (destination / "events-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (destination / "PUBLICATION.md").write_text(
        "# 公开证据说明\n\n"
        "此目录由私有原始运行记录脱敏导出，保留夹具、提示、最终回答、评分、"
        "运行元数据和事件摘要。原始 JSONL 未公开，因为其中包含本机临时路径、"
        "会话标识和与实验无关的全局运行时内容。\n",
        encoding="utf-8",
    )

    violations = []
    for path in destination.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in SENSITIVE_PATTERNS:
            if pattern.search(text):
                violations.append(f"{path.relative_to(destination)}: {pattern.pattern}")
    if violations:
        shutil.rmtree(destination)
        raise SystemExit("sanitization failed:\n" + "\n".join(violations))

    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
