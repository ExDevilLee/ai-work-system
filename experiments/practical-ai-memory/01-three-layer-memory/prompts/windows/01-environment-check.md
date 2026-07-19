# Win11 第二次提示词：环境检查

在已确认仓库和安全边界无误后，检查原生 Windows 11 环境是否满足 POC 要求。请报告 PowerShell、Python、Codex CLI、Git、Git LFS 的版本和可执行文件位置，并确认 Codex 已登录、可使用 `gpt-5.6-sol` 与 `medium` 推理强度。执行 `git check-attr eol` 检查 `fixtures/pilot-02/baseline/PROJECT_NOTES.md` 和 `prompts/current-task.md`，两者必须显示 `eol: lf`；不要手工改写夹具或提示来修复哈希。

执行 `python -m unittest test_run_experiment.py`，确认跨平台哈希排序测试通过。只做环境检查和回归测试，不启动正式实验，不读取真实记忆目录，不修改仓库文件。若当前 shell 实际运行在 WSL、哈希测试失败或 Codex 无法使用指定模型，请停止并给出阻塞原因。
