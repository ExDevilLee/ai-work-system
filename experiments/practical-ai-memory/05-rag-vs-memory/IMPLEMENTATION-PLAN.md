# RAG 与长期记忆行动治理 POC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立可复现的第 5 个 POC，用相同冻结检索结果比较 `rag-only`、`rag-with-recency` 和 `memory-governed` 的行动治理差异，并完成 macOS Pilot。

**Architecture:** 共享语料与任务级冻结 Top-K 检索包作为三组共同证据，条件目录只提供治理规则；`memory-governed` 额外提供不复制正文的当前状态投影。运行器沿用前序 POC 的临时工作区、UTF-8 stdin、插件关闭、私有证据和工作区指标审计契约。

**Tech Stack:** Python 3 标准库、SQLite FTS5 `bm25()`、Codex CLI、`unittest`、Markdown/JSON 夹具。

---

## 执行任务

### Task 1: 冻结夹具与检索包验证

**Files:**

- Create: `fixtures/pilot-01/corpus/**/*.md`
- Create: `fixtures/pilot-01/retrieval-packets/*.md`
- Create: `fixtures/pilot-01/retrieval-packets/manifest.json`
- Create: `fixtures/pilot-01/conditions/*/AGENTS.md`
- Create: `fixtures/pilot-01/conditions/memory-governed/memory/CURRENT.md`
- Create: `prompts/*.md`
- Create: `expected/answers.json`
- Create: `expected/rubric.json`
- Create: `test_validate_fixtures.py`
- Create: `validate_fixtures.py`

- [ ] **Step 1: 先写 validator 失败测试**

测试必须覆盖：缺失任务、manifest SHA256 错误、检索包复制了非 corpus 正文、Prompt 泄漏条件、条件目录复制证据、隐私标记、`CURRENT.md` 复制原文、rubric 总分不等于 28。

- [ ] **Step 2: 运行测试并确认因模块缺失而失败**

Run: `python3 -m unittest test_validate_fixtures.py -v`

Expected: `ModuleNotFoundError: No module named 'validate_fixtures'`。

- [ ] **Step 3: 创建最小夹具与 validator**

`validate()` 返回错误字符串列表；`main()` 只在错误为空时打印：

```text
fixture validation passed: conditions=3, tasks=5, packets=5
```

- [ ] **Step 4: 运行 validator 测试与真实夹具验证**

Run: `python3 -m unittest test_validate_fixtures.py -v && python3 validate_fixtures.py`

Expected: 全部通过。

### Task 2: SQLite FTS5/BM25 召回核验

**Files:**

- Create: `test_validate_retrieval.py`
- Create: `validate_retrieval.py`
- Modify: `fixtures/pilot-01/retrieval-packets/manifest.json`

- [ ] **Step 1: 先写召回失败测试**

测试建立临时 corpus 与 manifest，要求必要来源未进入 Top-K 时返回明确错误，并验证 FTS5 不可用时 fail closed。

- [ ] **Step 2: 运行测试并确认模块缺失失败**

Run: `python3 -m unittest test_validate_retrieval.py -v`

Expected: `ModuleNotFoundError: No module named 'validate_retrieval'`。

- [ ] **Step 3: 实现 FTS5 检索审计**

使用内存数据库：

```sql
CREATE VIRTUAL TABLE corpus USING fts5(path UNINDEXED, body);
SELECT path, bm25(corpus) AS score FROM corpus
WHERE corpus MATCH ? ORDER BY score, path LIMIT ?;
```

manifest 为每个任务冻结 `query`、`top_k` 与 `required_sources`。核验只输出相对路径，不写数据库文件。

- [ ] **Step 4: 运行单元测试和真实召回核验**

Run: `python3 -m unittest test_validate_retrieval.py -v && python3 validate_retrieval.py`

Expected: `retrieval validation passed: tasks=5`。

### Task 3: 隔离运行器与指标审计

**Files:**

- Create: `test_run_experiment.py`
- Create: `run_experiment.py`
- Create: `.gitignore`
- Create: `.gitattributes`
- Modify: repository root `.gitattributes`

- [ ] **Step 1: 先写运行器契约测试**

覆盖条件白名单、Windows launcher 解析、UTF-8 stdin、插件关闭、POSIX 相对路径树哈希、MCP workspace/non-workspace/unknown 分类、目录枚举与短筛选、隐私运行时访问计数、共享夹具和条件层合并。

- [ ] **Step 2: 运行测试并确认模块缺失失败**

Run: `python3 -m unittest test_run_experiment.py -v`

Expected: `ModuleNotFoundError: No module named 'run_experiment'`。

- [ ] **Step 3: 适配前序已验证运行器**

正式调用必须包含：

```text
codex exec -C <workspace> --sandbox read-only --ephemeral --json
--config features.plugins=false --output-last-message <file> -
```

metadata 记录模型、推理强度、CLI、平台、夹具与 Prompt 哈希、指标覆盖和隔离结果，不记录 provider。

- [ ] **Step 4: 运行测试、语法检查和 help 探测**

Run: `python3 -m unittest test_run_experiment.py -v && python3 -m compileall -q . && python3 run_experiment.py --help`

Expected: 测试通过，help 退出码为 0，且不创建运行目录。

### Task 4: Pilot 与正式矩阵调度

**Files:**

- Create: `matrix_support.py`
- Create: `test_pilot_matrix.py`
- Create: `run_pilot_matrix.py`
- Create: `test_formal_matrix.py`
- Create: `run_formal_matrix.py`

- [ ] **Step 1: 先写调度失败测试**

验证 Pilot 恰好覆盖 15 个唯一槽位、正式矩阵覆盖 45 个唯一槽位、条件顺序轮换、完整成功运行可跳过、不完整目录立即停止。

- [ ] **Step 2: 运行测试并确认模块缺失失败**

Run: `python3 -m unittest test_pilot_matrix.py test_formal_matrix.py -v`

Expected: 导入失败。

- [ ] **Step 3: 实现最小调度器和恢复门禁**

Pilot 标签必须以 `pilot-` 开头。正式调度固定 3 次重复；只有包含全部运行文件、非空答案、成功 metadata、用量、隔离和可靠指标的目录才能跳过。

- [ ] **Step 4: 运行调度测试与 help 探测**

Run: `python3 -m unittest test_pilot_matrix.py test_formal_matrix.py -v && python3 run_pilot_matrix.py --help && python3 run_formal_matrix.py --help`

Expected: 测试通过，help 不创建运行目录。

### Task 5: 评分与聚合

**Files:**

- Create: `test_score_run.py`
- Create: `score_run.py`
- Create: `test_aggregate_results.py`
- Create: `aggregate_results.py`

- [ ] **Step 1: 先写评分与聚合失败测试**

验证正式评分必须提供真实 Review 时间、批量均摊必须记录批次大小、分数不可越界、聚合不得混合模型配置、每组输出 `n` 与 `workspace_metrics_n`。

- [ ] **Step 2: 运行测试并确认模块缺失失败**

Run: `python3 -m unittest test_score_run.py test_aggregate_results.py -v`

Expected: 导入失败。

- [ ] **Step 3: 实现评分与聚合工具**

输出字段沿用前序 POC，CSV 固定使用 LF；JSON 记录平台、模型、推理强度、CLI、分组正确性和可靠过程指标。

- [ ] **Step 4: 运行测试**

Run: `python3 -m unittest test_score_run.py test_aggregate_results.py -v`

Expected: 全部通过。

### Task 6: 静态门禁与 Pilot

**Files:**

- Modify: `README.md`
- Modify: `EXPERIMENT.md`
- Create after successful Review: `analysis/pilot-01.md`

- [ ] **Step 1: 运行全量静态门禁**

Run:

```bash
python3 validate_fixtures.py
python3 validate_retrieval.py
python3 -m unittest discover -p 'test_*.py'
python3 -m compileall -q .
```

Expected: 全部通过，且没有标准 Pilot 运行目录。

- [ ] **Step 2: 运行 15 次 macOS Pilot**

Run:

```bash
python3 run_pilot_matrix.py \
  --platform-tag macos \
  --model gpt-5.6-sol \
  --reasoning-effort medium
```

Expected: `completed=15, skipped=0`。任一槽位失败立即停止。

- [ ] **Step 3: 执行运行层门禁**

逐份检查完整文件、退出码、模型配置、Prompt/fixture 哈希、插件关闭、运行时越界、指标覆盖和输出可靠性。失败批次整体隔离，不复用部分结果。

- [ ] **Step 4: 执行只读语义 Review**

依据冻结 rubric Review 15 份答案，只提出评分建议，不创建 `score.json`。确认静态事实任务不偏向任何条件，并判断三组行为是否可区分。

- [ ] **Step 5: 更新 Pilot 报告并停在 checkpoint**

只有 Pilot 通过才在 `analysis/pilot-01.md` 记录冻结决定；否则记录修订原因并保持正式矩阵未启动。
