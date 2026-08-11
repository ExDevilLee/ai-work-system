# macOS 正式实验报告（deepseek-v4-flash 对照 · memory-lifecycle-governance）

日期：2026-08-06

## 实验配置

- 模型：`deepseek-v4-flash`。
- 推理强度：`max`。
- 执行器：`codex-cli 0.146.1`。
- 平台：macOS，Apple Silicon。
- 会话：每次使用独立 `--ephemeral` 新会话。
- 沙箱：`read-only`。
- 样本：5 个任务 × 3 个条件共 36 次预定义正式运行（formal-01 15 次 + formal-02 15 次 + formal-03 6 次；每个条件恰好 12 次，每任务 4–8 次）。

本对照使用与 `gpt-5.6-sol` 基线相同的协议与夹具及同一份 rubric/answers/governance-checks。不同模型的数据没有并入同一聚合，聚合产物按模型独立命名（`data/formal-macos-deepseek-v4-flash-max.{json,csv}`）。

基线说明：

- macOS gpt 基线：`data/formal-macos-gpt-5.6-sol-medium.{json,csv}`，45 次（5 任务 × 3 条件 × 3 次），`codex-cli 0.145.0`，推理强度 `medium`。
- Win11 gpt 基线：`data/formal-win11-gpt-5.6-sol-medium.{json,csv}`，45 次，方向与 macOS 一致。本报告以 macOS gpt 作为同平台配置敏感性参照。

## 协议有效性

全部 36 次运行满足协议门禁：

- 退出码：36/36 为 0。
- 运行时工具访问（`runtime_tool_access_calls`）：36/36 为 0。
- 环境隔离：36/36 为 `protocol_environment_isolated: true`。
- 输出产物：36/36 均生成 final.md 与 metadata.json。
- 工作区指标覆盖完整且输出字节可靠：36/36。

`protocol_valid` 判定全部为 `yes`。

## 正确性（人工评分）

条件合计（deepseek-v4-flash 36 次 vs gpt-5.6-sol macOS 45 次）：

| 条件 | deepseek-v4-flash | gpt-5.6-sol（macOS） |
| --- | ---: | ---: |
| 只追加 | 47/67（70.1%） | 51/84（60.7%） |
| 最新记录优先 | 63/67（94.0%） | 72/84（85.7%） |
| 生命周期治理 | 68/68（100%） | 84/84（100%） |
| 合计 | 178/202（88.1%） | 207/252（82.1%） |

排程不同（deepseek 36 次，每条件 12 次；gpt 45 次，每条件 15 次），因此分母不同，百分比口径可比、绝对分不可比。

格子明细（只列两模型都丢分的可比单元；其余 11 格两模型均为满分）：

| 任务:条件 | deepseek-v4-flash | gpt-5.6-sol |
| --- | ---: | ---: |
| explicit-supersession:append-only | 8/12（n=2） | 6/18（n=3） |
| unresolved-conflict:latest-wins | 6/10（n=2） | 3/15（n=3） |
| scope-narrowing:append-only | 2/12（n=2） | 6/18（n=3） |
| emergency-revocation:append-only | 12/18（n=3） | 9/18（n=3） |

全部丢分集中在 4 个格子（共丢 24 分），按失败模式归类：

1. 只追加拒绝执行替代/撤销决定（explicit-supersession + scope-narrowing + emergency-revocation:append-only，共丢 20 分）：只追加机制下，模型把显式替代（DEC-201）、范围收窄（DEC-204）和紧急撤销（DEC-205）解释为"无唯一动作"而拒绝执行，旧规则仍指导行动。丢分形态与 gpt 完全一致——gpt 在同三个格子的丢分形态相同（6/18、6/18、9/18）。差异在于 deepseek 有一次正确应用了紧急撤销（emergency-revocation 一轮 6/6），说明只追加并不必然导致全部决定都无法执行，只是不够稳定。
2. 最新记录优先静默采用冲突记录（unresolved-conflict:latest-wins，丢 4 分）：deepseek 两次任务中一次正确识别冲突并标记 contested（5/5），另一次直接采用日期较新的 180 秒（1/5）。gpt 同格 3 次全部静默采用（3/15）。失败形态一致，deepseek 在此格表现更好。

生命周期治理条件的全部格子两模型均满分，治理机制的关键约束全部正确执行。

## 过程指标

按条件合并的中位数（deepseek 每条件 12 次，gpt 每条件 15 次；两模型使用不同 Codex CLI 版本，仅作量级参考）：

| 条件 | 模型 | 耗时（秒） | 上下文（B） | 工作区调用 | 输出（B） | input tokens | output tokens | reasoning tokens |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 只追加 | deepseek | 25 | 4,630 | 4 | 3,882 | 43,520 | 1,398 | 734 |
| 只追加 | gpt | 35 | 3,672 | 4 | 2,924 | 62,986 | 3,265 | 0 |
| 最新记录优先 | deepseek | 21 | 5,023 | 4 | 4,335 | 43,420 | 1,218 | 696 |
| 最新记录优先 | gpt | 36 | 3,762 | 4 | 3,074 | 84,170 | 3,363 | 0 |
| 生命周期治理 | deepseek | 19 | 4,492 | 4 | 3,630 | 43,892 | 972 | 408 |
| 生命周期治理 | gpt | 31 | 3,781 | 4 | 2,918 | 63,009 | 2,551 | 0 |

deepseek 单次耗时更短（19–25 秒 vs 31–36 秒）、input tokens 更少（约 4.3–4.4 万 vs 6.3–8.4 万），工作区调用相同（均 4 次），上下文字节同量级（4.5–5.0 KB vs 3.7–3.8 KB），output/reasoning tokens 模式不同（deepseek 有 reasoning tokens 输出，gpt 无）。

## 可以支持的结论

1. 条件梯度在第二组配置下复现：只追加 < 最新记录优先 < 生命周期治理，在当前两组配置中方向一致。生命周期治理满分、时间到期满分。
2. 全部丢分集中在同样的 4 个格子：只追加拒绝执行替代/撤销决定、最新记录优先静默采用冲突记录。这支持优先检查"记录机制本身不解决冲突解释"这一机制缺口，但不能据此排除配置变量的影响。
3. deepseek 配置整体得分率为 88.1%，gpt 配置为 82.1%；紧急撤销为 12/18 vs 9/18，未解决冲突为 6/10 vs 3/15。由于模型、推理强度、CLI 版本和样本排程不同，这些差异只作配置敏感性观察，不归因于更强推理或模型能力。

## 不能支持的结论

1. 不能声称 deepseek 比 gpt 更"安全"或更"谨慎"：每格仅 2–3 次样本，同一格内同时出现正确执行与拒绝执行，随机性可见。
2. 不能把耗时和 input token 差异归因于模型本身：两个模型使用不同 Codex CLI 版本（0.146.1 vs 0.145.0），平台、硬件、缓存状态不完全相同，只能作为量级参考。
3. 不能把 36 次样本推广为一般结论：排程与 gpt 不同（36 vs 45），单次运行的翻转即可改变一个格子的得分率。
4. 配置敏感性复核只在 macOS 上进行，Win11 仅有 gpt 一组配置，不能据此声称结果已在 Win11 的另一组配置下复现。

## 当前判断

截至 2026-08-06，04-memory-lifecycle-governance 的 macOS deepseek-v4-flash(max) 敏感性复核已完成：36/36 协议有效，178/202（88.1%），全部丢分集中在 4 个格子且失败模式与 gpt 配置逐项一致。生命周期治理与时间到期在第二组配置下仍然满分；只追加拒绝执行替代/撤销决定、最新记录优先静默采用冲突记录在当前两组配置中重复出现。文章可以说明结果方向在另一组配置下复现，并优先检查机制缺口；不能写成单变量模型因果。
