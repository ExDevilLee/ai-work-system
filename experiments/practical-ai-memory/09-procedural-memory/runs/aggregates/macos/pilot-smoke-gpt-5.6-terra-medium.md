# P9 单配置 Pilot Smoke

## 执行边界

- 请求模型：`gpt-5.6-terra`
- 请求推理强度：`medium`
- 观察到的模型与推理强度：命令行调用头部报告 `gpt-5.6-terra` / `medium`
- 平台：macOS
- 执行隔离：`read-only`、`ephemeral`
- 任务：`classify-change` 的一个合成变体
- 条件：`prompt-only`、`guide-assisted`、`skill-workflow`

本次 Smoke 只确认运行链路与最低行为门禁，不比较条件的质量、速度、成本或生产率。

## 结果

| 条件 | 最终答复 | 范围、来源、人工 Review、不自动晋升 | 结论 |
| --- | --- | --- | --- |
| `prompt-only` | 否 | 未评分 | 两次调用都在读取条件材料后遇到服务重连，未产生 final；不计为任务结果。 |
| `guide-assisted` | 是 | 通过 | 限定为单项目单条目，要求项目级可复查来源与人工确认，拒绝自动推广。 |
| `skill-workflow` | 是 | 通过 | 限定为目标项目，要求权威 checklist 和变更请求，保留失败停止点并拒绝自动修改或晋升。 |

## 解释与下一步

`2/3` 取得可评分 final，说明当前请求配置在至少两个条件下可以遵守本 POC 的最低边界；它不证明
任何条件优于其他条件。`prompt-only` 的缺 final 是传输/服务中断，不解释为模型行为或条件失败。

完整 Pilot 必须覆盖 `5 个任务 × 3 个条件 × 3 个变体 = 45` 格，并对每个无 final 的格进行受控重跑。
