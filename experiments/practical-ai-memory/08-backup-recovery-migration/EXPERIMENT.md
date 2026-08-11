# 备份、恢复与迁移 POC 冻结协议

## 当前状态

`dual-pilot-accepted`（GLM-5.2 + DeepSeek-V4-Flash，均为 session 执行）。两个配置各自完成 18 格
Pilot，最终接受状态均通过机械门禁；Pilot-01 完成 9 格抽查，Pilot-02 完成 18 格全量只读 Review。
未运行正式矩阵或 Win11 验证。

## 执行配置的记录规则

两个 macOS 配置均通过会话执行路径完成 Pilot：

| 字段 | GLM-5.2 (Pilot-01) | DeepSeek-V4-Flash (Pilot-02) | 证据状态 |
| --- | --- | --- | --- |
| 请求模型 | `glm-5.2` | `deepseek-v4-flash` | 用户指定 |
| 请求推理强度 | `unknown` | `unknown` | 用户未冻结 |
| 实际模型/强度 | `unknown` | `unknown` | 会话内无法独立观察 |
| 执行路径 | `session` | `session` | 可验证：无子进程 |

正式矩阵仍需两个独立 macOS 配置使用相同夹具、Prompt、rubric、任务数、条件数和重复次数，
并按配置独立聚合，不混合计算。

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

本 POC 不安排 Win11 验证。系列策略（`CROSS-PLATFORM-VALIDATION-STRATEGY.md`）从 POC 06 起默认
不在 Win11 重复矩阵；Lee 已确认 P8 同样不安排。文章结论口径为"macOS 双配置 Pilot 实测"，
不声明跨平台结果。

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

两个 macOS 配置（GLM-5.2 + DeepSeek-V4-Flash）均完成 Pilot 后，文章可描述：在冻结合成场景中，
完整性检查、冲突停机、人工恢复门禁和派生索引重建是否能被两个配置正确执行。

文章不得声称已经验证真实跨设备双向同步、自动冲突合并、真实备份可靠性、性能、成本、所有工具
兼容性、跨平台复现或任意模型上的普遍效果。
