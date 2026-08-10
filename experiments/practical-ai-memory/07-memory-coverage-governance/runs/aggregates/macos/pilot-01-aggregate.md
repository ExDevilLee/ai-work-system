# pilot-01 单配置 Pilot 脱敏聚合

## 边界

- 这是一个冻结合成夹具上的单配置 Pilot 切片：5 个任务、3 种条件、每格 1 次，共 15 次运行。它不是双模型正式矩阵。
- 公开聚合不包含原始回答、逐次计时、执行器版本或具体模型标识；这些内容仅留在未跟踪的本地私有目录。
- 单次运行不用于比较条件效果、模型表现或通用质量；本报告只记录协议和最小事实门禁是否通过。

## 机械评分结果

| 任务 | 条件 | 通过 | 未通过检查 |
| --- | --- | --- | --- |
| `coverage-gap` | `source-only` | 是 | 无 |
| `coverage-gap` | `state-projection` | 是 | 无 |
| `coverage-gap` | `coverage-governance-projection` | 是 | 无 |
| `review-due` | `source-only` | 是 | 无 |
| `review-due` | `state-projection` | 是 | 无 |
| `review-due` | `coverage-governance-projection` | 是 | 无 |
| `governance-queue` | `source-only` | 是 | 无 |
| `governance-queue` | `state-projection` | 是 | 无 |
| `governance-queue` | `coverage-governance-projection` | 是 | 无 |
| `scope-slice` | `source-only` | 否 | human_only_next_step |
| `scope-slice` | `state-projection` | 否 | human_only_next_step |
| `scope-slice` | `coverage-governance-projection` | 否 | human_only_next_step |
| `source-trace` | `source-only` | 是 | 无 |
| `source-trace` | `state-projection` | 是 | 无 |
| `source-trace` | `coverage-governance-projection` | 是 | 无 |

## 结论边界

本 Pilot 的机械门禁通过 12/15 格。通过只说明该冻结合成场景中的任务、隔离运行和评分协议能够执行；它不支持效率、优越性、跨模型稳定性或替代人工治理的结论。

存在未通过格：先用新标签重新冻结 Prompt 与 rubric，并从头重复该 Pilot；在修订后的完整 Pilot 通过前，不运行第二个模型配置或正式矩阵。
