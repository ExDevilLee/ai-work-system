# Win11 验证方案

本文档用于在真实 Windows 11 设备上复现第一篇文章的三层 AI 记忆系统 POC。Win11 正式验证已于 2026-07-20 完成；本文继续作为复现手册保留。最终结果和 macOS 对照见 [`analysis/formal-macos-win11-comparison.md`](analysis/formal-macos-win11-comparison.md)。

## 1. 仓库与安全边界

本次验证操作的 GitHub 仓库是：

- 仓库：<https://github.com/ExDevilLee/ai-work-system>
- 目标分支：`main`
- POC 目录：`experiments/practical-ai-memory/01-three-layer-memory`
- 验证主题：三层 AI 记忆系统 POC

macOS 与 Win11 已分别完成 `gpt-5.6-sol medium` 的 18 次正式实验；macOS 另有 6 次探索性模型对照。复现时仍只验证 Win11，不混入模型敏感性对照。

执行前必须确认：

- 使用上述仓库和 `main` 分支，不要在 CodexClaw 主项目或其他同名仓库中执行。
- 只使用 POC 自带的 `fixtures/`，不要读取或复制真实 CodexClaw 长期记忆目录。
- 不修改 `content/articles/`、`README`、发布配置或生产记忆文件。
- 不向 GitHub push 私有原始运行数据；只回传脱敏后的聚合结果和经过筛选的公开证据。
- 不记录或显示模型 provider；只记录模型名、推理强度、平台和工具版本。

## 2. 环境门禁

在 PowerShell 中进入 POC 目录后，依次执行：

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
git lfs version
git check-attr eol -- fixtures/pilot-02/baseline/PROJECT_NOTES.md
git check-attr eol -- prompts/current-task.md
```

记录输出，但不要把用户名、绝对路径、会话 ID 或密钥提交到仓库。确认当前是原生 Windows 11，而不是 WSL；确认 Codex CLI 已登录，并能使用 `gpt-5.6-sol` 与 `medium` 推理强度。两个 `git check-attr` 命令都应显示 `eol: lf`；即使本机设置了 `core.autocrlf=true`，实验夹具和提示也必须保持 LF，保证字节级哈希与 macOS 一致。

如果远程仓库、分支、工作区状态或 Codex 登录状态不符合预期，先停止，不要用手工改参数绕过门禁。

## 3. 依赖与 smoke test

先运行跨平台哈希回归测试，再验证仓库已经提交的 macOS 精简公开证据包：

```powershell
python -m unittest test_run_experiment.py
python validate_committed_evidence.py
```

`runs/public/` 是被 Git 忽略的本地脱敏中间层，新检出的仓库没有该目录是正常状态。此时不要把 `0 public runs` 当作阻塞；`validate_public_runs.py` 只在本机完成脱敏导出后运行。

`tree_checksum()` 必须按 POSIX 相对路径字符串排序，不能直接依赖 Windows 或 macOS 的 `Path` 排序。Windows 默认不区分大小写的路径顺序可能把 `references/INDEX.md` 排到小写文件之后，导致内容未变化但夹具哈希不同。

然后执行 6 次 smoke test，每个任务各运行 Baseline 和 Layered 一次。下面的两条命令先用 `current-task`，再把任务名替换为 `stable-rules` 和 `reference-retrieval`：

```powershell
python run_experiment.py baseline `
  --label win11-smoke-01 `
  --fixture-set pilot-02 `
  --task current-task `
  --model gpt-5.6-sol `
  --reasoning-effort medium `
  --platform-tag win11

python run_experiment.py layered `
  --label win11-smoke-01 `
  --fixture-set pilot-02 `
  --task current-task `
  --model gpt-5.6-sol `
  --reasoning-effort medium `
  --platform-tag win11
```

运行目录必须位于 `runs/private/win11/`。每次运行应有 `metadata.json`、`final.md`、`raw.jsonl` 和 `stderr.log`，并记录 `platform_tag=win11`、模型、推理强度、夹具哈希和提示哈希。确认命令没有逃逸到真实记忆目录后，再继续下一阶段。

## 4. 正式矩阵

只有 smoke test 全部通过后，执行 18 次正式矩阵：

正式矩阵前，Win11 Codex CLI 应与 macOS 正式证据使用的 `0.144.1` 对齐。不同 CLI 版本可以用于 smoke 兼容性检查，但不能直接归因于平台差异；如果 Win11 无法安装相同版本，应停止正式矩阵，并把当前结果单列为版本不同的兼容性样本。

```powershell
python run_formal_matrix.py `
  --platform-tag win11 `
  --model gpt-5.6-sol `
  --reasoning-effort medium
```

第一阶段不执行 Windows 模型敏感性对照，避免把平台差异和模型差异混在一起。每组任务和条件至少 3 次，运行器支持中断后继续执行。

## 5. 评分与聚合

先依据 `expected/answers.json` 逐项形成评分建议，由 Lee 确认后再写入 `score.json`。三个任务的满分分别是：

| 任务 | 满分 |
| --- | ---: |
| `current-task` | 5 |
| `stable-rules` | 10 |
| `reference-retrieval` | 8 |

对每次运行完成评分和指标审计，下面的占位符必须替换为该任务的真实评分和复核说明：

```powershell
python score_run.py runs/private/win11/<run-name> `
  --score <score> `
  --max-score <max-score> `
  --protocol-valid <yes-or-no> `
  --notes "<Lee 确认的逐项评分说明>"
python audit_run_metrics.py runs/private/win11/<run-name>
```

聚合时明确指定平台和输出名称：

```powershell
python aggregate_results.py `
  --platform-tag win11 `
  --prefix formal- `
  --output-stem formal-win11-gpt-5.6-sol-medium
```

正确性按各任务自己的标准答案逐项评分，不用总分掩盖具体失败。已识别且能通过 fixture 内容匹配确认来源的 MCP workspace 读取可以计入工作区调用次数和完整结果文本字节；资源枚举和工作区外读取不计入。无法可靠统计的调用次数、输出量、耗时或 token 必须标记为 unreliable，不得估算补齐。出现无法分类的 MCP 调用时，该运行的正确性仍可保留，但工作区指标必须按覆盖不完整处理，不能记为 0。一次失败只能记录为该运行的失败证据，不能直接推断 Win11 不兼容。

## 6. 脱敏与回传

先在 Win11 本地导出脱敏运行记录：

```powershell
python export_public_run.py runs/private/win11/<run-name> --platform-tag win11
python validate_public_runs.py --require-runs
```

不要将 `runs/private/` 或 `runs/public/` 全量复制回 GitHub。建议只回传：

- `data/formal-win11-gpt-5.6-sol-medium.csv`
- `data/formal-win11-gpt-5.6-sol-medium.json`
- 对应的 `analysis/` 报告
- 经过筛选的代表性证据

回传前逐项检查 Windows 用户名、Windows 绝对路径、Codex 会话 ID、真实记忆内容、API Key、内部域名、内部项目路径和 provider 信息。任何一项未清理都停止回传。

## 7. 结果回传清单

请把以下信息一起带回 macOS 主环境：

1. `platform_tag=win11` 的环境版本和执行日期。
2. 18 次运行的聚合 CSV/JSON，以及失败运行名称。
3. 每组 Baseline/Layered 的逐项得分和是否通过协议门禁。
4. Windows 特有异常、路径兼容性问题、Codex CLI 行为差异和修复方式。
5. 脱敏检查结果，以及确认没有上传私有原始记录。

完成上述证据门禁后，可以写“同一协议已在 macOS 与 Win11 独立复现”，但不能扩展为所有 Windows 环境都兼容，也不能写成已经验证跨设备双向同步。

## 8. 中断与误触发处理

- 参数探测只使用已经确认支持 `argparse` 的脚本版本；拉取更新后先执行 `python run_formal_matrix.py --help`，帮助命令必须只显示帮助并以退出码 0 结束。
- 如果旧脚本因 `--help` 误启动任务，在 Codex 调用前失败且仓库仍干净，可以把残留运行目录移出仓库并记录原路径、时间和失败阶段；不要删除或覆盖无法确认来源的目录。
- Windows npm 的 `codex.cmd` 可能截断作为命令参数传入的多行 prompt。运行器必须向 Codex 传入 `-`，并通过 UTF-8 stdin 发送完整 prompt；不要恢复为把 prompt 文本直接追加到 `.cmd` 参数。
- 任一运行目录已存在但缺少 `metadata.json` 时，矩阵脚本会停止。先隔离并检查该目录，不要通过修改脚本跳过不完整证据。
- 任何门禁失败后都不要继续 smoke test；修复并重新记录环境检查结果后再执行。
