# 当前记忆地图 POC

这是“AI 长期记忆实战”系列的第六个 POC。它以同一份冻结 manifest 为规范化事实源，分别验证 Agent 的当前状态恢复和人的状态治理体验。

## 双通道

- Agent 通道比较 `source-only`、`flat-index` 和 `state-projection`，研究显式状态、范围和关系是否影响当前行动判断。
- 人工通道比较事实等价的 `state-table` 和 `visual-map`，研究单名参与者在探索性任务中的正确率与操作差异。

两个通道共享事实，但不共享结论。Agent 不需要读取视觉地图，人的实验结果也不能证明 Agent 状态投影有效。

## 当前阶段

实验夹具、生成视图、隔离运行器、评分聚合与人工页面已经完成实现。macOS 已完成 Agent Pilot、45 次正式矩阵、真实计时 Review、评分与脱敏聚合；单名参与者的人类探索性实验也已完成。Win11 将按 Level 2 执行覆盖 5 个任务与 3 个条件的 15 次兼容性 Smoke，不阻塞本文的 macOS `review` 阶段。

设计与实施入口：

- [`DESIGN.md`](DESIGN.md)：完整研究设计、停止门禁和结论边界。
- [`EXPERIMENT.md`](EXPERIMENT.md)：冻结实验协议。
- [`IMPLEMENTATION-PLAN.md`](IMPLEMENTATION-PLAN.md)：分任务实施计划。
- [`fixture_model.py`](fixture_model.py)：manifest 校验、事实集合和规范 JSON API。
- [`analysis/pilot-01.md`](analysis/pilot-01.md)：Agent Pilot 的脱敏复核报告。
- [`analysis/human-trial.md`](analysis/human-trial.md)：单人探索性实验的条件级汇总。
- [`analysis/formal-macos.md`](analysis/formal-macos.md)：45 次 macOS 正式运行、评分与结论边界。

## 公开与私有边界

仓库可以公开合成夹具、协议、生成器、校验器、脱敏聚合和空白实验模板。以下内容只保留在本地私有目录：

- Agent 原始事件、完整回答、标准错误和逐次评分。
- 人工实验逐题事件。
- 用户名、账号、绝对路径、会话或浏览器身份、存储地址和真实记忆内容。

私有运行数据将分别写入 `runs/private/` 和 `human-results/private/`，并由本目录的 `.gitignore` 排除。

## 命令

当前可用的验证与实验命令：

```bash
python3 -m unittest discover -v
python3 validate_fixtures.py
python3 run_formal_matrix.py --platform-tag macos --model gpt-5.6-sol --reasoning-effort medium
python3 aggregate_results.py --platform-tag macos --model gpt-5.6-sol --reasoning-effort medium --output-stem formal-macos-gpt-5.6-sol-medium
```

请先阅读 `EXPERIMENT.md` 中的停止门禁和私有边界。正式矩阵已经完成；不要把该命令用于覆盖、替换或混入现有正式证据。Win11 兼容性 Smoke 需要单独按跨平台策略执行。
