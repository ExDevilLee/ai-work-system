# 覆盖治理投影 POC 冻结协议

## 本轮范围

本轮只执行一个由本次会话明确指定的模型配置，推理强度为 `medium`。具体模型标识只保存在本地私有运行元数据中；这一轮用于验证夹具、隔离运行器、Prompt、评分规则和协议门禁是否可用，不构成双模型正式矩阵或公开文章结论。

## 冻结条件

- 事实源：`fixtures/pilot-01/manifest.json` 与 `records/*.md`。
- 条件：`source-only`、`state-projection`、`coverage-governance-projection`。
- 任务：`coverage-gap`、`review-due`、`governance-queue`、`scope-slice`、`source-trace`。
- 每次运行使用独立临时工作区、`read-only` 沙箱和 `--ephemeral` 会话。
- 原始事件、最终回答、具体模型标识与运行元数据仅写入 `runs/private/`，不提交。

## Pilot 停止门禁

任一运行出现下列情况即停止，不进入下一格或正式矩阵：

- fixture 校验失败。
- Codex 命令非零退出，或未生成最终回答。
- 输出包含自动创建、替代、删除或晋升记忆的结论。
- 回答缺少任务要求的来源 ID。

## 允许的结论

Pilot 只能说明：该配置是否在一个冻结合成场景中完成了指定盘点任务，以及协议是否能稳定执行。它不能说明覆盖投影更高效、更准确、跨模型稳定，或可以替代人工治理。

## Pilot-01 结果与停止点

- 已运行 `5 个任务 × 3 个条件 × 1 次 = 15 次` 单配置隔离调用；每格均以零退出码生成最终答复。
- 机械评分通过 `12/15` 格。`coverage-gap`、`review-due`、`governance-queue` 与 `source-trace` 的三种条件均通过。
- `scope-slice` 的三种条件均未显式给出人工下一步。根因是冻结 Prompt 只要求范围边界和来源，没有把设计中要求的人工治理动作写成任务要求。
- 因此本 Pilot 标记为 `needs-protocol-revision`：不运行第二个模型配置，不进入正式矩阵，也不作条件效果结论。后续修订必须使用新标签、重新冻结 Prompt 与 rubric，并从头运行该 Pilot。

## Pilot-02 冻结修订

- `pilot-02` 保留 Pilot-01 的同一合成事实源、五个任务、三种条件和隔离执行方式；不会覆盖或重算 Pilot-01。
- 唯一任务契约改动是 `scope-slice`：对每个需要治理的主题域，必须给出最小人工复核下一步，并明确不自动创建规则、作出决定或扩展范围。
- 本轮使用独立的 `rubrics/pilot-02.json`；只有 `15/15` 格通过机械门禁，才可接受该单配置 Pilot。否则继续标记为 `needs-protocol-revision`。
- 即使 Pilot-02 全部通过，仍不运行第二个模型配置或正式矩阵，直到完成逐份只读 Review。

## Pilot-02 结果与停止点

- 已完成 `5 个任务 × 3 个条件 × 1 次 = 15 次` 独立隔离调用；每格均为零退出码且生成最终答复。
- 机械评分通过 `14/15` 格；Pilot-01 中的 `scope-slice` 三格均在本轮通过，说明新增的人类复核任务契约已被执行。
- 唯一失败为 `coverage-gap / coverage-governance-projection`：回答提出人工审阅，但未显式重申“不自动创建或改变规则”的边界。
- 结果继续标记为 `needs-protocol-revision`。本轮已完成 15 格执行目标，但不接受为通过的单配置 Pilot，也不运行第二个模型配置或正式矩阵。

## Pilot-03 冻结修订

- `pilot-03` 保持同一合成事实源、任务集合、条件和执行器，只补强 `coverage-gap`：答复必须显式说明不自动创建、替代、删除或晋升任何规则或记忆。
- 独立 rubric 为 `rubrics/pilot-03.json`。重新执行完整 `15` 格；仅在 `15/15` 通过并完成逐份只读 Review 后，才允许启动第二模型配置的 Pilot。

## Pilot-03 结果

- `15/15` 格均以零退出码生成最终答复，并全部通过冻结 rubric 的机械评分。
- 逐份只读 Review 已通过，脱敏结果见 `runs/aggregates/macos/pilot-03-readonly-review.md`。第一配置 Pilot 标记为 `accepted`，允许启动第二个独立模型配置的 Pilot；仍不允许直接进入正式矩阵。
