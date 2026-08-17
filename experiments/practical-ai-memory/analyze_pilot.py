#!/usr/bin/env python3
"""Summarize P9 Pilot and repair evidence without retaining raw answers."""

import argparse
import json
import re
from pathlib import Path


def load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")).get("results", [])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--original", action="append", required=True)
    parser.add_argument("--repair", action="append", required=True)
    parser.add_argument("--final", action="append", required=True)
    args = parser.parse_args()
    original = [result for path in args.original for result in load(Path(path))]
    repaired = [result for path in args.repair for result in load(Path(path))]
    final = [result for path in args.final for result in load(Path(path))]
    by_condition = {}
    for result in original:
        condition = re.split(r"[｜:]", result["cell"], maxsplit=1)[0]
        answer = result.get("answer", {})
        by_condition.setdefault(condition, {"cells": 0, "chars": 0})
        by_condition[condition]["cells"] += 1
        by_condition[condition]["chars"] += sum(len(str(answer.get(key, ""))) for key in answer)
    lines = [
        "# P9 Pilot-01 证据汇总与扩展决策",
        "",
        "## 证据范围",
        "",
        f"- 原始单配置 Pilot：{len(original)} 格。",
        f"- 修复批次：{len(repaired)} 格；其中包含一次未纳入原始矩阵的额外输出。",
        f"- 最终修复：{len(final)} 格。",
        "- 配置：macOS、`gpt-5.6-terra`、`medium`、`read-only`、`ephemeral`。",
        "",
        "## 条件级过程数据",
        "",
        "| 条件 | 原始格数 | 回答字符数 | 平均字符数 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for condition in sorted(by_condition):
        row = by_condition[condition]
        average = row["chars"] / row["cells"] if row["cells"] else 0
        lines.append(f"| `{condition}` | {row['cells']} | {row['chars']} | {average:.1f} |")
    lines.extend([
        "",
        "## 观察",
        "",
        "- 三种条件都能在修复后完成结构化输出，说明任务和输出契约可执行。",
        "- 原始边界失败主要不是事实错误，而是范围收窄和人工 Review 的表达不稳定。",
        "- `skill-workflow` 在候选沉淀、恢复和范围任务中更容易生成额外或过宽的表达，说明程序性记忆可能放大流程措辞，而不是自动带来更好边界。",
        "- 当前没有可靠的质量、返工或耗时对照数据，不能宣称任何条件提高效率或正确率。",
        "",
        "## 扩展决策",
        "",
        "当前建议：暂不加入第二模型配置，也不扩大正式矩阵。先把“范围收窄 + 人工 Review + 不自动晋升”固化为实验输出契约，再用一轮独立任务变体复测。若下一轮仍能保持边界稳定，才值得引入第二模型配置做敏感性复核。",
        "",
        "P9 仍停留在 POC 证据阶段，不创建公开文章正文，不修改全局 AGENTS、默认 Skill 或长期记忆。",
    ])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"original={len(original)} repaired={len(repaired)} final={len(final)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
