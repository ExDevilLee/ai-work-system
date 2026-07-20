# 常驻上下文与按需读取 POC

本实验为“AI 长期记忆实战”系列第二篇提供证据，比较同一组项目事实采用三种加载策略时的表现：全部写入自动加载入口、只常驻少量高后果规则，以及仅常驻资料索引。

## 当前研究问题

长期记忆并非越多常驻越好。实验尝试回答：哪些信息值得占用每次任务的上下文，哪些信息更适合通过索引按需读取？

三组条件共享完全相同的事实文件，只替换根目录的 `AGENTS.md`：

- `all-resident`：当前状态、稳定规则、观察、失效结论和参考资料正文全部复制到自动加载入口。
- `selective-resident`：只常驻稳定、跨任务且遗漏后果较高的三条规则，其余内容按任务读取。
- `index-only`：自动加载入口只提供导航，不直接携带项目事实。

详细变量、任务、评分和停止条件见 [`EXPERIMENT.md`](EXPERIMENT.md)。

## 当前阶段

三轮 Pilot 与 36 次 macOS 正式矩阵均已完成。三个条件各 12 个样本，全部命中冻结答案，工作区指标覆盖完整。结果没有支持“选择性常驻总是最优”：不同任务的读取成本不同，常驻规则也不能保证模型不再核对文件。完整结论与限制见 [`analysis/formal-macos.md`](analysis/formal-macos.md)。所有 Pilot 都不进入文章结论。

静态验证：

```bash
python3 validate_fixtures.py
python3 -m unittest discover -p 'test_*.py'
```

运行记录默认写入被 Git 忽略的 `runs/private/<platform-tag>/`。试跑只用于发现题目歧义、夹具泄漏、评分困难和指标覆盖缺口，不进入正式结论。macOS 脱敏公开证据已生成，下一阶段准备 Win11 复现；Win11 完成前不声明跨平台实测。

公开证据只保留全部 36 次正式运行的 manifest、第 1 轮 12 个代表样本，以及按条件去重的 3 份夹具。原始事件、绝对路径和会话标识不进入 Git：

```bash
python3 build_public_evidence.py
python3 validate_public_evidence.py
```

公开入口：[`evidence/README.md`](evidence/README.md)。

Win11 复现步骤见 [`WINDOWS-VALIDATION.md`](WINDOWS-VALIDATION.md)。

试跑复核：

- [`analysis/pilot-01.md`](analysis/pilot-01.md)
- [`analysis/pilot-02.md`](analysis/pilot-02.md)
- [`analysis/pilot-03.md`](analysis/pilot-03.md)

正式结果：

- [`analysis/formal-macos.md`](analysis/formal-macos.md)
- [`references/literature-ledger.md`](references/literature-ledger.md)
