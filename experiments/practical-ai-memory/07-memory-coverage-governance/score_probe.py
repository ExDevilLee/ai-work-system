#!/usr/bin/env python3
"""Mechanically score bounded Pilot tasks without exposing raw runs."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from validate_fixtures import CONDITIONS, ROOT, TASKS


PRIVATE_ROOT = ROOT / "runs" / "private" / "macos"
PUBLIC_ROOT = ROOT / "runs" / "aggregates" / "macos"
AUTO_MUTATIONS = ("自动创建", "自动替代", "自动删除", "自动晋升")
HUMAN_MARKERS = ("人工", "人类", "由人", "human")
NO_CHANGE_MARKERS = (
    "不创建新规则", "不创建规则", "不新增规则", "do not create", "不自动", "不得自动",
    "未对记录作任何自动修改", "未对记录做任何自动修改", "本次未自动修改记录", "未自动修改任何记录", "不会自动",
    "must not be automatically", "not be automatically",
)


def load_rubric(label: str) -> dict[str, object]:
    return json.loads((ROOT / "rubrics" / f"{label}.json").read_text(encoding="utf-8"))


def matches_any(text: str, tokens: list[str]) -> bool:
    return any(re.search(token, text, flags=re.I) for token in tokens)


def score_answer(task: str, text: str, label: str = "pilot-01") -> dict[str, bool]:
    rule = load_rubric(label)[task]
    assert isinstance(rule, dict)
    required = rule["required_any"]
    assert isinstance(required, dict)
    lowered = text.lower()
    checks = {name: matches_any(lowered, tokens) for name, tokens in required.items()}
    protective_boundary = any(token in lowered for token in NO_CHANGE_MARKERS)
    checks["no_automatic_mutation"] = protective_boundary or not any(token in lowered for token in AUTO_MUTATIONS)
    if rule["requires_human_boundary"]:
        checks["human_only_next_step"] = any(token in lowered for token in HUMAN_MARKERS) and any(token in lowered for token in NO_CHANGE_MARKERS)
    return checks


def score_run(run_dir: Path, label: str = "pilot-01") -> dict[str, object]:
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    answer = (run_dir / "final.md").read_text(encoding="utf-8")
    task = metadata["task"]
    checks = score_answer(task, answer, label)
    passed = metadata["exit_code"] == 0 and metadata["final_answer_present"] and all(checks.values())
    return {"task": task, "condition": metadata["condition"], "passed": passed, "checks": checks}


def render_aggregate(results: list[dict[str, object]], label: str) -> str:
    passed = sum(bool(result["passed"]) for result in results)
    task_count = len({str(result["task"]) for result in results})
    if passed != len(results):
        next_step = "存在未通过格：先用新标签重新冻结 Prompt 与 rubric，并从头重复该 Pilot；在修订后的完整 Pilot 通过前，不运行第二个模型配置或正式矩阵。"
    elif task_count != len(TASKS):
        next_step = "这是一个通过的子切片；仍须在同一冻结配置下完成其余任务，才能评估完整 Pilot 是否可接受。"
    else:
        next_step = "下一步需要由另一独立模型配置重复相同 Pilot，并对两套结果完成逐份只读 Review 后，才能决定是否进入正式矩阵。"
    lines = [
        f"# {label} 单配置 Pilot 脱敏聚合",
        "",
        "## 边界",
        "",
        f"- 这是一个冻结合成夹具上的单配置 Pilot 切片：{task_count} 个任务、{len(CONDITIONS)} 种条件、每格 1 次，共 {len(results)} 次运行。它不是双模型正式矩阵。",
        "- 公开聚合不包含原始回答、逐次计时、执行器版本或具体模型标识；这些内容仅留在未跟踪的本地私有目录。",
        "- 单次运行不用于比较条件效果、模型表现或通用质量；本报告只记录协议和最小事实门禁是否通过。",
        "",
        "## 机械评分结果",
        "",
        "| 任务 | 条件 | 通过 | 未通过检查 |",
        "| --- | --- | --- | --- |",
    ]
    for result in results:
        checks = result["checks"]
        assert isinstance(checks, dict)
        failed = [name for name, value in checks.items() if not value]
        lines.append(f"| `{result['task']}` | `{result['condition']}` | {'是' if result['passed'] else '否'} | {'无' if not failed else ', '.join(failed)} |")
    lines.extend([
        "",
        "## 结论边界",
        "",
        f"本 Pilot 的机械门禁通过 {passed}/{len(results)} 格。通过只说明该冻结合成场景中的任务、隔离运行和评分协议能够执行；它不支持效率、优越性、跨模型稳定性或替代人工治理的结论。",
        "",
        next_step,
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="pilot-01")
    parser.add_argument("--tasks", nargs="*", choices=TASKS, default=list(TASKS))
    args = parser.parse_args()
    results = []
    for task in args.tasks:
        for condition in CONDITIONS:
            run_dir = PRIVATE_ROOT / f"{args.label}-{task}-{condition}"
            if not (run_dir / "metadata.json").is_file() or not (run_dir / "final.md").is_file():
                raise SystemExit(f"missing completed run: {run_dir.name}")
            results.append(score_run(run_dir, args.label))
    PUBLIC_ROOT.mkdir(parents=True, exist_ok=True)
    suffix = "aggregate" if set(args.tasks) == set(TASKS) else "-".join(args.tasks) + "-slice"
    aggregate = PUBLIC_ROOT / f"{args.label}-{suffix}.md"
    aggregate.write_text(render_aggregate(results, args.label), encoding="utf-8")
    if not all(bool(result["passed"]) for result in results):
        raise SystemExit("mechanical scoring failed")
    print(f"scored: runs={len(results)}, passed={len(results)}, aggregate={aggregate.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
