# 三层 AI 记忆系统 POC

本实验为“AI 长期记忆实战”系列第一篇提供证据，比较同一组信息在“混合记录”和“三层分离”两种组织方式下，对新会话恢复任务与查找资料的影响。

当前阶段只验证 macOS。Windows 将在后续兼容性 checkpoint 使用同一夹具、提示和评分规则补充验证；在此之前，本实验不作跨平台结论。

## 核心假设

当信息内容完全相同，仅把它们分为当前工作状态、稳定长期记忆和按需参考资料三层时，新会话应该更容易：

- 找到当前目标和下一步动作。
- 区分稳定规则与临时观察。
- 在需要时找到参考资料并给出来源路径。
- 避免把已经失效或尚未确认的信息当成长期事实。

反例是：分层增加了文件和导航成本，却没有提高答案正确性，或者使 Agent 漏读必要信息。

## 目录

```text
01-three-layer-memory/
├── README.md
├── EXPERIMENT.md
├── fixtures/
│   └── pilot-02/
├── prompts/
├── expected/
├── evidence/          # 提交到 Git 的精简公开依据
├── runs/
│   ├── private/       # 完整原始记录，仅本地保留
│   └── public/        # 完整脱敏中间层，仅本地保留
├── data/
├── analysis/
└── references/
    └── literature-ledger.md
```

## 当前门禁

1. Pilot 01 已验证运行链路，但因正确性天花板效应未通过协议门禁。
2. Pilot 02 已拆分三个独立任务，并真实发现、保留和修正一次夹具不等价问题。
3. `gpt-5.6-sol medium` 的 18 次 macOS 正式实验已经完成并通过证据 Review。
4. `gpt-5.6-terra medium` 已完成 6 次探索性模型对照，不与主样本混算。
5. 当前 POC 已具备支持第一篇文章大纲和证据映射的条件。

详细变量、任务和评分方法见 [`EXPERIMENT.md`](EXPERIMENT.md)。

正式结果见：

- [`analysis/formal-macos-gpt-5.6-sol-medium.md`](analysis/formal-macos-gpt-5.6-sol-medium.md)
- [`analysis/model-sensitivity.md`](analysis/model-sensitivity.md)

试跑命令示例：

```bash
python3 run_experiment.py baseline --label pilot-02 \
  --model gpt-5.6-sol --reasoning-effort medium
python3 run_experiment.py layered --label pilot-02 \
  --model gpt-5.6-sol --reasoning-effort medium
```

正式运行使用非 `pilot` 标签时，脚本强制要求显式传入模型和推理强度。

## 公开与脱敏

实验运行默认写入 `runs/private/`。完成评分后，先使用 `export_public_run.py` 生成完整脱敏中间层 `runs/public/`：

```bash
python3 export_public_run.py runs/private/macos/<run-name>
python3 validate_public_runs.py
```

`runs/private/` 和 `runs/public/` 都由 Git 忽略。阶段实验完成后，再生成真正提交的精简证据：

```bash
python3 build_committed_evidence.py
python3 validate_committed_evidence.py
```

[`evidence/`](evidence/) 使用一份 manifest 记录全部 36 次运行，只展开 10 个代表样本，并复用中央夹具和提示文件。它保留真实失败、正式对照和模型差异，同时避免几十个重复目录干扰阅读。

仓库级规则见 [`docs/poc-evidence-publication.md`](../../../docs/poc-evidence-publication.md)。文章发布时使用下面的固定入口：

<https://github.com/ExDevilLee/ai-work-system/tree/main/experiments/practical-ai-memory/01-three-layer-memory>
