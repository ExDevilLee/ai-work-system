# 备份、恢复与迁移 POC 冻结协议

## 当前状态

`formal-matrix-complete-review-complete`。两个 macOS 请求配置已严格按 GLM-5.2、
DeepSeek-V4-Flash 的顺序各完成 54 格，并完成全量只读 Review。合计 99/108 通过；不安排
Win11 验证。

## 执行配置的记录规则

两个 macOS 配置均通过会话执行路径完成 Pilot：

| 字段 | GLM-5.2 (Pilot-01) | DeepSeek-V4-Flash (Pilot-02) | 证据状态 |
| --- | --- | --- | --- |
| 请求模型 | `glm-5.2` | `deepseek-v4-flash` | 用户指定 |
| 请求推理强度 | `unknown` | `unknown` | 用户未冻结 |
| 实际模型/强度 | `unknown` | `unknown` | 会话内无法独立观察 |
| 执行路径 | `session` | `session` | 可验证：无子进程 |

正式矩阵使用相同夹具、Prompt、rubric、任务数、条件数和重复次数，并按配置独立聚合，不混合
计算：

| 字段 | GLM-5.2 正式矩阵 | DeepSeek-V4-Flash 正式矩阵 |
| --- | --- | --- |
| 请求模型 | `glm-5.2` | `deepseek-v4-flash` |
| 请求推理强度 | `max` | `max` |
| 实际模型/强度 | `unknown` | `unknown` |
| 执行路径 | `omp-cli` | `omp-cli` |
| 样本数 | 54 | 54 |

请求配置由真实 CLI 选择器发起，但响应侧不提供独立身份回执，因此 `observed_*` 不从请求值反推。
运行器只公开脱敏后的命令形状，不保存或公开 provider。

正式协议修订为 `formal-r4-manifest-hash-aligned`：完整冻结快照用于身份哈希，模型输入使用任务级
确定性投影；答复上限 350 词，每格执行上限 300 秒。机械门禁在 Pilot rubric 之外增加条件证据
检查，要求缺少 backup、target 或 receipt 时明确降级结论。r4 同时统一 backup manifest 与
integrity report 的 `source_manifest_sha256` 为源清单真实文件哈希。早期完整快照超时、r2 误称
证据和 r3 发现哈希语义不一致的运行均保留在私有目录，不计入正式样本。

## 正式矩阵结果

| 请求配置 | 通过 | 语义失败 | deadline | 主线程中断 |
| --- | ---: | ---: | ---: | ---: |
| GLM-5.2 / max | 52/54 | 1 | 1 | 0 |
| DeepSeek-V4-Flash / max | 47/54 | 1 | 5 | 1 |
| 合计 | 99/108 | 2 | 6 | 1 |

两个语义失败均为条件证据越界：无 receipt 时声称 receipt 校验失败；无 backup hash 时借用 source
自哈希推进恢复资格。详细逐格复验见 `runs/aggregates/macos/formal-r4-*-readonly-review.md`，合并
解释见 `runs/aggregates/macos/formal-r4-macos-cross-config-summary.md`。请求配置不等于响应侧独立
观察到的模型身份或 effort。

## Pilot-01 结果（GLM-5.2）

- 18 格会话执行；18/18 零退出 + final 存在 + 机械评分通过。
- 逐份只读 Review 通过（9 格抽查）：`runs/aggregates/macos/pilot-01-readonly-review.md`。
- 脱敏聚合：`data/pilot-01-macos-glm-5.2.{csv,json}`。

## Pilot-02 结果（DeepSeek-V4-Flash）

- 18 格会话执行；18/18 零退出 + final 存在 + 机械评分通过。
- 两轮修正（透明记录）：5 格 rubric-token 合规改写（禁止列表原文触发否定检查窗口边界）；2 格条件可见性修正（backup-inventory 条件误引 backup-manifest.json，已回归至 version-summary + file-listing）。
- 逐份只读 Review 通过（18 格全覆盖）：`runs/aggregates/macos/pilot-02-readonly-review.md`。
- 脱敏聚合：`data/pilot-02-macos-deepseek-v4-flash.{csv,json}`。

## 冻结材料

Pilot 前应创建且校验下列合成材料：

- `fixtures/pilot-01/source-manifest.json`：权威源记录、范围、版本、哈希与关系。
- `fixtures/pilot-01/backup-manifest.json`：确定性备份清单、排除项和源清单哈希。
- `fixtures/pilot-01/records/*.md`：合成 Markdown 源记录。
- `fixtures/pilot-01/target-state/*.json`：仅用于描述目标端的合成盘点，不含真实目录。
- `prompts/*.md`、`expected/answers.json` 与 `rubrics/pilot-01.json`：任务、预期答案和评分项。

条件固定为 `source-only`、`backup-inventory`、`recovery-gated-bundle`；任务固定为
`clean-restore`、`partial-backup`、`integrity-mismatch`、`target-divergence`、`derived-index` 和
`rollback-receipt`。

## 样本规模与阶段门禁

| 阶段 | 每个配置规模 | 准入条件 | 允许的结论 |
| --- | --- | --- | --- |
| 静态验证 | 无模型调用 | fixture、派生物、泄漏、路径、隐私、评分器和审计测试通过 | 协议材料可开始 Pilot |
| Pilot | `6 × 3 × 1 = 18` | 每格零退出、final 存在、隔离与审计有效、冻结 rubric `18/18`；Pilot-01 只读抽查 9 格，Pilot-02 全量 Review 18 格 | 当前双配置 session 协议可执行 |
| 正式矩阵 | `6 × 3 × 3 = 54` | 每格完整性契约与机械 rubric 通过；54 格全量只读 Review 通过 | 当前请求配置在冻结合成场景中的正式结果 |

本 POC 不安排 Win11 验证。系列策略（`CROSS-PLATFORM-VALIDATION-STRATEGY.md`）从 POC 06 起默认
不在 Win11 重复矩阵；Lee 已确认 P8 同样不安排。文章结论口径已升级为“macOS 双配置正式矩阵
99/108”，始终不声明跨平台结果。

## 停止条件

任一条件满足即停止当前阶段，不启动下一格或下一阶段：

- fixture、备份 manifest、完整性报告或条件视图与权威源不一致。
- Prompt、条件视图或索引泄漏预期答案、评分项或其他条件专属信息。
- 输出建议自动覆盖、合并、删除、恢复或把派生索引作为权威事实。
- 输出缺少必须的来源 ID、适用范围或人工门禁说明。
- 访问隔离夹具外文件、真实记忆、用户级规则、插件或未批准的工具。
- 退出码非零、最终答复缺失、UTF-8/换行异常、运行元数据不完整，或命令调用无法完整审计。
- 同一批次内模型、推理强度、执行路径、平台标记、夹具、Prompt 或 rubric 发生变化。

## 隐私与公开边界

- `runs/private/` 保存完整事件、final、stderr、计时、私有 metadata 和评分，不提交。
- `runs/public/` 仅作本地脱敏中间层，同样不提交。
- 提交的公开包只包含合成夹具、校验与运行代码、脱敏聚合、manifest 和必要代表样本。
- 禁止出现真实用户名、账号、绝对路径、设备名、会话 ID、密钥、存储地址、真实记忆或 provider。

## 文章允许使用的结论

两个 macOS 请求配置（GLM-5.2 + DeepSeek-V4-Flash）已完成正式矩阵和全量只读 Review。文章
可描述 99/108 通过，并必须分别披露 2 个语义失败、6 个 deadline 和 1 个主线程中断。

文章不得声称已经验证真实跨设备双向同步、自动冲突合并、真实备份可靠性、性能、成本、所有工具
兼容性、跨平台复现或任意模型上的普遍效果。
