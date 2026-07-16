# Multi-Series Publishing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add series-aware README, Wiki, and MoWen publishing without changing the existing 15 article URLs, ordering, or first-series directory identity.

**Architecture:** A standard-library `series_catalog` module loads `content/series.json` and supplies validated metadata to all three publishers. Articles keep a stable global Wiki sequence while receiving a separate series-local sequence for navigation and MoWen titles. The MoWen mapping loader migrates legacy `directory` data into version 2 `directories` in memory before any write.

**Tech Stack:** Python 3.12, JSON, PyYAML 6.0.2, `unittest`, Markdown, GitHub Actions

---

## Task 1: Series Catalog And README Grouping

**Files:**

- Create: `content/series.json`
- Create: `scripts/series_catalog.py`
- Create: `tests/test_update_readme_index.py`
- Modify: `scripts/update_readme_index.py`
- Modify: `README.md`
- Modify: `README-EN.md`

- [x] **Step 1: Write failing tests for series validation, global Wiki page stability, series-local numbering, and bilingual grouping.**

The tests create two series and three ready articles, then assert that global Wiki pages remain `01`, `02`, `03` while local sequence resets to `01` in the second series.

- [x] **Step 2: Run the README tests and confirm imports or grouping assertions fail.**

Run: `python -m unittest tests.test_update_readme_index -v`

Expected: failure because `series_catalog` and grouped rendering do not exist.

- [x] **Step 3: Add the JSON catalog and shared loader.**

The loader validates `version`, unique IDs, unique positive order values, titles, Wiki pages, and known lifecycle states. It returns series sorted by `order` and raises `ValueError` for unknown article series.

- [x] **Step 4: Generate README sections by series.**

`article_rows()` keeps global Wiki page numbering and adds `series_id` plus `series_sequence`. Rendering writes one heading and MoWen directory link per series with ready articles.

- [x] **Step 5: Run README tests and regenerate both README files.**

Run: `python -m unittest tests.test_update_readme_index -v && python scripts/update_readme_index.py`

Expected: tests pass and the generated index reports 15 published articles in one completed series.

## Task 2: Series-Aware Wiki Navigation

**Files:**

- Modify: `scripts/sync_wiki.py`
- Modify: `scripts/verify_wiki.py`
- Modify: `tests/test_sync_wiki.py`
- Modify: `tests/test_verify_wiki.py`

- [x] **Step 1: Write failing tests for stable legacy pages, series landing pages, grouped Sidebar, and series-bounded navigation.**

The compatibility test records the current first-series page names and asserts they do not change. A two-series test asserts the last article in series one and first article in series two both have no cross-series neighbor.

- [x] **Step 2: Run Wiki tests and confirm the new expectations fail.**

Run: `python -m unittest tests.test_sync_wiki tests.test_verify_wiki -v`

Expected: failure because Wiki generation is still a single flat sequence.

- [x] **Step 3: Attach series metadata while preserving global pages.**

`ready_articles()` assigns global `page` values exactly as before and adds series-local sequence, title, and directory-page fields from `content/series.json`.

- [x] **Step 4: Generate grouped Home, series pages, nested Sidebar, and bounded article navigation.**

Each series page lists only that series. Article navigation receives the series directory page and calculates previous/next from the same group.

- [x] **Step 5: Update pre/post-publish validation and run Wiki tests.**

Run: `python -m unittest tests.test_sync_wiki tests.test_verify_wiki -v`

Expected: all tests pass, including page inventory and navigation validation.

## Task 3: MoWen Multi-Directory Compatibility

**Files:**

- Modify: `scripts/sync_mowen.py`
- Modify: `publishing/mowen-notes.json`
- Modify: `tests/test_sync_mowen.py`

- [x] **Step 1: Write failing tests for per-series numbering, separate directory documents, and legacy mapping migration.**

Tests assert that two series each start at sequence `1`, directory documents embed only their own notes, and an existing version 1 `directory` becomes `directories.long-term-ai-work-system` without losing fields.

- [x] **Step 2: Run MoWen tests and confirm the new expectations fail.**

Run: `python -m unittest tests.test_sync_mowen -v`

Expected: failures because numbering and directory state are global.

- [x] **Step 3: Add series-local sequences and mapping migration.**

`Article` gains `series`; discovery preserves newest-first processing while assigning sequence inside each series. Mapping load/save uses version 2 and a helper that resolves the selected series directory.

- [x] **Step 4: Build and synchronize one directory per series.**

Main groups articles by series, keeps missing articles first, updates affected directories, processes existing article changes, then performs an idempotent final directory pass.

- [x] **Step 5: Migrate the checked-in mapping and run MoWen tests.**

Run: `python -m unittest tests.test_sync_mowen -v`

Expected: all tests pass and the first-series note ID, URL, cover UUID, hashes, and publication state remain unchanged.

## Task 4: Workflow And Documentation Regression

**Files:**

- Modify: `.github/workflows/sync-wiki.yml`
- Modify: `.github/workflows/sync-mowen.yml`
- Modify: `docs/publishing-workflow.md`
- Modify: `docs/publishing-runbook.md`

- [x] **Step 1: Add new catalog and shared module paths to workflow change detection.**

Wiki and MoWen workflows must run when `content/series.json` or `scripts/series_catalog.py` changes.

- [x] **Step 2: Document global Wiki numbering, series-local navigation, and MoWen directory registration.**

The runbook must state that Lee registers the new series directory note ID before the first article is published.

- [x] **Step 3: Run the complete regression suite.**

Run: `python -m unittest tests.test_update_readme_index tests.test_sync_wiki tests.test_verify_wiki tests.test_sync_mowen -v`

Expected: all tests pass.

- [x] **Step 4: Run real first-series generation checks.**

Run:

```bash
python scripts/update_readme_index.py
python scripts/verify_wiki.py --phase pre --site-name "GitHub Wiki" --wiki-base-url "https://github.com/ExDevilLee/ai-work-system/wiki" --asset-base-url "https://raw.githubusercontent.com/ExDevilLee/ai-work-system/main"
python scripts/verify_wiki.py --phase pre --site-name "Gitee Wiki" --wiki-base-url "https://gitee.com/ExDevilLee/ai-work-system/wikis" --asset-base-url "https://gitee.com/ExDevilLee/ai-work-system/raw/main"
python scripts/sync_mowen.py
```

Expected: 15 ready articles, unchanged legacy Wiki page names, both Wiki checks pass, and MoWen dry-run conversion succeeds without API calls.

- [x] **Step 5: Run Markdown and Git integrity checks.**

Run: `git diff --check` plus the repository Markdown checker on the modified Markdown files.

Expected: no new formatting errors; known intentional `MORE` and numbered-roadmap baselines remain unchanged.
