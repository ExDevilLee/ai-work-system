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

三轮 Pilot 已完成：12 次完整矩阵与两轮各 3 次高后果任务修订验证。最终三组均命中冻结答案，工作区指标覆盖完整，协议门禁已经通过。当前进入 36 次 macOS 正式矩阵；所有 Pilot 都不进入文章结论。

静态验证：

```bash
python3 validate_fixtures.py
python3 -m unittest test_run_experiment.py test_validate_fixtures.py
```

运行记录默认写入被 Git 忽略的 `runs/private/<platform-tag>/`。试跑只用于发现题目歧义、夹具泄漏、评分困难和指标覆盖缺口，不进入正式结论。

试跑复核：

- [`analysis/pilot-01.md`](analysis/pilot-01.md)
- [`analysis/pilot-02.md`](analysis/pilot-02.md)
- [`analysis/pilot-03.md`](analysis/pilot-03.md)
