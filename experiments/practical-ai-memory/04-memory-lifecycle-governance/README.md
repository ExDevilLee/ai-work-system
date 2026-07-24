# 长期记忆生命周期治理 POC

本实验为“AI 长期记忆实战”系列第四篇提供证据，比较长期记忆写入后面对冲突、过期、替代、范围变化和撤销时的三种治理机制。

## 当前研究问题

面对完全相同的历史记录、后续证据和治理决定，下列三种机制是否会影响 Agent 对当前有效记忆的判断：

- `append-only`：只追加记录，不改变旧记忆状态。
- `latest-wins`：默认采用时间最新的记录覆盖旧记录。
- `lifecycle-governed`：显式维护 `active`、`contested`、`superseded`、`expired` 和 `revoked` 状态。

重点观察：

- Agent 是否继续执行已经过期、被替代或被撤销的规则；
- 未解决冲突是否被较新记录静默覆盖；
- 适用范围收窄后，旧的全局结论是否仍被错误泛化；
- 历史记录能否保留，同时不再参与当前行动；
- 治理收益是否伴随更高的项目上下文读取成本。

详细变量、任务、评分项和停止条件见 [`EXPERIMENT.md`](EXPERIMENT.md)。

## 当前阶段

实验方案、合成夹具和隔离运行器已经建立，夹具验证、32 项单元测试、Python 编译和帮助参数门禁均通过。

2026-07-23 曾按执行边界暂停实际 N 次 POC 验证：

- 不继续运行剩余 Pilot，不启动 45 次正式重复矩阵。
- 暂停指令到达前已经误触发 9 次完整运行和 1 次中断运行；它们已整体移出可恢复矩阵路径，保留在本地私有区。
- 上述运行不做语义 Review、不评分、不聚合，也不能作为文章或 POC 结论。
- 后续只有在 Lee 明确恢复验证后，才从干净 Pilot 矩阵重新开始。

2026-07-24，Lee 已明确恢复此前暂停的工作。完整、干净的 15 次 macOS Pilot 01 已完成，运行层门禁全部通过；语义 Review 发现 `append-only` 与 `latest-wins` 的对照定义仍有歧义，因此 Pilot 01 不进入正式矩阵，也不作为效果证据。

收紧条件定义后的 15 次 macOS Pilot 02 已完成，并同时通过执行门禁和条件可区分性 Review。随后按冻结协议完成 45 次 macOS 正式运行、真实计时 Review、评分和聚合：

- 45/45 运行通过协议门禁，15 个任务/条件组合均为 `n=3`。
- `append-only`：51/84。
- `latest-wins`：72/84。
- `lifecycle-governed`：84/84。
- 45/45 工作区指标覆盖完整且输出可靠。

详细结果见 [`analysis/formal-macos.md`](analysis/formal-macos.md)。第四篇文章已进入 `review`，当前尚未执行 Win11 复现。

Win11 使用相同冻结协议的完整复现步骤见 [`WINDOWS-VALIDATION.md`](WINDOWS-VALIDATION.md)。

静态验证：

```bash
python3 validate_fixtures.py
python3 -m unittest discover -p 'test_*.py'
```

运行记录默认写入被 Git 忽略的 `runs/private/<platform-tag>/`。实验只使用合成发布记录，不读取真实记忆目录、CodexClaw 私有内容或用户级 Codex 插件。
