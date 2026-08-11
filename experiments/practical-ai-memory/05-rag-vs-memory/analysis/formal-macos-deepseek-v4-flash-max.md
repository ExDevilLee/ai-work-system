# macOS 正式实验报告（deepseek-v4-flash 对照 · 05-rag-vs-memory）

日期：2026-08-06

## 实验配置

- 模型：`deepseek-v4-flash`。
- 推理强度：`max`。
- 执行器：`codex-cli 0.146.1`。
- 平台：macOS，Apple Silicon。
- 会话：每次使用独立 `--ephemeral` 新会话。
- 沙箱：`read-only`。
- 样本：5 个任务 × 3 个条件共 36 次预定义正式运行（formal-01 15 次 + formal-02 15 次 + formal-03 6 次；每个条件恰好 12 次，每任务 7–8 次）。

本对照使用与 `gpt-5.6-sol` 基线相同的协议与夹具及同一份 rubric/answers。不同模型的数据没有并入同一聚合，聚合产物按模型独立命名（`data/formal-macos-deepseek-v4-flash-max.{json,csv}`）。

基线说明：

- macOS gpt 基线：`data/formal-macos-gpt-5.6-sol-medium.{json,csv}`，45 次（5 任务 × 3 条件 × 3 次），`codex-cli 0.145.0`，推理强度 `medium`。
- Win11 gpt 基线：`data/formal-win11-gpt-5.6-sol-medium.{json,csv}`，45 次。本报告以 macOS gpt 作为同平台配置敏感性参照。

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
| rag-only | 59/68（86.8%） | 75/84（89.3%） |
| rag-with-recency | 53/68（77.9%） | 69/84（82.1%） |
| memory-governed | 66/66（100%） | 84/84（100%） |
| 合计 | 178/202（88.1%） | 228/252（90.5%） |

排程不同（deepseek 36 次，每条件 12 次；gpt 45 次，每条件 15 次），因此分母不同，百分比口径可比、绝对分不可比。

格子明细（两模型都在同一格丢分或表现不同的可比单元；其余 11 格两模型均为满分）：

| 任务:条件 | deepseek-v4-flash | gpt-5.6-sol |
| --- | ---: | ---: |
| approved-decision:rag-only | 13/18（n=3） | 15/18（n=3） |
| approved-decision:rag-with-recency | 3/18（n=3） | 6/18（n=3） |
| scope-bound-rule:rag-only | 8/12（n=2） | 12/18（n=3） |
| scope-bound-rule:rag-with-recency | 12/12（n=2） | 15/18（n=3） |

全部丢分集中在 3 个格子（共丢 24 分），按失败模式归类：

1. **最新记录优先把"较新"误读为"已批准"（approved-decision:rag-with-recency，最大失分源）**：包内日期最新的 NAV-202 是未批准的增量更新建议（不做远端检查），两个模型都静默采纳它指导行动，而非已批准的全量重建+远端检查方案。deepseek 3/18、gpt 6/18，失败形态一致；deepseek 三轮中仍有一轮正确拒绝（formal-01），说明同机制下模型可以识别，只是不稳定。
2. **仅检索包证据不足时表述保守（approved-decision:rag-only，deepseek 13/18 vs gpt 15/18）**：rag-only 包内无批准状态字段，deepseek 一次完全未断言当前动作（formal-01，3 分），另两次给出全量重建+远端检查但未说明批准层级（active/proposed），每轮各扣 1 分。这是"包内证据不足"导致的保守表述，不是机制缺口。
3. **范围推导保守（scope-bound-rule:rag-only，8/12 vs gpt 12/18）**：无法仅凭包内证据确定 Blog-B/Note-C 是否强制 PNG，选择不下结论（每轮丢 2 分）；deepseek 正确识别 IMG-402 限定范围但未继续推导。gpt 同格同样丢 6 分。
4. **日期优先在无冲突时无害甚至有益（scope-bound-rule:rag-with-recency）**：最新记录 IMG-402 恰为当前正确规则，deepseek 12/12 满分，而 gpt 丢 3 分（15/18）。同格两模型表现不同，是唯一一个 deepseek 优于 gpt 的失分格。

两轮一致性：formal-01/02 同格分数除 approved-decision:rag-only（3 分 → 5 分，一次未断言当前动作、两次给出动作但缺批准层级）外完全一致。

## 过程指标

按条件合并的中位数（deepseek 每条件 12 次，gpt 每条件 15 次；两模型使用不同 Codex CLI 版本，仅作量级参考）：

| 条件 | 模型 | 耗时（秒） | 上下文（B） | 工作区调用 | 输出（B） | input tokens | output tokens | reasoning tokens |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rag-only | deepseek | 27 | 7,256 | 4 | 6,832 | 45,139 | 1,778 | 1,104 |
| rag-only | gpt | 60 | 6,455 | 4 | 6,031 | 89,300 | 1,189 | 183 |
| rag-with-recency | deepseek | 23 | 7,453 | 3 | 7,038 | 38,588 | 1,457 | 900 |
| rag-with-recency | gpt | 40 | 6,946 | 2 | 6,531 | 66,013 | 854 | 151 |
| memory-governed | deepseek | 21 | 8,460 | 4 | 7,940 | 34,018 | 1,154 | 543 |
| memory-governed | gpt | 55 | 7,444 | 2 | 6,924 | 88,813 | 948 | 18 |

deepseek 单次耗时更短（21–27 秒 vs 40–60 秒）、input tokens 少一半以上（3.4–4.5 万 vs 6.6–8.9 万），output tokens 略多（1.2–1.8 千 vs 0.9–1.2 千），reasoning tokens 显著（0.5–1.1 千 vs 0–0.2 千）；上下文字节同量级（7.2–8.5 KB vs 6.5–7.4 KB），其中 memory-governed 条件 deepseek 上下文更大（8,460 vs 7,444 B），对应更长的治理指令。

## 可以支持的结论

1. 条件梯度在第二组配置下复现：memory-governed（100%）> rag-only（86.8% / 89.3%）> rag-with-recency（77.9% / 82.1%），当前两组配置方向一致。显式批准状态与范围限定是 05 场景下最有效的治理形式；裸加"日期优先"反而成为负资产——这与 04 中 latest-wins 优于 append-only 的方向不同，说明日期优先的价值取决于"较新的记录是否更权威"这一前提是否成立。
2. 全部丢分集中在同样的 3 个格子：最新记录优先把较新但未批准的方案（NAV-202）静默当作当前决定、仅检索包证据不足时表述保守。这支持优先检查"较新即权威"这一机制缺口，但不能据此排除配置变量的影响。
3. deepseek 得分率与 gpt 同档（88.1% vs 90.5%，百分比口径；样本数不同）。approved-decision:rag-with-recency 的日期陷阱两模型都踩（3/18 vs 6/18）；scope-bound-rule:rag-with-recency deepseek 满分而 gpt 丢 3 分，说明日期优先在无冲突时无害。
4. memory-governed 满分在第二组配置下复现（66/66 与 84/84）：approved-decision 任务在 memory-governed 下 12/12，而 rag-only 13/18、rag-with-recency 3/18——在当前冻结任务中，批准状态标注把同一任务的得分率从最低 16.7% 拉回 100%。

## 不能支持的结论

1. 不能声称 deepseek 比 gpt 更"安全"或更"谨慎"：每格仅 2–3 次样本，approved-decision:rag-only 出现 3 分与 5 分两轮波动，同格差异存在随机性。
2. 不能把耗时和 token 差异归因于模型本身：两个模型使用不同 Codex CLI 版本（0.146.1 vs 0.145.0），平台、硬件、缓存状态不完全相同，只能作为量级参考。
3. 不能把 36 次样本推广为一般结论：排程与 gpt 不同（36 vs 45），单次运行的翻转即可改变一个格子的得分率。
4. 配置敏感性复核只在 macOS 上进行，Win11 仅有 gpt 一组配置，不能据此声称结果已在 Win11 的另一组配置下复现。

## 当前判断

截至 2026-08-06，05-rag-vs-memory 的 macOS deepseek-v4-flash(max) 敏感性复核已完成：36/36 协议有效，178/202（88.1%）。memory-governed 满分在第二组配置下复现；rag-with-recency 的 approved-decision 日期陷阱（较新但未批准的 NAV-202 被静默采纳）是当前两组配置共有的最大失分源；日期优先在无冲突时无害。文章可以说明批准状态与范围限定的治理结果在另一组配置下复现，并优先检查"较新即权威"的机制缺口；不能写成单变量模型因果。
