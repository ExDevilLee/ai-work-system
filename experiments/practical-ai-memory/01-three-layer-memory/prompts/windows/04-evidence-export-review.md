# Win11 第五次提示词：证据导出复核

请在回传前执行 `python validate_public_runs.py --require-runs` 并复核脱敏证据。确认公开目录只包含经过筛选的运行、评分、元数据和事件摘要；确认没有私有原始 `raw.jsonl`、真实 CodexClaw 记忆内容、Windows 用户名、Windows 绝对路径、Codex 会话 ID、API Key、内部域名、内部项目路径或模型 provider。

报告可回传文件清单、校验命令及结果、失败运行清单和仍需人工确认的项目。没有完成脱敏检查前，不要复制文件回 GitHub，也不要 push。
