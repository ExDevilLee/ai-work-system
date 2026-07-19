#!/usr/bin/env python3
"""Build the compact evidence package committed with this POC."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LOCAL_PUBLIC = ROOT / "runs" / "public" / "macos"
OUTPUT = ROOT / "evidence"
INVALID_BASELINE = "pilot-02-reference-retrieval-baseline"
REPRESENTATIVE_RUNS = (
    "formal-01-current-task-baseline",
    "formal-01-current-task-layered",
    "formal-01-stable-rules-baseline",
    "formal-01-stable-rules-layered",
    "formal-01-reference-retrieval-baseline",
    "formal-01-reference-retrieval-layered",
    "pilot-02-reference-retrieval-baseline",
    "pilot-02-reference-retrieval-layered",
    "model-terra-01-reference-retrieval-baseline",
    "model-terra-01-reference-retrieval-layered",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture_reference(run_name: str, condition: str) -> str:
    if run_name == INVALID_BASELINE:
        return "../../fixtures/pilot-02-invalid-baseline"
    return f"../../../fixtures/pilot-02/{condition}"


def without_line_suffix(value: str) -> str:
    return re.sub(r":\d+$", "", value)


def manifest_record(run_dir: Path) -> dict[str, object]:
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    score = json.loads((run_dir / "score.json").read_text(encoding="utf-8"))
    run_name = metadata["run_name"]
    representative = run_name in REPRESENTATIVE_RUNS
    return {
        "run_name": run_name,
        "purpose": metadata.get("purpose"),
        "task": metadata.get("task"),
        "condition": metadata.get("condition"),
        "model": metadata.get("requested_model"),
        "reasoning_effort": metadata.get("reasoning_effort"),
        "model_record_status": metadata.get("model_record_status"),
        "codex_version": metadata.get("codex_version"),
        "fixture_sha256": metadata.get("fixture_sha256"),
        "prompt_sha256": metadata.get("prompt_sha256"),
        "exit_code": metadata.get("exit_code"),
        "elapsed_seconds": metadata.get("elapsed_seconds"),
        "usage": metadata.get("usage"),
        "workspace_command_calls": metadata.get("workspace_command_calls"),
        "mixed_scope_command_calls": metadata.get("mixed_scope_command_calls"),
        "workspace_output_bytes_reliable": metadata.get(
            "workspace_output_bytes_reliable"
        ),
        "workspace_metric_coverage_complete": metadata.get(
            "workspace_metric_coverage_complete"
        ),
        "workspace_metric_unmeasured_tool_calls": metadata.get(
            "workspace_metric_unmeasured_tool_calls"
        ),
        "workspace_mcp_tool_calls": metadata.get("workspace_mcp_tool_calls"),
        "workspace_mcp_output_bytes": metadata.get("workspace_mcp_output_bytes"),
        "mixed_scope_adjusted_bytes": metadata.get("mixed_scope_adjusted_bytes"),
        "workspace_output_bytes": metadata.get("workspace_output_bytes"),
        "score": score,
        "representative_path": (
            f"representative-runs/{run_name}" if representative else None
        ),
    }


def build_representative(run_name: str) -> None:
    source = LOCAL_PUBLIC / run_name
    metadata = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
    condition = metadata["condition"]
    task = metadata["task"]
    target = OUTPUT / "representative-runs" / run_name
    target.mkdir(parents=True)

    fixture_ref = fixture_reference(run_name, condition)
    prompt_ref = f"../../../prompts/{task}.md"
    final_text = (source / "final.md").read_text(encoding="utf-8")
    final_text = re.sub(
        r"\]\(fixture-snapshot/([^)]*)\)",
        lambda match: f"]({fixture_ref}/{without_line_suffix(match.group(1))})",
        final_text,
    )
    (target / "final.md").write_text(final_text, encoding="utf-8")

    for name in ("metadata.json", "score.json", "events-summary.json"):
        shutil.copy2(source / name, target / name)

    reproduce = (
        "# 复现入口\n\n"
        f"- 夹具：[`{fixture_ref}`]({fixture_ref})\n"
        f"- 提示：[`{prompt_ref}`]({prompt_ref})\n"
        f"- 夹具 SHA-256：`{metadata['fixture_sha256']}`\n"
        f"- 提示 SHA-256：`{metadata['prompt_sha256']}`\n\n"
        "本目录只保留代表性回答、评分、元数据和命令摘要。"
        "完整运行集合压缩记录在 [`../../manifest.jsonl`](../../manifest.jsonl)。\n"
    )
    (target / "REPRODUCE.md").write_text(reproduce, encoding="utf-8")


def main() -> int:
    run_dirs = sorted(path for path in LOCAL_PUBLIC.iterdir() if path.is_dir())
    if len(run_dirs) != 36:
        raise SystemExit(f"expected 36 local public runs, found {len(run_dirs)}")
    missing = [name for name in REPRESENTATIVE_RUNS if not (LOCAL_PUBLIC / name).is_dir()]
    if missing:
        raise SystemExit(f"missing representative runs: {missing}")

    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    (OUTPUT / "representative-runs").mkdir(parents=True)
    invalid_fixture = OUTPUT / "fixtures" / "pilot-02-invalid-baseline"
    shutil.copytree(
        LOCAL_PUBLIC / INVALID_BASELINE / "fixture-snapshot",
        invalid_fixture,
    )

    manifest_path = OUTPUT / "manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8") as handle:
        for run_dir in run_dirs:
            handle.write(
                json.dumps(manifest_record(run_dir), ensure_ascii=False, separators=(",", ":"))
                + "\n"
            )

    for run_name in REPRESENTATIVE_RUNS:
        build_representative(run_name)

    readme = """# 公开实验依据

本目录是从 36 份本地脱敏运行记录中生成的精简公开包。

- `manifest.jsonl`：记录全部 36 次运行的模型配置、评分、指标和校验和。
- `representative-runs/`：保留 10 个代表样本，包括一轮完整正式对照、一次无效协议和一次模型差异对照。
- `fixtures/pilot-02-invalid-baseline/`：保留首次参考资料实验的不等价夹具，用于解释为什么该运行被判为无效。

正式夹具位于 `../fixtures/pilot-02/`，提示位于 `../prompts/`，不在每个运行目录中重复复制。完整原始事件只保留在本地私有区，不进入 Git。
"""
    (OUTPUT / "README.md").write_text(readme, encoding="utf-8")
    print(f"built {manifest_path} with {len(run_dirs)} records")
    print(f"representative runs: {len(REPRESENTATIVE_RUNS)}")
    print(f"manifest sha256: {sha256(manifest_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
