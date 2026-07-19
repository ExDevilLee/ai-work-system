# Win11 第四次提示词：正式矩阵复核

请复核 Win11 正式矩阵是否按照 `EXPERIMENT.md` 执行：三个任务、Baseline 和 Layered 两种条件、每组至少 3 次，共 18 次；条件顺序应交替，避免时间顺序偏差。

逐项检查运行完整性、协议有效性、评分依据、失败模式、workspace 输出字节、调用次数、耗时和 token。依据 `expected/answers.json` 形成逐项评分建议，但在 Lee 明确确认前不要执行 `score_run.py`，不要把 AI 建议伪装成人工复核结果。无法可靠统计的指标必须标记 unreliable，不得估算。不要把 Win11 结果和 macOS 结果混合聚合，也不要据此直接修改文章结论。
