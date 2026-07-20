# Win11 复现方案

本文档用于在真实 Windows 11 设备上复现第二个 POC：比较长期记忆中“全部常驻、选择性常驻、仅索引”三种加载策略。当前 macOS 正式矩阵已经完成；Win11 结果完成相同门禁后，才能在文章中写成跨平台复现。

## 1. 仓库与边界

- 仓库：<https://github.com/ExDevilLee/ai-work-system>
- 分支：`main`
- POC 目录：`experiments/practical-ai-memory/02-resident-vs-on-demand`
- 目标模型：`gpt-5.6-sol`
- 推理强度：`medium`

只使用本 POC 的 `fixtures/pilot-01/`，不要读取或复制真实 CodexClaw 记忆目录。不要修改 `content/articles/`、README、发布配置或生产记忆文件。不要记录或显示模型 provider；只记录模型名、推理强度、平台和 Codex CLI 版本。私有运行目录不能回传或 push。

## 2. 环境门禁

在 PowerShell 中进入 POC 目录后逐项执行：

```powershell
git remote -v
git branch --show-current
git status --short
git rev-parse HEAD
$PSVersionTable
python --version
codex --version
git --version
Get-Command python
Get-Command codex
git config --get core.autocrlf
git check-attr eol -- run_experiment.py
git check-attr eol -- prompts/critical-boundary.md
git check-attr eol -- fixtures/pilot-01/common/memory/MEMORY.md
```

确认是原生 Win11，不是 WSL；Codex CLI 已登录，并能使用目标模型与推理强度。三个 `git check-attr` 都必须显示 `eol: lf`。如果 `core.autocrlf=true` 但属性没有显示 `eol: lf`，先停止，不要手工改写文件或继续实验。

## 3. 代码与 smoke 门禁

先确认帮助命令不会启动任务，再运行静态验证：

```powershell
python run_formal_matrix.py --help
python -m unittest discover -p "test_*.py"
python validate_fixtures.py
python -m compileall -q .
```

`run_formal_matrix.py --help` 必须退出码为 0，且不创建运行目录。然后对 4 个任务和 3 个条件各运行 1 次 smoke，共 12 次：

```powershell
$tasks = @("critical-boundary", "reference-detail", "volatile-state", "status-conflict")
$conditions = @("all-resident", "selective-resident", "index-only")
foreach ($task in $tasks) {
  foreach ($condition in $conditions) {
    python run_experiment.py $condition `
      --label win11-smoke-01 `
      --fixture-set pilot-01 `
      --task $task `
      --model gpt-5.6-sol `
      --reasoning-effort medium `
      --platform-tag win11
    if ($LASTEXITCODE -ne 0) { throw "smoke failed: $task / $condition" }
  }
}
```

每个成功运行都应包含 `metadata.json`、`final.md`、`raw.jsonl`、`stderr.log`、`fixture-snapshot/` 和 `prompt.md`，并满足：平台标签为 `win11`、模型为 `gpt-5.6-sol`、推理强度为 `medium`、多行中文 prompt 完整传入、fixture/prompt 哈希稳定。若任一运行失败、语义答案不完整、出现 prompt 截断、读取真实记忆或指标覆盖不完整，立即停止，不进入正式矩阵。

运行器已经针对 Windows 做了以下处理，不要在本机手工绕过：

- 通过 PATH 解析 `codex.cmd`，不把裸 `codex` 直接交给 `CreateProcess`。
- 使用 UTF-8 解码 stdout/stderr。
- 使用 stdin 传递多行 prompt，避免 npm `.cmd` 的 `%*` 截断。
- 使用 POSIX 相对路径排序计算 fixture 哈希。

## 4. 正式矩阵

只有 12 次 smoke 全部通过后，执行 36 次正式矩阵。正式矩阵使用的 Codex CLI 必须与 macOS 证据一致，为 `0.144.1`；如果无法对齐，只能保留为版本不同的兼容性样本，不能直接比较平台：

```powershell
python run_formal_matrix.py `
  --platform-tag win11 `
  --model gpt-5.6-sol `
  --reasoning-effort medium
```

运行器支持中断后继续。出现已存在但不完整的运行目录时会停止；先隔离并记录该目录，不要改脚本跳过。不要做模型敏感性对照，也不要把 smoke 混入正式结果。

## 5. 评分与聚合

正式运行结束后先只回传只读 Review 结果，由 Lee 确认后再写入 `score.json`。四类任务满分如下：

| 任务 | 满分 |
| --- | ---: |
| `critical-boundary` | 6 |
| `reference-detail` | 4 |
| `volatile-state` | 5 |
| `status-conflict` | 5 |

评分命令示例：

```powershell
python score_run.py runs/private/win11/<run-name> `
  --score <score> `
  --max-score <max-score> `
  --protocol-valid <yes-or-no> `
  --review-minutes <measured-minutes> `
  --review-time-method individual `
  --notes "<逐项评分说明>"
```

如果采用批量 Review 均摊时间，必须明确记录批次总时长折算后的每次平均值：

```powershell
python score_run.py runs/private/win11/<run-name> `
  --score <score> --max-score <max-score> --protocol-valid <yes-or-no> `
  --review-minutes <batch-total-minutes-divided-by-batch-size> `
  --review-time-method batch_average --review-batch-size <batch-size> `
  --notes "<逐项评分说明；人工时间为批次均摊>"
```

聚合时只指定 Win11：

```powershell
python aggregate_results.py `
  --platform-tag win11 `
  --prefix formal- `
  --output-stem formal-win11-gpt-5.6-sol-medium
```

正确性、fixture/prompt 哈希、指标覆盖和平台标签必须逐项检查。若 MCP 或其他工具读取无法可靠计量，保留正确性评分，但将工作区指标标为覆盖不完整，不能将其当作 0。

## 6. 回传清单

只回传以下脱敏结果，不回传 `runs/private/win11/`、`raw.jsonl`、临时绝对路径、用户名、会话 ID、真实记忆内容、API Key 或 provider：

- `data/formal-win11-gpt-5.6-sol-medium.csv`
- `data/formal-win11-gpt-5.6-sol-medium.json`
- 36 次运行的门禁摘要和失败运行名称
- Windows 特有异常与修复方式

第二 POC 的公开证据构建器固定读取 macOS 私有运行，Win11 结果不要在 Win11 端运行 `build_public_evidence.py`，待回传 macOS 主环境后再决定是否做跨平台公开对照。完成 Win11 聚合前，不要修改文章、生成跨平台结论、提交或 push。
