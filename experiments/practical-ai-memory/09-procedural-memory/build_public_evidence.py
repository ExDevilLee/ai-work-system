#!/usr/bin/env python3
"""Build P9's compact public evidence package from sanitized Pilot records."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "runs" / "public" / "deepseek-v4-flash-max"
PRIVATE_METADATA = (
    ROOT
    / "runs"
    / "private"
    / "deepseek-v4-flash-max"
    / "requested-observed-metadata.json"
)
EVIDENCE = ROOT / "evidence"
FIXTURE = ROOT / "fixtures" / "pilot-01"
CONDITIONS = ("prompt-only", "guide-assisted", "skill-workflow")
REPRESENTATIVE_TASKS = ("apply-scope", "recover-failure", "distill-candidate")
AGGREGATE_RECORDS = (
    ("terra-pilot-01-initial", "pilot-01-review.md", 45, 28, 17),
    ("terra-pilot-01-repair", "pilot-01-repair-review.md", 18, 17, 1),
    ("terra-pilot-01-final-repair", "pilot-01-final-repair-review.md", 1, 1, 0),
    ("terra-pilot-02-initial", "pilot-02-review.md", 45, 42, 3),
    ("terra-pilot-02-repair", "pilot-02-repair-review.md", 3, 3, 0),
)
SENSITIVE_PATTERNS = (
    re.compile(r"/Users/"),
    re.compile(r"[A-Za-z]:[\\/]+Users[\\/]"),
    re.compile(r'"thread_id"\s*:'),
    re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"provider_label", re.IGNORECASE),
)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value or "cell"


def load_tasks() -> tuple[dict[str, int], dict[str, tuple[str, int]]]:
    payload = json.loads((FIXTURE / "tasks.json").read_text(encoding="utf-8"))
    task_order: dict[str, int] = {}
    cells: dict[str, tuple[str, int]] = {}
    for task_index, task in enumerate(payload["tasks"], start=1):
        task_id = task["id"]
        task_order[task_id] = task_index
        for variant_index, variant in enumerate(task["variants"], start=1):
            cells[f"{task_id}｜{variant}"] = (task_id, variant_index)
    return task_order, cells


def condition_payload(condition: str) -> tuple[Path, dict[str, object]]:
    path = PUBLIC / f"p9-deepseek-v4-flash-max-{condition}.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def representative_path(condition: str, task: str, variant_index: int) -> str | None:
    if task not in REPRESENTATIVE_TASKS or variant_index != 1:
        return None
    return f"representative-runs/{task}-{condition}"


def build_cell_records() -> list[dict[str, object]]:
    metadata = json.loads(PRIVATE_METADATA.read_text(encoding="utf-8"))
    task_order, expected_cells = load_tasks()
    records = []
    review_sha = sha256(ROOT.parent / "review_pilot.py")

    for condition in CONDITIONS:
        source_path, payload = condition_payload(condition)
        results = payload.get("results", [])
        if len(results) != 15:
            raise SystemExit(f"{condition}: expected 15 results, found {len(results)}")
        actual_cells = [result.get("cell") for result in results]
        if actual_cells != list(expected_cells):
            raise SystemExit(f"{condition}: cell order differs from frozen tasks.json")

        material = FIXTURE / "materials" / f"{condition}.md"
        for result in results:
            cell = str(result["cell"])
            task, variant_index = expected_cells[cell]
            answer = result["answer"]
            records.append(
                {
                    "record_type": "cell",
                    "run_name": (
                        f"sensitivity-{slug(condition)}-"
                        f"{task_order[task]:02d}-{slug(task)}-{variant_index:02d}"
                    ),
                    "dataset": "second-model-sensitivity",
                    "fixture_set": "pilot-01",
                    "condition": condition,
                    "task": task,
                    "variant_index": variant_index,
                    "cell": cell,
                    "requested_model": metadata["requested_model"],
                    "requested_effort": metadata["requested_effort"],
                    "observed_model": metadata["observed_model"],
                    "observed_effort": metadata["observed_effort"],
                    "platform": metadata["platform"],
                    "sandbox": metadata["sandbox"],
                    "session": metadata["session"],
                    "condition_retries": metadata["condition_runs"][condition]["retries"],
                    "review": {
                        "status": "passed",
                        "rubric": "scope-source-human-review-no-auto-promotion",
                        "review_script_sha256": review_sha,
                    },
                    "tasks_sha256": sha256(FIXTURE / "tasks.json"),
                    "material_sha256": sha256(material),
                    "source_batch_sha256": sha256(source_path),
                    "answer_sha256": sha256_bytes(canonical_json(answer)),
                    "representative_path": representative_path(
                        condition, task, variant_index
                    ),
                }
            )
    return records


def build_aggregate_records() -> list[dict[str, object]]:
    aggregate_root = ROOT / "runs" / "aggregates" / "macos"
    records = []
    for name, filename, reviewed, passed, failed in AGGREGATE_RECORDS:
        path = aggregate_root / filename
        records.append(
            {
                "record_type": "aggregate-review",
                "run_name": name,
                "dataset": name.removeprefix("terra-"),
                "requested_model": "gpt-5.6-terra",
                "requested_effort": "medium",
                "observed_model": "gpt-5.6-terra",
                "observed_effort": "medium",
                "platform": "macOS",
                "sandbox": "read-only",
                "session": "ephemeral",
                "reviewed_cells": reviewed,
                "passed_cells": passed,
                "failed_cells": failed,
                "source_record_status": "aggregate-only",
                "source_record_note": (
                    "The original temporary cell JSON was not retained in the P9 "
                    "public/private run directories; this record must not be treated "
                    "as a cell-level reproducibility claim."
                ),
                "evidence_path": f"../runs/aggregates/macos/{filename}",
                "evidence_sha256": sha256(path),
                "representative_path": None,
            }
        )
    return records


def build_representatives(records: list[dict[str, object]]) -> None:
    by_key = {
        (record["condition"], record["cell"]): record
        for record in records
        if record["record_type"] == "cell"
    }
    _, expected_cells = load_tasks()
    first_cells = {
        task: cell
        for cell, (task, variant_index) in expected_cells.items()
        if task in REPRESENTATIVE_TASKS and variant_index == 1
    }

    for condition in CONDITIONS:
        _, payload = condition_payload(condition)
        results = {result["cell"]: result for result in payload["results"]}
        for task in REPRESENTATIVE_TASKS:
            cell = first_cells[task]
            record = by_key[(condition, cell)]
            target = EVIDENCE / str(record["representative_path"])
            target.mkdir(parents=True)
            answer = results[cell]["answer"]
            (target / "final.json").write_text(
                json.dumps(
                    {"cell": cell, "answer": answer}, ensure_ascii=False, indent=2
                )
                + "\n",
                encoding="utf-8",
            )
            public_metadata = {
                key: record[key]
                for key in (
                    "run_name",
                    "dataset",
                    "fixture_set",
                    "condition",
                    "task",
                    "variant_index",
                    "requested_model",
                    "requested_effort",
                    "observed_model",
                    "observed_effort",
                    "platform",
                    "sandbox",
                    "session",
                    "review",
                    "tasks_sha256",
                    "material_sha256",
                    "answer_sha256",
                )
            }
            (target / "metadata.json").write_text(
                json.dumps(public_metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (target / "REPRODUCE.md").write_text(
                "# 代表样本复核入口\n\n"
                f"- 任务表：[`../../fixtures/tasks.json`](../../fixtures/tasks.json)\n"
                f"- 条件材料：[`../../fixtures/materials/{condition}.md`](../../fixtures/materials/{condition}.md)\n"
                "- 全量记录：[`../../manifest.jsonl`](../../manifest.jsonl)\n\n"
                "`final.json` 是脱敏后的单格 final。`metadata.json` 记录请求/观察配置、"
                "边界 Review 结果和校验和；它不包含会话标识、绝对路径或执行平台凭据。\n",
                encoding="utf-8",
            )


def write_claim_matrix() -> None:
    (EVIDENCE / "claim-matrix.md").write_text(
        "# P9 公开主张矩阵\n\n"
        "| 可公开主张 | 证据 | 允许程度 | 不允许外推 |\n"
        "| --- | --- | --- | --- |\n"
        "| 在第二模型配置的冻结 Pilot-01 中，三条件共 45 格均通过逐份边界 Review | `manifest.jsonl` 的 45 条 `cell` 记录与 9 个代表样本 | 可直接陈述 | 不等于生产率、真实任务质量或通用模型能力 |\n"
        "| Terra Pilot-01 首轮 28/45 通过，修复批次关闭已发现边界问题 | `aggregate-review` 记录与对应 Review 报告 | 只能按聚合历史陈述 | 原始临时 JSON 未保留，不能声称公开包支持逐格复算 |\n"
        "| Terra Pilot-02 首轮 42/45 通过，3 个失败均来自 `prompt-only` 恢复任务的范围表达，修复后 3/3 通过 | Pilot-02 聚合 Review 与修复报告 | 可按报告陈述 | 不代表 `guide-assisted` 或 `skill-workflow` 普遍优于提示词 |\n"
        "| 两组配置出现不同首轮边界结果 | 分配置报告 | 只能称为配置敏感性信号 | 不能把差异归因于模型、推理强度或执行路径中的单一变量 |\n"
        "| 程序性记忆应保留范围、来源、人工门和禁止自动晋升 | 冻结协议与两组 Review 门禁 | 可作为本 POC 的设计结论 | 不能写成所有团队和工具的通用最佳实践 |\n"
        "| Windows 或真实项目已经验证 | 无 | 禁止 | 本 POC 只覆盖 macOS 合成任务 |\n",
        encoding="utf-8",
    )


def write_readme() -> None:
    (EVIDENCE / "README.md").write_text(
        "# P9 公开实验依据\n\n"
        "本目录公开 P9「程序性记忆」在 macOS 合成任务上的可复查证据。两组模型配置始终分开记录，不合并成总分，也不比较运行平台提供方。\n\n"
        "## 内容\n\n"
        "- `manifest.jsonl`：45 条第二模型逐格记录，加 5 条 Terra 聚合 Review 记录。\n"
        "- `representative-runs/`：9 个脱敏代表样本，覆盖范围限定、失败恢复和候选沉淀三类高风险任务，以及全部三种条件。\n"
        "- `fixtures/`：冻结任务表、条件材料和实验 manifest。\n"
        "- `claim-matrix.md`：文章可以使用与不得外推的主张边界。\n\n"
        "## 证据完整性边界\n\n"
        "第二模型的 45 格脱敏 final 仍在本机中间层，公开 manifest 可逐格校验并展开代表样本。Terra Pilot 的原始 final 当时写入临时目录，未进入 P9 的 `runs/private/` 或 `runs/public/`；当前只保留逐份 Review、修复 Review 与分析报告。因此 manifest 将这些历史记录明确标为 `aggregate-only`，不补造逐格输出或校验和。\n\n"
        "这不影响文章讨论“程序性记忆需要哪些边界”，但会限制复现口径：公开包支持第二模型逐格复核，只支持 Terra 聚合结果审计。文章进入 `ready` 前，应由人工确认是否接受这一历史证据缺口。\n\n"
        "## 本地验证\n\n"
        "```bash\n"
        "python3 validate_design.py\n"
        "python3 validate_protocol.py\n"
        "python3 validate_public_evidence.py\n"
        "```\n\n"
        "这些命令只读取合成夹具和公开证据，不会调用模型、修改真实项目或访问私有记忆。\n",
        encoding="utf-8",
    )


def scan_sensitive() -> list[str]:
    failures = []
    for path in EVIDENCE.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in SENSITIVE_PATTERNS:
            if pattern.search(text):
                failures.append(f"{path.relative_to(EVIDENCE)}: {pattern.pattern}")
    return failures


def main() -> int:
    if not PRIVATE_METADATA.is_file():
        raise SystemExit("missing requested/observed metadata")
    if EVIDENCE.exists():
        shutil.rmtree(EVIDENCE)
    (EVIDENCE / "representative-runs").mkdir(parents=True)
    shutil.copytree(FIXTURE, EVIDENCE / "fixtures")

    records = build_cell_records() + build_aggregate_records()
    with (EVIDENCE / "manifest.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(
                json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            )
    build_representatives(records)
    write_claim_matrix()
    write_readme()

    failures = scan_sensitive()
    if failures:
        shutil.rmtree(EVIDENCE)
        raise SystemExit("sanitization failed:\n" + "\n".join(failures))
    print("built cell_records=45 aggregate_records=5 representatives=9")
    print(f"manifest_sha256={sha256(EVIDENCE / 'manifest.jsonl')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
