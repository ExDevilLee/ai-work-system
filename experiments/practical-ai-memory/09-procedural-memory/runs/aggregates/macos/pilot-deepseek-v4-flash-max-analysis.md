# P9 第二模型敏感性复核证据汇总

## 证据范围

- 第二模型复核 Pilot：45 格（3 条件 × 15 格），三个条件均首轮产出完整 final。
- 修复批次：无；三个条件首轮即全部通过逐份边界 Review。
- 最终通过：45/45 格；`review_pilot.py` 输出 `reviewed=45 failures=0`。
- 配置：macOS、`deepseek-v4-flash`、`max`、`read-only`、`ephemeral`；requested 与 observed 均单独记录，不与 Pilot-01（`gpt-5.6-terra` / `medium`）混合聚合。
- 固定输入与 Pilot-01 相同：`fixtures/pilot-01` 的 tasks.json 与三个条件材料；cell 集合与任务 manifest 逐字一致（每批次 15 格，顺序一致）。

## 条件级过程数据

| 条件 | 格数 | 回答字符数 | 平均字符数 | 逐份 Review |
| --- | ---: | ---: | ---: | ---: |
| `prompt-only` | 15 | 1810 | 120.7 | 15/15 |
| `guide-assisted` | 15 | 1635 | 109.0 | 15/15 |
| `skill-workflow` | 15 | 1618 | 107.9 | 15/15 |

## 观察

- 三种条件在该模型配置下都首轮完成结构化输出且全部通过逐份边界 Review，说明任务与输出契约可执行，且本轮没有出现 Pilot-01 首轮中范围收窄与人工 Review 表达不稳定的现象。
- 本轮 `guide-assisted` 与 `skill-workflow` 的平均回答字符数略低于 `prompt-only`；未观察到 Pilot-01 中 `skill-workflow` 更容易生成额外或过宽表达的现象（本轮 0 失败格）。
- 以上仅为单轮、单配置、合成矩阵的过程数据；不比较 provider，不把单次差异解释为普遍模型能力，不证明任何条件带来普遍质量或效率提升。

## 扩展决策

- 保留“范围收窄 + 人工 Review + 不自动晋升”作为实验输出契约。
- 本轮结果与 metadata 单独保存于 `runs/private/deepseek-v4-flash-max/` 与 `runs/public/deepseek-v4-flash-max/`，不与 Pilot-01 / Pilot-02 混合。
- 两模型边界稳定性比较仅在 Lee 决定并完成逐份 Review 后进行；本报告只呈现各自结果。
- P9 仍停留在 POC 证据阶段，不创建公开文章正文，不修改全局 AGENTS、默认 Skill 或长期记忆。
