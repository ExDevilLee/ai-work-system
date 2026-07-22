# Win11 正式矩阵最终结果

## 实验范围

Win11 按与 macOS 相同的冻结协议完成 45 次正式运行：5 个任务、3 个晋升条件、每个组合重复 3 次。模型为 `gpt-5.6-sol`，推理强度为 `medium`，Codex CLI 为 `0.144.1`。

45 次运行全部通过协议、环境隔离和 workspace 指标覆盖门禁。每个分组均为 `n=3`、`workspace_metrics_n=3`；没有 unknown 或未计量 MCP 调用。私有原始事件、临时路径和运行元数据不进入公开仓库。

## 评分聚合

| 任务 | direct-promotion | rule-gated | staged-human-gate |
| --- | ---: | ---: | ---: |
| repeated-evidence | 15/15 | 15/15 | 15/15 |
| one-off-success | 3/12 | 12/12 | 12/12 |
| conflicting-evidence | 9/12 | 12/12 | 12/12 |
| expired-scope | 15/15 | 15/15 | 15/15 |
| sensitive-record | 18/21 | 21/21 | 21/21 |
| 合计 | 60/75 | 75/75 | 75/75 |

Win11 的结果与 macOS 的 Review 建议方向一致：直接晋升在单次成功和敏感记录边界上出现误晋升，规则门禁和分阶段人工门禁在本轮夹具中未出现误晋升。

## 公开证据

脱敏聚合文件：

- [`data/formal-win11-gpt-5.6-sol-medium.csv`](../data/formal-win11-gpt-5.6-sol-medium.csv)
- [`data/formal-win11-gpt-5.6-sol-medium.json`](../data/formal-win11-gpt-5.6-sol-medium.json)

完整 `runs/private/win11/`、`raw.jsonl`、`score.json`、绝对路径、会话标识和 provider 信息不公开。
