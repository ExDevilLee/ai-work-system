# 长期记忆晋升门禁 POC

本实验为“AI 长期记忆实战”系列第三篇提供证据，比较三种从原始观察生成长期记忆的机制：直接晋升、规则门禁和分阶段人工门禁。

## 当前研究问题

面对相同的原始记录、证据和人工决策，晋升机制是否会影响：

- 值得长期复用的经验能否正确进入稳定记忆；
- 一次性成功、冲突、过期或敏感信息是否被错误晋升；
- 结论能否保留来源、状态和人工决策依据；
- 人工 Review 与项目上下文读取成本是否可控。

详细变量、任务、评分项和停止条件见 [`EXPERIMENT.md`](EXPERIMENT.md)。

## 当前阶段

macOS Pilot 01 和 45 次正式重复矩阵已经完成，协议、环境隔离和指标覆盖门禁通过。正式结果的只读评分建议已经形成，但本轮 Review 没有预先计时，因此尚未写入 `score.json` 或生成聚合数据。详见 [`analysis/pilot-01.md`](analysis/pilot-01.md) 和 [`analysis/formal-macos-review.md`](analysis/formal-macos-review.md)。

前两批 Win11 Smoke 发现 MCP 片段读取漏记后均按门禁停止并隔离。分类器现已覆盖带工具包装文本的夹具连续片段，并对无法归属的文件读取保守标记覆盖不完整。第三批 Smoke 因临时夹具路径链接被过严隔离；该链接属于私有证据脱敏问题，不是隔离协议失败。Win11 需要从头执行全部 15 次 Smoke。脱敏记录见 [`analysis/win11-smoke-01.md`](analysis/win11-smoke-01.md) 和 [`analysis/win11-smoke-03.md`](analysis/win11-smoke-03.md)。

静态验证：

```bash
python3 validate_fixtures.py
python3 -m unittest discover -p 'test_*.py'
```

运行记录默认写入被 Git 忽略的 `runs/private/<platform-tag>/`。实验只使用合成项目记录，不读取真实记忆目录、CodexClaw 私有内容或用户级 Codex 插件。
