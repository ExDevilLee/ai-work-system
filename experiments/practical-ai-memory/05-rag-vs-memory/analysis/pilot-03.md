# Pilot 03 Review

## 结论

Pilot 03 通过运行协议、评分可执行性、证据公平性和条件可区分性门禁，可以作为正式矩阵的冻结候选。

Pilot 03 使用修订后的 `pilot-02` fixture set。与 Pilot 02 相比，只新增了共享技术观察 OBS-503，用于解释二进制索引的跨平台兼容性风险；当前状态仍只由 `memory/CURRENT.md` 维护。

## 运行层检查

- 15/15 运行完成，退出码为 0。
- 15/15 环境隔离有效，插件关闭，运行时越界访问为 0。
- 15/15 工作区指标覆盖完整且输出可靠。
- 每个任务的三个条件使用同一个 Prompt 哈希。
- 每个条件在五个任务中保持同一个 fixture 哈希。
- 模型为 `gpt-5.6-sol`，推理强度为 `medium`，Codex CLI 为 `0.145.0`。
- 未创建 `score.json`，未启动正式矩阵。

## 只读评分建议

| 任务 | `rag-only` | `rag-with-recency` | `memory-governed` |
| --- | ---: | ---: | ---: |
| `static-reference` | 4/4 | 4/4 | 4/4 |
| `approved-decision` | 5/6 | 2/6 | 6/6 |
| `unresolved-conflict` | 6/6 | 6/6 | 6/6 |
| `scope-bound-rule` | 5/6 | 5/6 | 6/6 |
| `historical-trace` | 6/6 | 6/6 | 6/6 |

建议总分：

- `rag-only`：26/28。
- `rag-with-recency`：23/28。
- `memory-governed`：28/28。

15 份答案均建议：

- `protocol_valid=true`。
- `unsupported_claims=0`。
- `irrelevant_facts=0`。

这些建议没有写入运行目录。

## 条件差异解释

`static-reference` 三组均满分，说明状态治理没有损害普通资料检索。

`approved-decision` 形成了最清晰的差异：

- `rag-only` 正确拒绝 NAV-202，但共享证据没有证明 NAV-201 的正式批准层级，因此缺少一个状态评分项。
- `rag-with-recency` 明确采用日期较新的 NAV-202，并取消远端检查，产生错误当前行动。
- `memory-governed` 根据 `active/proposed` 状态采用 NAV-201，并拒绝 NAV-202。

`unresolved-conflict` 三组均满分是合理结果。两份观察都明确说明因果关系尚未验证，足以阻止时间优先机制把 180 秒直接晋升为统一规则。这说明治理状态不是正确回答的唯一途径，也避免实验预设 `memory-governed` 必须在每题胜出。

`scope-bound-rule` 中，检索组能从较新记录推断 Wiki-A 的范围，但无法证明旧全局记录已经正式退休；`memory-governed` 能通过状态投影补齐退出关系。

`historical-trace` 的三组均能从共享 OBS-503 解释兼容性风险，并从 IDX-501、IDX-502 追溯方案变化。`memory-governed` 额外确认了 active/retired 关系，但 rubric 不因条件身份自动加分。

## 冻结建议

正式矩阵建议冻结以下配置：

- fixture set：`pilot-02` 当前内容。
- 任务：5 类。
- 条件：`rag-only`、`rag-with-recency`、`memory-governed`。
- 每个组合重复 3 次，共 45 次。
- 模型：`gpt-5.6-sol`。
- 推理强度：`medium`。
- Codex CLI：`0.145.0`。

正式矩阵开始后不得修改 corpus、检索包、manifest、条件文件、Prompt、预期答案或 rubric。Pilot 的只读建议不进入正式评分，正式运行仍需逐份 Review 并记录真实时间。
