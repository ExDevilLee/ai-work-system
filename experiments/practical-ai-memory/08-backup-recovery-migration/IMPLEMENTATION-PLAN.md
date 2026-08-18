# P8 实施计划：先校验，再运行

## 决策与里程碑

推荐先建立“合成权威源、备份清单和恢复门禁”这一条窄链路，再扩展到运行器和跨平台 Level 3 验证。这样
每个阶段都可独立验证，也不会接触真实备份数据。

备选路径：

| 路径 | 取舍 |
| --- | --- |
| 先做合成夹具与静态校验，再接模型运行 | 推荐；失败成本低，能先发现泄漏和错误事实模型。 |
| 直接用真实备份跑端到端恢复 | 不采用；敏感、不可复现，且会把工具故障与协议缺陷混在一起。 |
| 先写公开文章再补 POC | 不采用；会倒逼证据和结论，违背系列证据边界。 |

## 目标文件结构

```text
08-backup-recovery-migration/
├── .gitattributes
├── .gitignore
├── README.md
├── DESIGN.md
├── EXPERIMENT.md
├── IMPLEMENTATION-PLAN.md
├── fixture_model.py
├── generate_backup_bundle.py
├── validate_fixtures.py
├── run_experiment.py
├── matrix_support.py
├── run_pilot_matrix.py
├── run_formal_matrix.py
├── score_run.py
├── aggregate_results.py
├── fixtures/pilot-01/
│   ├── source-manifest.json
│   ├── backup-manifest.json
│   ├── records/
│   ├── target-state/
│   └── conditions/
├── prompts/
├── expected/
├── rubrics/
└── test_*.py
```

## 实施顺序

1. 建立 manifest schema 与合成记录。
   - `source-manifest.json` 必须拒绝绝对路径、重复 ID、未知状态、循环关系和无来源记录。
   - 备份 manifest 必须只列出源文件；派生索引必须以排除理由出现，不得伪装成可恢复源。

2. 实现确定性生成与反向校验。
   - 根据源 manifest 生成备份 manifest、三种条件视图和完整性报告。
   - 反向验证每个文件哈希、版本、范围、来源 ID、排除项和目标端分歧标记。
   - 测试缺失文件、哈希篡改、过时版本、冲突目标和索引复制企图均被拒绝。

3. 冻结任务、Prompt、预期答案与评分表。
   - 每个任务同时评分事实、范围、来源、允许/禁止动作和人工下一步。
   - 评分器必须把“自动覆盖/合并/删除/恢复”视为协议失败。
   - 条件名称、答案和 rubric 不得进入 Agent Prompt。

4. 实现隔离运行与审计。
   - 独立临时工作区、`read-only`、`--ephemeral`、UTF-8 stdin、关闭用户级插件。
   - 明确记录 `requested_model`、`requested_effort`、`observed_model`、`observed_effort`、执行路径和平台；未知值保留未知。
   - GLM 会话运行若不能提供等价的命令隔离和审计，应单列为会话执行路径，不与 CLI 数据混合。

5. 先用 GLM 配置跑 Pilot。
   - 在运行前由 Lee 冻结 GLM 推理强度与执行路径。
   - `18/18` 机械门禁与逐份只读 Review 通过，才允许第二配置 Pilot；否则新标签修订协议并从头 Pilot。

6. 完成双配置 macOS 正式矩阵与公开证据候选。
   - 每个配置 `54` 格；分别评分、真实计时 Review、脱敏聚合。
   - 生成公开 `evidence/` 前运行隐私扫描、代表样本哈希校验与 manifest 数量校验。

7. 不安排 Win11 验证，并决定文章是否进入写作。
   - 当前系列策略从 POC 06 起默认不在 Win11 重复矩阵；Lee 已确认 P8 同样不安排。
   - 文章使用两个 macOS 正式矩阵支持的 99/108 口径，不声明跨平台复现。

## 当前验收状态

- [x] 全部合成 source/backup manifest 可验证，且生成结果可重现。
- [x] 三种条件的冻结材料通过静态一致性、泄漏与路径校验。
- [x] 六个故障场景均能触发对应的停止或人工门禁。
- [x] 私有运行目录由 `.gitignore` 排除；公开包只包含脱敏聚合与只读 Review。
- [x] 两个请求配置的 requested/observed metadata 分开记录；不可观察字段保持 `unknown`。
- [x] 两组 macOS Pilot 的最终接受状态均通过 18/18 机械门禁；Pilot-01 抽查 9 格，Pilot-02
  全量 Review 18 格。
- [x] 文章已升级为正式矩阵口径，并披露全部失败类别。
- [x] 已冻结正式运行器、两个请求配置、`max` 强度、任务级投影、condition-aware 门禁、三轮
  旋转顺序与严格续跑契约。
- [x] GLM-5.2 的 54 格正式矩阵、机械评分和全量只读 Review 已完成（52/54）。
- [x] DeepSeek-V4-Flash 的 54 格正式矩阵、机械评分和全量只读 Review 已完成（47/54）。

## 后续决策门禁

正式矩阵已按 GLM-5.2、DeepSeek-V4-Flash 顺序完成，最终公开证据和文章口径已升级。P8 不安排
Win11 验证，不生成跨平台结论。后续若扩充真实恢复或其他平台，必须建立新的协议标签和接受门禁。
