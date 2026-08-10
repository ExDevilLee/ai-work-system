#!/usr/bin/env python3
"""Mechanically score the bounded Pilot coverage-gap task without exposing raw runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PRIVATE_ROOT = ROOT / "runs" / "private" / "macos"
PUBLIC_ROOT = ROOT / "runs" / "aggregates" / "macos"
CONDITIONS = ("source-only", "state-projection", "coverage-governance-projection")


def score_answer(text: str) -> dict[str, bool]:
    lowered = text.lower()
    return {
        "identifies_incident_handling": "incident-handling" in lowered,
        "states_win11_scope": "win11" in lowered,
        "explains_no_current_record": any(token in lowered for token in ("no current", "no-active-record", "没有任何对应记录", "不存在可执行")),
        "cites_manifest": "manifest.json" in lowered,
        "cites_record_sources": "records/" in lowered,
        "human_only_next_step": any(token in lowered for token in ("人工", "人类", "human")) and any(token in lowered for token in ("不创建新规则", "不新增规则", "do not create")),
        "no_automatic_mutation": not any(token in lowered for token in ("自动创建", "自动替代", "自动删除", "自动晋升")),
    }


def score_run(run_dir: Path) -> dict[str, object]:
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    answer = (run_dir / "final.md").read_text(encoding="utf-8")
    checks = score_answer(answer)
    passed = metadata["exit_code"] == 0 and metadata["final_answer_present"] and all(checks.values())
    return {"condition": metadata["condition"], "passed": passed, "checks": checks}


def render_aggregate(results: list[dict[str, object]]) -> str:
    lines = [
        "# Pilot-01 coverage-gap 最小对照聚合",
        "",
        "## 边界",
        "",
        "- 这是单个冻结任务在三种条件下各一次的可复跑 Pilot 切片，不是完整 Pilot，更不是正式矩阵。",
        "- 公开聚合不包含原始回答、逐次计时、执行器版本或具体模型标识；这些内容仅留在未跟踪的本地私有目录。",
        "- 本文只报告协议是否通过最小机械门禁，不能用于比较条件效果、模型表现或通用质量。",
        "",
        "## 机械评分结果",
        "",
        "| 条件 | 通过 | 关键检查 |",
        "| --- | --- | --- |",
    ]
    for result in results:
        checks = result["checks"]
        assert isinstance(checks, dict)
        failed = [name for name, value in checks.items() if not value]
        check_label = "全部通过" if not failed else "失败：" + ", ".join(failed)
        lines.append(f"| `{result['condition']}` | {'是' if result['passed'] else '否'} | {check_label} |")
    lines.extend([
        "",
        "## 本切片可以说明什么",
        "",
        "三种条件都完成了所要求的覆盖缺口盘点：识别 `incident-handling / win11`，说明无当前可执行记录，引用 manifest 与记录来源，并把下一步限制为人工复核、不自动改写记忆。",
        "",
        "下一步仍须完成其余四个任务、冻结人工 rubric 并在两个独立模型配置下执行各自的 Pilot；通过后才可进入正式矩阵。",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="pilot-01")
    args = parser.parse_args()
    results = []
    for condition in CONDITIONS:
        run_dir = PRIVATE_ROOT / f"{args.label}-coverage-gap-{condition}"
        if not (run_dir / "metadata.json").is_file() or not (run_dir / "final.md").is_file():
            raise SystemExit(f"missing completed run: {run_dir.name}")
        results.append(score_run(run_dir))
    PUBLIC_ROOT.mkdir(parents=True, exist_ok=True)
    aggregate = PUBLIC_ROOT / f"{args.label}-coverage-gap-slice.md"
    aggregate.write_text(render_aggregate(results), encoding="utf-8")
    if not all(bool(result["passed"]) for result in results):
        raise SystemExit("mechanical scoring failed")
    print(f"scored: runs={len(results)}, passed={len(results)}, aggregate={aggregate.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
