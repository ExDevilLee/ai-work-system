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
