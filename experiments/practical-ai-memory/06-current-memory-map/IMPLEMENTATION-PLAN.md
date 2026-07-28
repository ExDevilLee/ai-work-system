# 当前记忆地图 POC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立可复现的第 6 个 POC，分别验证状态投影对 Agent 当前状态恢复的影响，以及相同事实下可视化地图对单人探索性治理任务的影响。

**Architecture:** 冻结 `manifest.json` 作为规范化事实源，由确定性生成器产生普通索引、机器可读状态投影、状态表和可视化地图。Agent 通道沿用前序 POC 的隔离 Codex CLI 运行与评分契约；人工通道使用 Python 标准库本地服务保存私有交互结果，并通过相同事实集合校验隔离视觉表达变量。

**Tech Stack:** Python 3.11+ 标准库、Codex CLI、`unittest`、HTML/CSS/JavaScript、Playwright 验收、Markdown/JSON 合成夹具。

---

## 文件结构

```text
06-current-memory-map/
├── .gitattributes
├── .gitignore
├── DESIGN.md
├── EXPERIMENT.md
├── IMPLEMENTATION-PLAN.md
├── README.md
├── fixture_model.py
├── generate_views.py
├── validate_fixtures.py
├── run_experiment.py
├── matrix_support.py
├── run_pilot_matrix.py
├── run_formal_matrix.py
├── score_run.py
├── aggregate_results.py
├── human_experiment.py
├── human/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── fixtures/pilot-01/
│   ├── manifest.json
│   ├── records/**/*.md
│   ├── generated/
│   │   ├── flat-index.md
│   │   ├── state-projection.json
│   │   ├── state-table.json
│   │   └── visual-map.json
│   └── conditions/*/AGENTS.md
├── human-fixtures/
│   ├── pack-a.json
│   └── pack-b.json
├── prompts/*.md
├── expected/
│   ├── answers.json
│   └── rubric.json
└── test_*.py
```

职责边界：

- `fixture_model.py` 只负责 schema 解析、规范化和事实集合提取。
- `generate_views.py` 只负责从 manifest 确定性生成四类派生产物。
- `validate_fixtures.py` 只负责跨文件一致性、泄漏和隐私门禁。
- Agent 运行、矩阵、评分与聚合沿用第 5 个 POC 的独立脚本边界。
- `human_experiment.py` 只提供静态页面和私有结果写入 API，不参与答案评分规则生成。
- `human/app.js` 只控制条件顺序、答题状态、计时和事件提交。

## Task 1：建立协议骨架和状态模型

**Files:**

- Create: `EXPERIMENT.md`
- Create: `README.md`
- Create: `.gitignore`
- Create: `.gitattributes`
- Create: `fixture_model.py`
- Create: `test_fixture_model.py`
- Modify: repository root `.gitattributes`

- [ ] **Step 1: 写状态模型失败测试**

在 `test_fixture_model.py` 创建临时 manifest，覆盖五种状态、缺失来源、非法关系、重复 ID 和绝对路径：

```python
class FixtureModelTest(unittest.TestCase):
    def test_load_manifest_rejects_absolute_source(self) -> None:
        manifest = valid_manifest()
        manifest["records"][0]["source"] = "/private/example.md"
        with self.assertRaisesRegex(ValueError, "relative source"):
            load_manifest(write_manifest(manifest))

    def test_fact_set_is_stable(self) -> None:
        model = load_manifest(write_manifest(valid_manifest()))
        self.assertEqual(
            fact_set(model),
            {
                ("MEM-001", "active", "project", "records/decisions/current.md"),
                ("MEM-002", "superseded", "project", "records/decisions/old.md"),
                ("MEM-003", "conflict", "global", "records/observations/conflict.md"),
                ("MEM-004", "pending-validation", "global", "records/observations/pending.md"),
                ("MEM-005", "active", "macos", "records/rules/scoped.md"),
            },
        )
```

- [ ] **Step 2: 运行测试并确认模块缺失失败**

Run: `python3 -m unittest test_fixture_model.py -v`

Expected: `ModuleNotFoundError: No module named 'fixture_model'`。

- [ ] **Step 3: 实现最小状态模型 API**

`fixture_model.py` 固定暴露四个函数：

| 函数 | 输入 | 成功结果 | 失败结果 |
| --- | --- | --- | --- |
| `load_manifest` | manifest `Path` | 已通过 schema 校验的字典 | 汇总错误后抛出 `ValueError` |
| `validate_manifest` | manifest 字典 | 错误字符串列表，合法时为空 | 不抛异常 |
| `fact_set` | 合法 manifest 字典 | `(id, status, scope, source)` 集合 | 非法记录抛出 `ValueError` |
| `canonical_json` | JSON 可序列化对象 | 规范化 UTF-8 bytes | 不可序列化时抛出 `TypeError` |

模块常量 `VALID_STATUSES` 固定为 `active`、`superseded`、`conflict` 和 `pending-validation`。

`canonical_json()` 使用 `sort_keys=True`、`ensure_ascii=False`、紧凑分隔符和结尾 LF，保证 macOS/Win11 字节一致。

- [ ] **Step 4: 写协议和仓库边界文件**

`EXPERIMENT.md` 从 `DESIGN.md` 提炼冻结协议，明确 Agent 三条件、人工两条件、15 次 Pilot、45 次 macOS 正式矩阵和 Win11 Level 2 Smoke。`.gitignore` 至少包含：

```gitignore
runs/private/
human-results/private/
data/
__pycache__/
```

局部与根级 `.gitattributes` 为本 POC 的 Python、Markdown、JSON、HTML、CSS 和 JavaScript 声明 `text eol=lf`。

- [ ] **Step 5: 运行测试和文档检查**

Run:

```bash
python3 -m unittest test_fixture_model.py -v
npm run lint:md -- experiments/practical-ai-memory/06-current-memory-map/DESIGN.md experiments/practical-ai-memory/06-current-memory-map/EXPERIMENT.md experiments/practical-ai-memory/06-current-memory-map/README.md
git diff --check
```

Expected: 单元测试与 Markdown lint 全部通过。

- [ ] **Step 6: 提交状态模型骨架**

```bash
git add .gitattributes experiments/practical-ai-memory/06-current-memory-map
git diff --cached --check
git commit -m "feat(memory): define current map fixture model"
```

## Task 2：冻结 Agent 夹具、Prompt 和评分表

**Files:**

- Create: `fixtures/pilot-01/manifest.json`
- Create: `fixtures/pilot-01/records/**/*.md`
- Create: `fixtures/pilot-01/conditions/source-only/AGENTS.md`
- Create: `fixtures/pilot-01/conditions/flat-index/AGENTS.md`
- Create: `fixtures/pilot-01/conditions/state-projection/AGENTS.md`
- Create: `prompts/active-decision.md`
- Create: `prompts/superseded-rule.md`
- Create: `prompts/unresolved-conflict.md`
- Create: `prompts/scope-boundary.md`
- Create: `prompts/pending-observation.md`
- Create: `expected/answers.json`
- Create: `expected/rubric.json`
- Create: `test_validate_fixtures.py`
- Create: `validate_fixtures.py`

- [ ] **Step 1: 写 fixture 门禁失败测试**

测试必须逐项验证：

| 测试名 | 修改输入 | 必须出现的错误片段 |
| --- | --- | --- |
| `test_rejects_prompt_leaking_condition` | Prompt 写入 `state-projection` | `prompt leaks condition` |
| `test_rejects_flat_index_status_leak` | 普通索引写入 `superseded` | `flat index leaks status` |
| `test_rejects_projection_body_copy` | 投影复制一段原始正文 | `projection copies body` |
| `test_rejects_missing_expected_source` | 删除答案要求的来源 | `missing expected source` |
| `test_rejects_private_markers` | 记录加入绝对用户路径 | `sensitive marker` |
| `test_requires_five_tasks_and_three_conditions` | 删除一个任务 | `expected 5 tasks` |
| `test_requires_rubric_totals_to_match_answers` | rubric 总分加 1 | `rubric total mismatch` |

- [ ] **Step 2: 运行测试并确认 validator 尚不存在**

Run: `python3 -m unittest test_validate_fixtures.py -v`

Expected: 导入 `validate_fixtures` 失败。

- [ ] **Step 3: 编写合成记录和冻结任务**

五个任务分别使用独立主题，避免一条记录同时回答多个任务。每个任务至少包含一条干扰历史或观察记录；Prompt 只描述问题和要求的编号答案，不包含条件名、文件路径、状态标签或评分项。

`expected/rubric.json` 每个任务明确列出分值与语义条件，例如：

```json
{
  "unresolved-conflict": {
    "max_score": 5,
    "criteria": [
      {"id": "names-both-values", "points": 1},
      {"id": "keeps-conflict-open", "points": 1},
      {"id": "does-not-act", "points": 1},
      {"id": "proposes-controlled-check", "points": 1},
      {"id": "cites-used-sources", "points": 1}
    ]
  }
}
```

- [ ] **Step 4: 实现 fixture validator**

`validate(root, fixture_set="pilot-01") -> list[str]` 检查任务、条件、manifest、来源、Prompt、答案、rubric、敏感标记和派生文件契约。成功时只输出：

```text
fixture validation passed: conditions=3, tasks=5, records=10
```

- [ ] **Step 5: 运行测试和真实夹具验证**

Run:

```bash
python3 -m unittest test_validate_fixtures.py -v
python3 validate_fixtures.py
```

Expected: 全部通过。

- [ ] **Step 6: 提交冻结 Agent 协议**

```bash
git add experiments/practical-ai-memory/06-current-memory-map
git diff --cached --check
git commit -m "test(memory): freeze current map agent fixtures"
```

## Task 3：生成普通索引、状态投影和人工视图数据

**Files:**

- Create: `generate_views.py`
- Create: `test_generate_views.py`
- Create: `fixtures/pilot-01/generated/*`
- Create: `human-fixtures/pack-a.json`
- Create: `human-fixtures/pack-b.json`

- [ ] **Step 1: 写确定性生成与事实等价失败测试**

| 测试名 | 断言 |
| --- | --- |
| `test_generation_is_byte_stable` | 连续生成两次的四个文件 SHA256 完全一致 |
| `test_table_and_map_have_equal_fact_sets` | 两种视图的 `(id, status, scope, source)` 集合相等 |
| `test_flat_index_omits_status_and_relations` | 索引中不存在四个冻结状态值和 `supersedes` 字段 |
| `test_projection_omits_record_body` | 任一原始正文均不是投影 JSON 的子串 |
| `test_human_packs_have_equal_status_shapes` | 两包的状态计数、关系计数、问题数和满分相等 |

- [ ] **Step 2: 运行测试并确认生成器模块缺失**

Run: `python3 -m unittest test_generate_views.py -v`

Expected: 导入 `generate_views` 失败。

- [ ] **Step 3: 实现四类生成函数**

`generate_views.py` 固定暴露：

| 函数 | 返回契约 |
| --- | --- |
| `render_flat_index(manifest)` | 只含标题、相对路径、稳定摘要和更新时间的 Markdown |
| `build_state_projection(manifest)` | 只含状态、范围、关系、行动边界和来源指针的字典 |
| `build_state_table(pack)` | 人工表格条件的事实字典 |
| `build_visual_map(pack)` | 同一事实加展示字段的地图字典 |
| `generate_all(root, fixture_set="pilot-01")` | 原子写入四个规范化 LF 文件，无返回值 |

`state-table.json` 与 `visual-map.json` 必须保留相同 record ID、状态、关系、范围和来源；地图只增加 `group`、`tone` 和 `edge_direction` 等展示字段。

- [ ] **Step 4: 生成并验证已提交产物**

Run:

```bash
python3 generate_views.py
python3 validate_fixtures.py
python3 -m unittest test_generate_views.py -v
git diff --exit-code -- fixtures/pilot-01/generated
```

Expected: 生成器重复运行不产生差异。

- [ ] **Step 5: 提交生成器与派生产物**

```bash
git add experiments/practical-ai-memory/06-current-memory-map
git diff --cached --check
git commit -m "feat(memory): generate current map projections"
```

## Task 4：实现隔离 Agent 运行器和矩阵调度

**Files:**

- Create: `run_experiment.py`
- Create: `test_run_experiment.py`
- Create: `matrix_support.py`
- Create: `run_pilot_matrix.py`
- Create: `run_formal_matrix.py`
- Create: `test_pilot_matrix.py`
- Create: `test_formal_matrix.py`

- [ ] **Step 1: 复制并冻结前序运行器契约测试**

从第 5 个 POC 移植测试，保留以下具体断言：Windows launcher 解析、UTF-8 stdin、POSIX 相对路径排序、`features.plugins=false`、MCP workspace/non-workspace/unknown 分类、目录枚举、短筛选、运行时越界访问和可靠输出字节。

新增条件装配断言：

```python
self.assertNotIn("flat-index.md", source_only_files)
self.assertIn("flat-index.md", flat_index_files)
self.assertNotIn("state-projection.json", flat_index_files)
self.assertIn("state-projection.json", projection_files)
```

- [ ] **Step 2: 运行测试并确认运行器模块缺失**

Run: `python3 -m unittest test_run_experiment.py test_pilot_matrix.py test_formal_matrix.py -v`

Expected: 导入失败。

- [ ] **Step 3: 适配前序运行器**

正式命令保持：

```text
codex exec -C "$WORKSPACE" --sandbox read-only --ephemeral --json
--config features.plugins=false --output-last-message "$OUTPUT_FILE" -
```

metadata 必须记录模型、推理强度、Codex CLI、平台、Prompt/fixture 哈希、插件状态、运行时访问、MCP 分类、指标覆盖和输出可靠性，不得记录 provider。

macOS Pilot 还必须通过 `sandbox-exec` 将子进程执行面限制为 Codex 启动链、受控
shell 和 `cat`、`sed`、`nl`、`rg`。这个限制是运行器边界，不依赖 `AGENTS.md`
中的自然语言约定；拒绝事件按失败运行隔离，不能被恢复调度跳过。

- [ ] **Step 4: 实现矩阵调度和恢复门禁**

Pilot 覆盖 15 个唯一槽位；正式矩阵覆盖 45 个唯一槽位。条件顺序按任务与重复轮换。只有四个运行文件完整、答案非空、退出码为 0、隔离有效、指标覆盖完整且输出可靠的运行才能被恢复调度跳过。

- [ ] **Step 5: 运行测试、编译和 help 探测**

Run:

```bash
python3 -m unittest test_run_experiment.py test_pilot_matrix.py test_formal_matrix.py -v
python3 -m compileall -q .
python3 run_experiment.py --help
python3 run_pilot_matrix.py --help
python3 run_formal_matrix.py --help
```

Expected: 全部通过，help 不创建运行目录。

- [ ] **Step 6: 提交 Agent 执行链路**

```bash
git add experiments/practical-ai-memory/06-current-memory-map
git diff --cached --check
git commit -m "feat(memory): add current map agent runner"
```

## Task 5：实现评分、审计和聚合

**Files:**

- Create: `score_run.py`
- Create: `aggregate_results.py`
- Create: `test_score_run.py`
- Create: `test_aggregate_results.py`

- [ ] **Step 1: 写评分与聚合失败测试**

| 测试名 | 断言 |
| --- | --- |
| `test_requires_real_review_minutes` | 缺少正数 Review 分钟时拒绝写分 |
| `test_rejects_score_above_task_max` | 任一 rubric 得分超过上限时退出非零 |
| `test_preserves_protocol_and_claim_counts` | 三个审计字段逐值写入 `score.json` |
| `test_creates_fifteen_groups_of_three` | 45 份运行聚合成 15 组且每组 `n=3` |
| `test_requires_workspace_metrics_n` | 覆盖不完整运行不进入 workspace 样本数 |
| `test_does_not_mix_model_or_effort` | 模型或推理强度不一致时聚合失败 |

- [ ] **Step 2: 运行测试并确认模块缺失**

Run: `python3 -m unittest test_score_run.py test_aggregate_results.py -v`

Expected: 导入失败。

- [ ] **Step 3: 实现评分和聚合工具**

评分文件保存逐项 rubric、`protocol_valid`、`unsupported_claims`、`irrelevant_facts`、真实 Review 分钟数和批次大小。CSV 固定 LF；JSON 聚合记录平台、模型、推理强度、CLI、`n`、`workspace_metrics_n` 和正确性。

- [ ] **Step 4: 运行测试**

Run: `python3 -m unittest test_score_run.py test_aggregate_results.py -v`

Expected: 全部通过。

- [ ] **Step 5: 提交评分链路**

```bash
git add experiments/practical-ai-memory/06-current-memory-map
git diff --cached --check
git commit -m "feat(memory): score current map agent runs"
```

## Task 6：实现人工实验页面和私有结果服务

**Files:**

- Create: `human_experiment.py`
- Create: `test_human_experiment.py`
- Create: `human/index.html`
- Create: `human/app.js`
- Create: `human/styles.css`

- [ ] **Step 1: 写服务与结果门禁失败测试**

| 测试名 | 断言 |
| --- | --- |
| `test_accepts_complete_synthetic_result` | 两条件、10 题、完整计时结果通过 |
| `test_rejects_missing_timer_or_answers` | 缺少 `elapsed_ms` 或答案时拒绝 |
| `test_rejects_absolute_paths_and_identity_fields` | 绝对路径、姓名、邮箱或 provider 均拒绝 |
| `test_rejects_duplicate_condition` | 两次相同 condition 拒绝 |
| `test_summary_contains_only_aggregate_fields` | 摘要不含 session ID、逐题事件或路径 |

- [ ] **Step 2: 运行测试并确认服务模块缺失**

Run: `python3 -m unittest test_human_experiment.py -v`

Expected: 导入 `human_experiment` 失败。

- [ ] **Step 3: 实现本地服务 API**

固定 API：

```text
GET  /                       -> human/index.html
GET  /api/session            -> 随机条件顺序和两套脱敏场景
POST /api/complete                  -> 校验并写入以随机 session ID 命名的私有 JSON
GET  /api/summary/:session_id       -> 只返回条件级聚合
```

服务只绑定 `127.0.0.1`。`validate_submission(payload)` 拒绝姓名、邮箱、用户名、绝对路径、thread ID、provider 和不完整事件。

- [ ] **Step 4: 实现固定格式实验界面**

界面包含：状态区、单题答题区、来源详情按钮、进度、条件结束后的信心选择和最终完成页。表格与地图共享同一答案控件和详情能力；地图状态同时使用颜色与文本标签。

前端提交结构固定为：

```json
{
  "session_id": "local-random-id",
  "condition_order": ["state-table", "visual-map"],
  "conditions": [
    {
      "condition": "state-table",
      "pack_id": "pack-a",
      "elapsed_ms": 120000,
      "correct": 5,
      "total": 5,
      "detail_opens": 2,
      "answer_changes": 1,
      "confidence": 4
    }
  ]
}
```

- [ ] **Step 5: 运行单元测试和静态语法检查**

Run:

```bash
python3 -m unittest test_human_experiment.py -v
python3 -m py_compile human_experiment.py
node --check human/app.js
```

Expected: 全部通过。

- [ ] **Step 6: 提交人工实验应用**

```bash
git add experiments/practical-ai-memory/06-current-memory-map
git diff --cached --check
git commit -m "feat(memory): add current map human trial"
```

## Task 7：完成浏览器验收和隐私审计

**Files:**

- Create: `analysis/ui-validation.md`
- Modify when defects are found: `human/index.html`
- Modify when defects are found: `human/app.js`
- Modify when defects are found: `human/styles.css`

- [ ] **Step 1: 启动本地人工实验服务**

Run: `python3 human_experiment.py --port 8765`

Expected: 输出 `human experiment listening on http://127.0.0.1:8765`，且不自动开始计时。

- [ ] **Step 2: 使用 Playwright 检查桌面与移动视口**

检查 `1440×900` 与 `390×844`：页面非空、文字和按钮不重叠、最长状态文本不溢出、详情可展开、问题切换不引发布局跳动、状态不只依赖颜色。

- [ ] **Step 3: 使用专用合成测试会话验证事件链路**

完成一轮标记为 `browser-smoke` 的测试提交，确认计时、答案修改、详情展开和汇总字段正确。测试结果必须写入隔离目录并在验证后移出正式人工结果目录。

- [ ] **Step 4: 记录验收证据**

`analysis/ui-validation.md` 记录视口、操作、结果和缺陷修复，不记录本机绝对路径或浏览器身份。截图仅在不含私有路径和会话 ID 时进入公开证据候选。

- [ ] **Step 5: 运行隐私与格式门禁**

Run:

```bash
python3 validate_fixtures.py
python3 -m unittest discover -p 'test_*.py'
npm run lint:md -- experiments/practical-ai-memory/06-current-memory-map/*.md experiments/practical-ai-memory/06-current-memory-map/analysis/*.md
git diff --check
```

Expected: 全部通过。

- [ ] **Step 6: 提交页面验收记录**

```bash
git add experiments/practical-ai-memory/06-current-memory-map
git diff --cached --check
git commit -m "test(memory): verify current map human trial"
```

## Task 8：执行 macOS Agent Pilot 并停在 Review checkpoint

**Files:**

- Create after successful Review: `analysis/pilot-01.md`
- Private only: `runs/private/macos/pilot-*`

- [ ] **Step 1: 执行全部静态门禁**

Run:

```bash
python3 generate_views.py
git diff --exit-code -- fixtures/pilot-01/generated
python3 validate_fixtures.py
python3 -m unittest discover -p 'test_*.py'
python3 -m compileall -q .
python3 run_experiment.py --help
python3 run_pilot_matrix.py --help
python3 run_formal_matrix.py --help
```

Expected: 全部通过，help 不创建运行目录。

- [ ] **Step 2: 记录冻结环境并运行 15 次 Pilot**

Run:

```bash
python3 run_pilot_matrix.py \
  --platform-tag macos \
  --model gpt-5.6-sol \
  --reasoning-effort medium
```

Expected: `completed=15, skipped=0, failed=0`。任一槽位失败立即停止。

- [ ] **Step 3: 执行运行层审计**

逐份确认四类运行文件、退出码、模型、推理强度、CLI、Prompt/fixture 哈希、插件关闭、运行时越界为 0、MCP unknown 为 0、指标覆盖完整且输出可靠。

- [ ] **Step 4: 执行只读语义 Review**

依据冻结 rubric 提出 15 份评分建议，不创建 `score.json`。确认普通索引没有状态泄漏，三个条件存在可解释差异，并检查所有回答是否完整回答编号问题。

- [ ] **Step 5: 写 Pilot 报告并暂停**

只有 Pilot 通过才在 `analysis/pilot-01.md` 记录正式矩阵冻结候选。Pilot 失败则记录隔离位置、失败门禁和修订范围，不启动正式矩阵。

- [ ] **Step 6: 提交 Pilot 报告**

```bash
git add experiments/practical-ai-memory/06-current-memory-map/analysis/pilot-01.md
git diff --cached --check
git commit -m "docs(memory): report current map pilot"
```

## Task 9：执行人工探索性实验并形成 checkpoint

**Files:**

- Create: `analysis/human-trial.md`
- Private only: `human-results/private/*.json`

- [ ] **Step 1: 确认正式场景未被参与者预览**

检查浏览器 Smoke 使用专用测试包，`pack-a` 与 `pack-b` 的正式答案未出现在公开验收页面或截图中。若已泄露，重新生成等价场景包并重新跑事实等价门禁。

- [ ] **Step 2: 启动正式本地服务**

Run: `python3 human_experiment.py --port 8765 --mode formal`

Expected: 服务生成新的随机 session，不输出答案或参与者身份。

- [ ] **Step 3: Lee 完成一次 5 至 8 分钟实验**

不中途查看结果，不切换到夹具文件。完成两种条件后，服务生成一份私有逐题记录和一份条件级脱敏汇总。

- [ ] **Step 4: 校验人工结果完整性**

Run:

```bash
RESULT_FILE="$(find human-results/private -type f -name '*.json' -print | sort | tail -1)"
python3 human_experiment.py --validate-result "$RESULT_FILE"
```

Expected: `human result valid: conditions=2, questions=10`。校验命令使用实际生成的本地文件名，不把该文件名写入公开文档。

- [ ] **Step 5: 写探索性结果报告并暂停**

`analysis/human-trial.md` 只记录两种条件的正确率、总耗时、详情展开、答案修改和主观信心，明确 `n=1`、无显著性检验、不能推广到人群。此时不启动 45 次正式矩阵，等待 Lee Review Agent Pilot 与人工结果。

- [ ] **Step 6: 提交脱敏人工报告**

```bash
git add experiments/practical-ai-memory/06-current-memory-map/analysis/human-trial.md
git diff --cached --check
git commit -m "docs(memory): report current map human trial"
```

## 执行完成门槛

本计划的首个实施 checkpoint 是：

- 夹具、四类派生产物和事实等价门禁通过。
- Agent 运行、评分和聚合链路测试通过。
- 人工页面完成桌面与移动验收。
- 15 次 macOS Agent Pilot 完成只读 Review。
- 一次人工探索性实验完成并生成脱敏报告。
- 45 次 macOS 正式矩阵尚未自动启动，等待 Lee 根据 Pilot 证据确认。

该 checkpoint 之后，正式矩阵、评分、聚合、Win11 Level 2 Smoke、公开证据和第六篇文章分别作为后续受控阶段推进。
