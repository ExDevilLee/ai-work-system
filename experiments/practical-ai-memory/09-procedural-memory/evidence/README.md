# P9 公开实验依据

本目录公开 P9「程序性记忆」在 macOS 合成任务上的可复查证据。两组请求配置始终分开记录，不比较运行平台提供方；正式矩阵只在合并汇总中计算总体通过与失败分类。

## 内容

- `manifest.jsonl`：45 条第二模型逐格记录，加 5 条 Terra 聚合 Review 记录。
- `representative-runs/`：9 个脱敏代表样本，覆盖范围限定、失败恢复和候选沉淀三类高风险任务，以及全部三种条件。
- `fixtures/`：冻结任务表、条件材料和实验 manifest。
- `claim-matrix.md`：文章可以使用与不得外推的主张边界。

- `../data/formal-r2-macos-terra-medium.*` 与 `../data/formal-r3-macos-deepseek-max.*`：正式矩阵脱敏聚合。
- `../runs/aggregates/macos/formal-*-readonly-review.md`：正式矩阵分配置 Review 与合并汇总。

## 证据完整性边界

第二模型的 45 格脱敏 final 仍在本机中间层，公开 manifest 可逐格校验并展开代表样本。Terra Pilot 的原始 final 当时写入临时目录，未进入 P9 的 `runs/private/` 或 `runs/public/`；当前只保留逐份 Review、修复 Review 与分析报告。因此 manifest 将这些历史记录明确标为 `aggregate-only`，不补造逐格输出或校验和。

这项不对称只适用于旧 Pilot。正式矩阵已经为两组配置保存 raw final 与 metadata，并公开脱敏聚合；完整事件流继续留在私有目录。

## 本地验证

```bash
python3 validate_design.py
python3 validate_protocol.py
python3 validate_public_evidence.py
python3 -m unittest test_formal_matrix.py
```

这些命令只读取合成夹具和公开证据，不会调用模型、修改真实项目或访问私有记忆。
