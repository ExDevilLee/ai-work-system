#!/usr/bin/env python3
"""Score the frozen 5 x 3 x 3 formal matrix and render a de-identified aggregate.

Scoring reuses score_probe's rubric gates (same frozen rubric as the accepted
Pilot). Raw answers, timing and model identity stay in the untracked private
directory; only pass/fail per cell and the aggregate report are rendered.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from score_probe import ROOT, PUBLIC_ROOT, score_run


FORMAL_RUNS_ROOT = ROOT / "runs" / "private" / "macos"
TASKS = (
    "coverage-gap",
    "review-due",
    "governance-queue",
    "scope-slice",
    "source-trace",
)
CONDITIONS = ("source-only", "state-projection", "coverage-governance-projection")
REPETITIONS = 3


def collect_run_dirs(run_prefix: str) -> list[Path]:
    run_dirs: list[Path] = []
    for repetition in range(1, REPETITIONS + 1):
        for task in TASKS:
            for condition in CONDITIONS:
                run_dir = (
                    FORMAL_RUNS_ROOT
                    / f"{run_prefix}{repetition:02d}-{task}-{condition}"
                )
                if not (run_dir / "metadata.json").is_file() or not (run_dir / "final.md").is_file():
                    raise SystemExit(f"missing completed run: {run_dir.name}")
                run_dirs.append(run_dir)
    return run_dirs


def render_aggregate(results: list[dict[str, object]], label: str) -> str:
    passed = sum(bool(result["passed"]) for result in results)
    lines = [
        f"# {label} 正式矩阵脱敏聚合",
        "",
        "## 边界",
        "",
        f"- 这是冻结合成夹具上的正式矩阵：{len(TASKS)} 个任务 × {len(CONDITIONS)} 种条件 × {REPETITIONS} 次重复，共 {len(results)} 次隔离运行。",
        "- 公开聚合不包含原始回答、逐次计时、执行器版本或具体模型标识；这些内容仅留在未跟踪的本地私有目录。",
        "- 正式矩阵通过只说明该冻结合成场景中的任务、隔离运行和评分协议可稳定执行；它不支持跨模型稳定性、效率、条件优越性或替代人工治理的结论。",
        "",
        "## 机械评分结果",
        "",
        "| 重复 | 任务 | 条件 | 通过 | 未通过检查 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for index, result in enumerate(results):
        repetition = index // (len(TASKS) * len(CONDITIONS)) + 1
        checks = result["checks"]
        assert isinstance(checks, dict)
        failed = [name for name, value in checks.items() if not value]
        lines.append(
            f"| {repetition} | `{result['task']}` | `{result['condition']}` | "
            f"{'是' if result['passed'] else '否'} | {'无' if not failed else ', '.join(failed)} |"
        )
    lines.extend([
        "",
        "## 结论边界",
        "",
        f"本矩阵的机械门禁通过 {passed}/{len(results)} 格。通过只说明该冻结合成场景中的任务、隔离运行和评分协议能够执行；它不支持效率、优越性、跨模型稳定性或替代人工治理的结论。",
        "",
        "下一步：逐份只读 Review 后，才可决定哪些结论进入公开文章，以及是否需要 Win11 兼容性 Smoke。",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="pilot-04-deepseek")
    parser.add_argument("--aggregate-name", default="formal-matrix-deepseek-aggregate")
    parser.add_argument("--run-prefix", default="formal-")
    args = parser.parse_args()
    results = [score_run(run_dir, args.label) for run_dir in collect_run_dirs(args.run_prefix)]
    PUBLIC_ROOT.mkdir(parents=True, exist_ok=True)
    aggregate = PUBLIC_ROOT / f"{args.aggregate_name}.md"
    aggregate.write_text(render_aggregate(results, args.label), encoding="utf-8")
    passed = sum(bool(result["passed"]) for result in results)
    print(f"scored: runs={len(results)}, passed={passed}, aggregate={aggregate.relative_to(ROOT)}")
    if passed != len(results):
        failures = [
            f"{result['task']}/{result['condition']}"
            for result in results
            if not bool(result["passed"])
        ]
        print("failed cells:", ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
