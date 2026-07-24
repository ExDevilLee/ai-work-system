# Win11 复现方案

本文档用于在原生 Windows 11 设备上复现第四个 POC：比较长期记忆面对冲突、过期、替代、范围收窄和紧急撤销时的三种生命周期治理机制。

macOS 的实验与文章基线提交为 `938e2af9313905867e67df9ad7aa061d6f223ad2`，并已完成 45 次正式运行。Win11 应同步到包含该基线和本复现文档的最新 `origin/main`，同时确认实验基线仍在当前 HEAD 的祖先链中。冻结夹具、提示、评分表、模型配置和 Codex CLI 版本必须与 macOS 一致；全部门禁通过后，才能把文章中的 macOS 结论扩展为跨平台复现。

## 1. 仓库与执行边界

- 仓库：<https://github.com/ExDevilLee/ai-work-system>
- 分支：`main`
- 实验与文章基线：`938e2af9313905867e67df9ad7aa061d6f223ad2`
- 执行提交：包含本复现文档的最新 `origin/main`，开始实验后冻结并回传 SHA
- POC 目录：`experiments/practical-ai-memory/04-memory-lifecycle-governance`
- 模型：`gpt-5.6-sol`
- 推理强度：`medium`
- Codex CLI：`0.145.0`
- Smoke：5 个任务 × 3 个条件，共 15 次
- 正式矩阵：5 个任务 × 3 个条件 × 3 次，共 45 次

只允许使用本 POC 的 `fixtures/pilot-01/`。禁止读取或复制真实长期记忆、真实项目资料和用户级 Codex 插件；禁止修改 `content/articles/`、README、Roadmap、发布配置、夹具、提示、冻结答案或评分表。

不要记录或显示模型 provider。不要回传 Windows 用户名、绝对路径、会话 ID、API Key、原始事件或私有运行内容。`runs/private/win11/` 不能提交或 Push。

## 2. 同步与环境门禁

在 PowerShell 中进入仓库后执行：

```powershell
git fetch origin main
git switch main
git pull --ff-only origin main
git status --short
git rev-parse HEAD
git rev-parse origin/main
git merge-base --is-ancestor 938e2af9313905867e67df9ad7aa061d6f223ad2 HEAD
```

继续前必须满足：

- `HEAD` 与 `origin/main` 完全一致。
- `git merge-base --is-ancestor` 退出码为 0，确认包含实验基线。
- 开始 Smoke 后冻结当前 HEAD；除非修复协议缺陷，不再同步其他提交。
- 工作区和暂存区干净。
- 现有 stash 不需要删除，但不得应用到本次实验。
- 如果同名未跟踪聚合文件阻塞同步，先按 SHA-256 与远端 blob 比较；未经 Lee 确认不要删除。

记录环境版本，但回传时只保留脱敏版本信息：

```powershell
$PSVersionTable.PSVersion
python --version
codex --version
git --version
Get-Command python
Get-Command codex
git config --get core.autocrlf
```

确认当前是原生 Windows 11，不是 WSL；Codex 已登录，并能使用目标模型与推理强度。Codex CLI 必须为 `0.145.0`。版本不一致时停止，不把不同 CLI 的结果直接与 macOS 比较。

检查 LF 属性：

```powershell
git check-attr eol -- run_experiment.py
git check-attr eol -- prompts/unresolved-conflict.md
git check-attr eol -- fixtures/pilot-01/conditions/lifecycle-governed/AGENTS.md
git check-attr eol -- fixtures/pilot-01/common/records/INDEX.md
```

四项都必须显示 `eol: lf`。即使 `core.autocrlf=true`，也不能手工转换夹具或提示。属性不满足时停止，由 macOS 主环境修复后再同步。

## 3. 静态门禁

帮助命令必须退出码为 0，并且不能创建运行目录：

```powershell
python run_experiment.py --help
python run_pilot_matrix.py --help
python run_formal_matrix.py --help
python aggregate_results.py --help
python score_run.py --help
```

然后执行：

```powershell
python -m unittest discover -p "test_*.py"
python validate_fixtures.py
python -m compileall -q .
```

预期为 32 项单元测试通过，夹具验证报告 3 个条件和 5 个任务。任一命令失败都立即停止，不启动 Smoke。

## 4. 单次运行门禁

Win11 上曾出现 PowerShell 读取被沙箱拒绝后改用 MCP 读取的情况。因此不能只看退出码；每次运行结束后必须检查 `metadata.json`。

在当前 PowerShell 会话定义门禁函数：

```powershell
function Assert-LifecycleRun {
  param(
    [Parameter(Mandatory=$true)][string]$RunName,
    [Parameter(Mandatory=$true)][string]$Purpose
  )

  $runDir = Join-Path "runs/private/win11" $RunName
  $required = @(
    "metadata.json",
    "final.md",
    "raw.jsonl",
    "stderr.log",
    "prompt.md"
  )
  foreach ($name in $required) {
    if (-not (Test-Path (Join-Path $runDir $name) -PathType Leaf)) {
      throw "missing file: $RunName / $name"
    }
  }
  if (-not (Test-Path (Join-Path $runDir "fixture-snapshot") -PathType Container)) {
    throw "missing fixture snapshot: $RunName"
  }

  $metadata = Get-Content (Join-Path $runDir "metadata.json") -Raw -Encoding UTF8 |
    ConvertFrom-Json
  if ($metadata.exit_code -ne 0) { throw "non-zero exit: $RunName" }
  if ($metadata.platform_tag -ne "win11") { throw "wrong platform: $RunName" }
  if ($metadata.requested_model -ne "gpt-5.6-sol") { throw "wrong model: $RunName" }
  if ($metadata.reasoning_effort -ne "medium") { throw "wrong effort: $RunName" }
  if ($metadata.codex_version -ne "codex-cli 0.145.0") { throw "wrong CLI: $RunName" }
  if ($metadata.purpose -ne $Purpose) { throw "wrong purpose: $RunName" }
  if ($metadata.plugins_enabled -ne $false) { throw "plugins enabled: $RunName" }
  if ($metadata.runtime_tool_access_calls -ne 0) { throw "runtime access: $RunName" }
  if ($metadata.protocol_environment_isolated -ne $true) {
    throw "environment not isolated: $RunName"
  }
  if ($metadata.workspace_metric_coverage_complete -ne $true) {
    throw "workspace metric coverage incomplete: $RunName"
  }
  if ($metadata.workspace_metric_unmeasured_tool_calls -ne 0) {
    throw "unmeasured tool calls: $RunName"
  }
  if ($metadata.workspace_output_bytes_reliable -ne $true) {
    throw "workspace output unreliable: $RunName"
  }
  if ($null -eq $metadata.usage) { throw "missing usage: $RunName" }
  if (-not (Get-Content (Join-Path $runDir "final.md") -Raw -Encoding UTF8).Trim()) {
    throw "empty final answer: $RunName"
  }
}
```

该函数只读取运行产物，不修改原始记录。若门禁失败，立即停止并隔离当前批次，不要为了继续运行而修改 `metadata.json`。

## 5. Smoke：15 次全组合验证

Smoke 需要覆盖每个任务和条件，而不是只选择一个“看起来能跑”的样例：

```powershell
$tasks = @(
  "explicit-supersession",
  "unresolved-conflict",
  "time-expiry",
  "scope-narrowing",
  "emergency-revocation"
)
$conditions = @("append-only", "latest-wins", "lifecycle-governed")
$smokeLabel = "pilot-win11-smoke-01"

foreach ($task in $tasks) {
  foreach ($condition in $conditions) {
    $runName = "$smokeLabel-$task-$condition"
    python run_experiment.py $condition `
      --label $smokeLabel `
      --fixture-set pilot-01 `
      --task $task `
      --model gpt-5.6-sol `
      --reasoning-effort medium `
      --platform-tag win11
    if ($LASTEXITCODE -ne 0) { throw "smoke process failed: $runName" }
    Assert-LifecycleRun -RunName $runName -Purpose "protocol pilot"
  }
}
```

15 次运行门禁全部通过后，再逐份只读检查 `final.md`：

- 完整回答提示中的编号问题。
- 没有出现“请提供问题”、prompt 截断、沙箱拒绝后未恢复或明显自相矛盾。
- 来源只来自隔离 fixture。
- 临时绝对路径链接如果只指向本次隔离工作区，可以作为 Windows 私有输出表现记录，不单独判协议失败；不得回传链接文本。
- 真实用户路径、隔离目录外读取、插件读取、未知 MCP 分类或指标假完整均为协议失败。

任何一项失败都把整批 Smoke 移入 `work/` 下的隔离目录并记录脱敏原因，然后停止。修复必须由干净提交承载；同步新提交后从头重新运行 15 次 Smoke，不能复用旧批次中的成功样本。

## 6. 正式矩阵：45 次冻结运行

只有完整 Smoke 通过后才能启动正式矩阵。正式顺序与 macOS 调度器一致：每轮包含 15 个任务/条件组合，共 3 轮。

下面的包装器会在每次运行后立即执行元数据门禁，避免指标覆盖失败被后续运行掩盖：

```powershell
$tasks = @(
  "explicit-supersession",
  "unresolved-conflict",
  "time-expiry",
  "scope-narrowing",
  "emergency-revocation"
)
$conditions = @("append-only", "latest-wins", "lifecycle-governed")

for ($repeat = 1; $repeat -le 3; $repeat++) {
  $label = "formal-{0:D2}" -f $repeat
  $offset = $repeat - 1
  for ($taskIndex = 0; $taskIndex -lt $tasks.Count; $taskIndex++) {
    $start = ($taskIndex + $offset) % $conditions.Count
    for ($conditionIndex = 0; $conditionIndex -lt $conditions.Count; $conditionIndex++) {
      $condition = $conditions[($start + $conditionIndex) % $conditions.Count]
      $task = $tasks[$taskIndex]
      $runName = "$label-$task-$condition"
      $runDir = Join-Path "runs/private/win11" $runName

      if (Test-Path $runDir) {
        Assert-LifecycleRun -RunName $runName -Purpose "formal run"
        Write-Host "SKIP complete run: $runName"
        continue
      }

      python run_experiment.py $condition `
        --label $label `
        --fixture-set pilot-01 `
        --task $task `
        --model gpt-5.6-sol `
        --reasoning-effort medium `
        --platform-tag win11
      if ($LASTEXITCODE -ne 0) { throw "formal process failed: $runName" }
      Assert-LifecycleRun -RunName $runName -Purpose "formal run"
    }
  }
}
```

如果出现 HTTP 429：

1. 立即停止，不重试当前槽位，不启动后续槽位。
2. 将不完整槽位整体移到 `work/` 下的隔离目录。
3. 记录是否存在 `Retry-After`，没有时不要估算服务端恢复时间。
4. 冷却后先重新执行静态门禁。
5. 只补失败槽位；已经完成且哈希未变的正式运行继续保留。
6. 恢复包装器会校验并跳过完整槽位，不能创建替代样本改变每组 `n=3`。

最终必须得到 45 个有效运行，15 个任务/条件组合各 `n=3`。

## 7. 正式运行审计

执行结束后先做只读审计，不评分：

- 45/45 文件完整、退出码为 0。
- 15 个分组各 `n=3`。
- 45/45 平台为 `win11`。
- 45/45 模型、推理强度和 CLI 与冻结配置一致。
- 三个条件各自的 fixture SHA-256 稳定。
- 五个任务各自的 prompt SHA-256 稳定。
- 45/45 `plugins_enabled=false`。
- 45/45 `runtime_tool_access_calls=0`。
- 45/45 环境隔离有效。
- 45/45 工作区指标覆盖完整且输出可靠。
- MCP `unknown/unmeasured=0`。
- 不修改 `raw.jsonl`、`metadata.json` 或 `final.md`。

然后逐份读取 `final.md`，依据冻结的 `expected/rubric.json` 形成评分建议，但不要创建 `score.json`。

| 任务 | 单次满分 |
| --- | ---: |
| `explicit-supersession` | 6 |
| `unresolved-conflict` | 5 |
| `time-expiry` | 5 |
| `scope-narrowing` | 6 |
| `emergency-revocation` | 6 |

只读 Review 回传每个运行的建议得分、`protocol_valid`、`unsupported_claims` 和一句依据。等待 Lee 确认后再进入正式评分。

## 8. 评分与聚合

评分必须记录真实 Review 时间，不能估算或补造。可以逐次计时，也可以记录完整批次总时长后均摊到 45 次：

```powershell
python score_run.py runs/private/win11/<run-name> `
  --score <score> `
  --max-score <max-score> `
  --protocol-valid <yes-or-no> `
  --review-minutes <真实批次总分钟数除以45> `
  --review-time-method batch_average `
  --review-batch-size 45 `
  --irrelevant-facts 0 `
  --unsupported-claims 0 `
  --notes "<逐项评分说明>"
```

45 份 `score.json` 完成并独立校验后，只聚合 Win11：

```powershell
python aggregate_results.py `
  --platform-tag win11 `
  --prefix formal- `
  --output-stem formal-win11-gpt-5.6-sol-medium
```

聚合后检查：

- JSON 有 15 个任务/条件分组。
- 每组 `n=3`。
- 每组 `workspace_metrics_n=3`。
- 模型为 `gpt-5.6-sol`。
- 推理强度为 `medium`。
- Codex CLI 为 `0.145.0`。
- CSV 为 45 行正式运行，不含 Smoke。

最后计算两个聚合文件的 SHA-256。

## 9. 回传与停止点

只回传：

- 固定提交、脱敏环境版本和门禁摘要。
- Smoke 与正式矩阵的完成、跳过、失败数量。
- 15 个分组的 `n`、`workspace_metrics_n` 和 correctness。
- 三个条件的总分。
- MCP workspace、non-workspace 和 unknown 调用摘要。
- Windows 特有异常及脱敏处理方式。
- 两个聚合文件的大小与 SHA-256。
- Git 状态摘要。

允许回传的文件只有：

- `data/formal-win11-gpt-5.6-sol-medium.csv`
- `data/formal-win11-gpt-5.6-sol-medium.json`

不要回传或上传 `runs/private/win11/`、`raw.jsonl`、`score.json`、临时绝对路径、用户名、会话 ID、provider、API Key 或真实记忆内容。

Win11 端不要修改文章，不生成跨平台结论，不构建公开证据，不提交，不 Push。两个聚合文件完成并校验后暂停，由 macOS 主环境下载、复核并决定文章是否可以推进到 `ready`。
