# Win11 第三次提示词：Smoke test 复核

请复核刚刚完成的 Win11 smoke test。检查 `runs/private/win11/` 下每次运行是否包含 `metadata.json`、`final.md`、`raw.jsonl` 和 `stderr.log`，并核对平台标签、模型名、推理强度、夹具 SHA-256、提示 SHA-256、退出码和评分所需信息。

确认命令只访问隔离 fixture workspace，没有访问真实 CodexClaw 记忆目录；确认没有 provider 信息、密钥、Windows 用户名或不应公开的绝对路径被写入将要回传的证据。若任何一项失败，不要继续正式矩阵，先报告失败运行和证据路径。
