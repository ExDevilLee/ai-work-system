# 当前记忆地图 POC

这是“AI 长期记忆实战”系列的第六个 POC。它以同一份冻结 manifest 为规范化事实源，分别验证 Agent 的当前状态恢复和人的状态治理体验。

## 双通道

- Agent 通道比较 `source-only`、`flat-index` 和 `state-projection`，研究显式状态、范围和关系是否影响当前行动判断。
- 人工通道比较事实等价的 `state-table` 和 `visual-map`，研究单名参与者在探索性任务中的正确率与操作差异。

两个通道共享事实，但不共享结论。Agent 不需要读取视觉地图，人的实验结果也不能证明 Agent 状态投影有效。

## 当前阶段

**实现进行中。** 当前已建立实验协议、manifest 状态模型、校验 API 和 LF 边界。实验夹具、生成视图、隔离运行器、评分聚合与人工页面将在后续任务实现，目前还不能启动 Pilot 或人工实验。

设计与实施入口：

- [`DESIGN.md`](DESIGN.md)：完整研究设计、停止门禁和结论边界。
- [`EXPERIMENT.md`](EXPERIMENT.md)：冻结实验协议。
- [`IMPLEMENTATION-PLAN.md`](IMPLEMENTATION-PLAN.md)：分任务实施计划。
- [`fixture_model.py`](fixture_model.py)：manifest 校验、事实集合和规范 JSON API。

## 公开与私有边界

仓库可以公开合成夹具、协议、生成器、校验器、脱敏聚合和空白实验模板。以下内容只保留在本地私有目录：

- Agent 原始事件、完整回答、标准错误和逐次评分。
- 人工实验逐题事件。
- 用户名、账号、绝对路径、会话或浏览器身份、存储地址和真实记忆内容。
- 模型 provider。

私有运行数据将分别写入 `runs/private/` 和 `human-results/private/`，并由本目录的 `.gitignore` 排除。

## 命令

当前可用的状态模型测试：

```bash
python3 -m unittest test_fixture_model.py -v
```

实施计划完成后将提供以下命令；对应脚本目前尚不存在，当前阶段不要执行：

```bash
python3 validate_fixtures.py
python3 generate_views.py
python3 run_pilot_matrix.py
python3 run_formal_matrix.py
python3 aggregate_results.py
python3 human_experiment.py
```

后续仍须先通过夹具、事实等价、隐私和页面门禁，再按 15 次 Pilot、45 次 macOS 正式矩阵和 15 次 Win11 Level 2 兼容性 Smoke 的顺序推进。
