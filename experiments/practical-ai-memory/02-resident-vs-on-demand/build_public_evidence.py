#!/usr/bin/env python3
"""Build a compact, sanitized evidence package from private formal runs."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PRIVATE = ROOT / "runs" / "private" / "macos"
OUTPUT = ROOT / "evidence"
CONDITIONS = ("all-resident", "selective-resident", "index-only")
TASKS = ("critical-boundary", "reference-detail", "volatile-state", "status-conflict")
REPRESENTATIVE_RUNS = tuple(
    f"formal-01-{task}-{condition}" for task in TASKS for condition in CONDITIONS
)
SENSITIVE_PATTERNS = (
    re.compile(r"/Users/"),
    re.compile(r"(?:/private)?/var/folders/"),
    re.compile(r"[A-Za-z]:(?:\\\\|\\|/)Users(?:\\\\|\\|/)"),
    re.compile(r'"thread_id"'),
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile("msu" + "tools", re.IGNORECASE),
    re.compile("pro" + "vider" + "_label", re.IGNORECASE),
)
PUBLIC_METADATA_KEYS = (
    "run_name",
    "condition",
    "fixture_set",
    "task",
    "purpose",
    "started_at_utc",
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
    "workspace_mcp_tool_calls",
    "workspace_mcp_output_bytes",
    "mixed_scope_adjusted_bytes",
    "workspace_output_bytes",
    "resident_instruction_bytes",
    "project_context_bytes_reliable",
    "project_context_bytes",
    "command_shape",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def without_line_suffix(value: str) -> str:
    return re.sub(r":\d+$", "", value)


def sanitize_final(text: str, condition: str) -> str:
    text = re.sub(
        r"\]\([^)]*/workspace/([^)]*)\)",
        lambda match: (
            f"](../../fixtures/{condition}/{without_line_suffix(match.group(1))})"
        ),
        text,
    )
    text = re.sub(r"/Users/[^/\s]+/[^\s\"']*", "<redacted-user-path>", text)
    text = re.sub(r"/var/folders/[^\s\"')]+", "<redacted-temp-path>", text)
    text = re.sub(r"(?m)^(\s*)\d+\.(?=\s)", r"\g<1>1.", text)
    text = re.sub(r"[ \t]+(?=\n|$)", "", text)
    return "# 模型最终回答\n\n" + text.rstrip() + "\n"


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_metadata(metadata: dict[str, object]) -> dict[str, object]:
    return {key: metadata.get(key) for key in PUBLIC_METADATA_KEYS}


def event_summary(run_dir: Path) -> dict[str, object]:
    events = [
        json.loads(line)
        for line in (run_dir / "raw.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    event_types = Counter(event.get("type", "unknown") for event in events)
    completed_items = Counter()
    for event in events:
        if event.get("type") == "item.completed":
            completed_items[event.get("item", {}).get("type", "unknown")] += 1
    return {
        "raw_event_count": len(events),
        "event_type_counts": dict(sorted(event_types.items())),
        "completed_item_type_counts": dict(sorted(completed_items.items())),
        "raw_jsonl_publication": (
            "withheld because it contains local paths, thread identifiers, "
            "and unrelated runtime context"
        ),
    }


def manifest_record(run_dir: Path) -> dict[str, object]:
    metadata = load_json(run_dir / "metadata.json")
    score = load_json(run_dir / "score.json")
    run_name = str(metadata["run_name"])
    return {
        **safe_metadata(metadata),
        "score": score,
        "representative_path": (
            f"representative-runs/{run_name}" if run_name in REPRESENTATIVE_RUNS else None
        ),
    }


def build_representative(run_name: str) -> None:
    source = PRIVATE / run_name
    metadata = load_json(source / "metadata.json")
    condition = str(metadata["condition"])
    task = str(metadata["task"])
    target = OUTPUT / "representative-runs" / run_name
    target.mkdir(parents=True)

    (target / "final.md").write_text(
        sanitize_final((source / "final.md").read_text(encoding="utf-8"), condition),
        encoding="utf-8",
    )
    (target / "metadata.json").write_text(
        json.dumps(safe_metadata(metadata), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    shutil.copy2(source / "score.json", target / "score.json")
    (target / "events-summary.json").write_text(
        json.dumps(event_summary(source), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    fixture_ref = f"../../fixtures/{condition}"
    prompt_ref = f"../../../prompts/{task}.md"
    (target / "REPRODUCE.md").write_text(
        "# 复现入口\n\n"
        f"- 夹具：[`{fixture_ref}`]({fixture_ref})\n"
        f"- 提示：[`{prompt_ref}`]({prompt_ref})\n"
        f"- 夹具 SHA-256：`{metadata['fixture_sha256']}`\n"
        f"- 提示 SHA-256：`{metadata['prompt_sha256']}`\n\n"
        "本目录只保留代表性回答、评分、公开元数据和事件数量摘要。"
        "全部正式运行记录在 [`../../manifest.jsonl`](../../manifest.jsonl)。\n",
        encoding="utf-8",
    )


def scan_sensitive() -> list[str]:
    failures = []
    for path in OUTPUT.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in SENSITIVE_PATTERNS:
            if pattern.search(text):
                failures.append(f"{path.relative_to(OUTPUT)}: {pattern.pattern}")
    return failures


def main() -> int:
    run_dirs = sorted(path for path in PRIVATE.glob("formal-*") if path.is_dir())
    if len(run_dirs) != 36:
        raise SystemExit(f"expected 36 private formal runs, found {len(run_dirs)}")
    if any(not (path / "score.json").is_file() for path in run_dirs):
        raise SystemExit("all private formal runs must be reviewed before export")
    missing = [name for name in REPRESENTATIVE_RUNS if not (PRIVATE / name).is_dir()]
    if missing:
        raise SystemExit(f"missing representative runs: {missing}")

    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    (OUTPUT / "representative-runs").mkdir(parents=True)
    (OUTPUT / "fixtures").mkdir()

    for condition in CONDITIONS:
        source = PRIVATE / f"formal-01-critical-boundary-{condition}" / "fixture-snapshot"
        shutil.copytree(source, OUTPUT / "fixtures" / condition)

    manifest = OUTPUT / "manifest.jsonl"
    with manifest.open("w", encoding="utf-8") as handle:
        for run_dir in run_dirs:
            handle.write(
                json.dumps(manifest_record(run_dir), ensure_ascii=False, separators=(",", ":"))
                + "\n"
            )

    for run_name in REPRESENTATIVE_RUNS:
        build_representative(run_name)

    (OUTPUT / "README.md").write_text(
        "# 公开实验依据\n\n"
        "本目录由 36 份 macOS 私有正式运行记录脱敏生成。\n\n"
        "- `manifest.jsonl`：覆盖全部 36 次运行的模型配置、评分、指标和校验和。\n"
        "- `representative-runs/`：保留第 1 轮全部 12 个任务与条件组合。\n"
        "- `fixtures/`：按三种条件去重保留真实运行夹具。\n\n"
        "提示位于 `../prompts/`。原始 `raw.jsonl`、绝对路径、会话标识和私有运行内容不进入 Git。\n",
        encoding="utf-8",
    )

    failures = scan_sensitive()
    if failures:
        shutil.rmtree(OUTPUT)
        raise SystemExit("sanitization failed:\n" + "\n".join(failures))

    print(f"built records=36 representatives={len(REPRESENTATIVE_RUNS)}")
    print(f"manifest sha256={sha256(manifest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
