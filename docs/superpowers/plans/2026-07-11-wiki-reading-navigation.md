# Wiki Continuous Reading Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate fixed previous, directory, and next navigation at the bottom of every GitHub and Gitee Wiki article.

**Architecture:** `write_wiki` remains the full-rebuild coordinator. It derives neighboring articles from the complete ordered ready-article list and passes navigation data into `render_article`, which renders a portable Markdown table using the current platform's Wiki base URL.

**Tech Stack:** Python 3 standard library, `unittest`, Markdown, GitHub Actions.

---

### Task 1: Define Navigation Behavior With Tests

**Files:**
- Modify: `tests/test_sync_wiki.py`

- [x] Add a test that renders a middle article and expects links for previous article, `Home`, and next article.
- [x] Add boundary assertions that missing previous or next articles render `无` beneath the corresponding table header.
- [x] Add a full-rebuild test using a temporary Wiki directory, then append a new article and verify the former last article receives a next link.
- [x] Run `python3 -m unittest tests.test_sync_wiki -v` and confirm the new tests fail because navigation arguments and output do not exist yet.

### Task 2: Implement Full-Rebuild Navigation

**Files:**
- Modify: `scripts/sync_wiki.py`
- Modify: `docs/publishing-workflow.md`

- [x] Add a small navigation renderer that uses `wiki_page_url` for previous, `Home`, and next destinations.
- [x] Extend `render_article` with previous page, next page, and Wiki base URL inputs; place navigation after the article body and before source metadata.
- [x] Update `write_wiki` to derive neighbors from the complete ordered list on every run and pass them to `render_article`.
- [x] Document that adding a new ready article regenerates existing pages whose neighboring links change.
- [x] Run `python3 -m unittest tests.test_sync_wiki tests.test_sync_mowen -v`, `python3 -m py_compile scripts/sync_wiki.py`, `python3 scripts/sync_wiki.py --dry-run`, and `git diff --check`.
- [x] Generate temporary GitHub and Gitee Wiki outputs and inspect the first, middle, and last article navigation URLs.
