# Wiki Publication Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add repeatable pre-publish and post-publish checks for GitHub Wiki and Gitee Wiki article pages and images.

**Architecture:** A shared `scripts/verify_wiki.py` validates source articles, generates expected Wiki files through `scripts/sync_wiki.py`, and compares a fresh remote Wiki clone plus remote image hashes after publishing. Both existing Wiki workflows call the same CLI with platform-specific URLs and credentials.

**Tech Stack:** Python 3.12, PyYAML 6.0.2, standard-library `unittest`, Git, GitHub Actions.

---

### Task 1: Standardize Article Metadata Parsing

**Files:**
- Create: `requirements-wiki.txt`
- Modify: `scripts/sync_wiki.py`
- Modify: `tests/test_sync_wiki.py`

- [x] Add failing tests for valid YAML frontmatter containing quoted punctuation and invalid YAML.
- [x] Run `python -m unittest tests.test_sync_wiki -v` and confirm the new tests fail under the simplified parser.
- [x] Replace simplified frontmatter parsing with `yaml.safe_load`, preserving the existing ready-article output contract.
- [x] Pin `PyYAML==6.0.2` in `requirements-wiki.txt` and rerun the tests.

### Task 2: Implement Pre-Publish Verification

**Files:**
- Create: `scripts/verify_wiki.py`
- Create: `tests/test_verify_wiki.py`

- [x] Add failing tests for missing images, invalid `images/<two-digit-number>/...` paths, extension/signature mismatch, and valid generated navigation.
- [x] Run `python -m unittest tests.test_verify_wiki -v` and confirm failures are caused by the missing verifier.
- [x] Implement ready-source image discovery, file-signature checks, temporary full Wiki generation, page inventory checks, navigation checks, and platform asset URL checks.
- [x] Run `python -m unittest tests.test_verify_wiki -v` and confirm all pre-publish tests pass.

### Task 3: Implement Post-Publish Verification

**Files:**
- Modify: `scripts/verify_wiki.py`
- Modify: `tests/test_verify_wiki.py`

- [x] Add failing tests for stale remote Markdown, stale remote image bytes, and retry followed by success.
- [x] Implement fresh remote Wiki cloning, expected-versus-remote Markdown comparison, HTTP image download, SHA-256 comparison, and bounded retries.
- [x] Run `python -m unittest tests.test_verify_wiki -v` and confirm all post-publish tests pass.

### Task 4: Integrate Both Wiki Workflows

**Files:**
- Modify: `.github/workflows/sync-wiki.yml`
- Modify: `.github/workflows/sync-to-gitee.yml`
- Modify: `.github/workflows/sync-mowen.yml`
- Modify: `docs/publishing-workflow.md`

- [x] Install `requirements-wiki.txt` in both Wiki workflows.
- [x] Run the platform-specific pre-publish command before `sync_wiki.py --push` and the post-publish command afterward.
- [x] Add verifier files and dependency changes to trigger filters; keep them outside MoWen's publishing allowlist so verification-only pushes do not consume quota.
- [x] Document automated guarantees, retries, failure output, and the remaining visual-review boundary.

### Task 5: Verify and Publish

**Files:**
- Modify: this plan checklist

- [x] Run `python -m unittest tests.test_sync_wiki tests.test_verify_wiki tests.test_sync_mowen -v`.
- [x] Run `python -m py_compile scripts/sync_wiki.py scripts/verify_wiki.py`.
- [x] Run local GitHub and Gitee pre-publish verification commands.
- [x] Run workflow YAML syntax checks and `git diff --check`.
- [ ] Commit and push, then confirm both Wiki workflows pass and MoWen skips publishing.
