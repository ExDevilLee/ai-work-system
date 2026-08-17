# P9 公开实验依据

本目录公开 P9「程序性记忆」在 macOS 合成任务上的可复查证据。两组模型配置始终分开记录，不合并成总分，也不做提供方比较。

## 内容

- `manifest.jsonl`：45 条第二模型逐格记录，加 5 条 Terra 聚合 Review 记录。
- `representative-runs/`：9 个脱敏代表样本，覆盖范围限定、失败恢复和候选沉淀三类高风险任务，以及全部三种条件。
- `fixtures/`：冻结任务表、条件材料和实验 manifest。
- `claim-matrix.md`：文章可以使用与不得外推的主张边界。

## 证据完整性边界

第二模型的 45 格脱敏 final 仍在本机中间层，公开 manifest 可逐格校验并展开代表样本。Terra Pilot 的原始 final 当时写入临时目录，未进入 P9 的 `runs/private/` 或 `runs/public/`；当前只保留逐份 Review、修复 Review 与分析报告。因此 manifest 将这些历史记录明确标为 `aggregate-only`，不补造逐格输出或校验和。

这不影响文章讨论“程序性记忆需要哪些边界”，但会限制复现口径：公开包支持第二模型逐格复核，只支持 Terra 聚合结果审计。文章进入 `ready` 前，应由人工确认是否接受这一历史证据缺口。

## 本地验证

```bash
python3 validate_design.py
python3 validate_protocol.py
python3 validate_public_evidence.py
```

这些命令只读取合成夹具和公开证据，不会调用模型、修改真实项目或访问私有记忆。
