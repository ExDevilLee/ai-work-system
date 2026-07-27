# Pilot 02 Review

## 结论

Pilot 02 已形成可解释的条件差异，但 `historical-trace` 缺少 rubric 要求的退出原因证据，不能进入正式矩阵。

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
| `approved-decision` | 3/6 | 2/6 | 6/6 |
| `unresolved-conflict` | 6/6 | 6/6 | 6/6 |
| `scope-bound-rule` | 5/6 | 5/6 | 6/6 |
| `historical-trace` | 4/6 | 5/6 | 5/6 |

建议总分：

- `rag-only`：22/28。
- `rag-with-recency`：22/28。
- `memory-governed`：27/28。

这些建议没有写入运行目录。

## 已验证的条件差异

`approved-decision` 已经成功隔离状态治理：

- `rag-only` 找回 NAV-201 与 NAV-202，但因没有批准状态而拒绝确定唯一当前方案。
- `rag-with-recency` 采用日期较新的 NAV-202，即使它的检索标签显示为 proposal。
- `memory-governed` 根据状态投影采用 `active` 的 NAV-201，并拒绝 `proposed` 的 NAV-202。

`static-reference` 三组均满分，说明状态治理没有破坏普通资料检索。`unresolved-conflict` 三组也均谨慎处理，表明明确的因果限制足以阻止 recency 静默选边；这属于合理结果，不要求每个任务都制造差异。

## 停止原因

`historical-trace` 的冻结 rubric 要求说明旧索引复制方案因平台相关状态退出。Pilot 02 的共享证据只保留了两个候选方案，没有保留平台相关状态的技术观察。三组都无法从现有材料回答该评分项，`memory-governed` 也明确拒绝补造原因。

这属于证据缺失，不应通过修改评分表或给某个条件自动得分解决。下一版应增加一条共享技术观察：二进制索引包含平台相关路径或缓存状态，跨平台直接复用不可靠。该观察只解释技术原因，不声明哪套方案当前有效；当前状态仍由治理投影决定。
