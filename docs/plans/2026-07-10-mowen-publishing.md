# 墨问发布链路实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将所有 `status: ready` 的文章幂等发布到墨问，并维护一篇按时间倒序内嵌全部文章的《AI 长期工作系统》目录笔记。

**Architecture:** 主仓库文章仍是唯一内容源。Python 脚本负责读取文章元信息、调用固定版本的 Markdown 转换器、通过墨问官方 MCP 创建或编辑笔记，并使用仓库内映射文件保存墨问笔记 ID；目录由脚本每次全量重建，因此新文章发布后会自动出现在最上方。

**Tech Stack:** Python 3 标准库、`PyYAML`、`md-to-mowen@1.9.1`、墨问官方 MCP、GitHub Actions。

---

## 文件职责

- `scripts/sync_mowen.py`：文章发现、转换、MCP 调用、映射维护、目录重建和命令行入口。
- `tests/test_sync_mowen.py`：元信息解析、倒序排序、目录 NoteAtom、映射和 dry-run 行为测试。
- `publishing/mowen-notes.json`：文章源路径到墨问笔记 ID 的持久映射，以及目录笔记 ID。
- `assets/mowen/ai-work-system-cover.png`：目录封面源文件。
- `.github/workflows/sync-mowen.yml`：在 `main` 的相关文章或发布代码变化后同步墨问。
- `requirements-mowen.txt`、`package.json`、`package-lock.json`：固定发布链路依赖版本。
- `docs/publishing-workflow.md`、`docs/publishing-runbook.md`：更新发布约定与操作说明。

## Task 1：纯数据转换

- [ ] 先写失败测试，覆盖只选择 `ready` 文章、按日期和源文件名稳定倒序排列。
- [ ] 运行 `python3 -m unittest tests.test_sync_mowen -v`，确认因实现缺失而失败。
- [ ] 实现文章发现和标准 YAML frontmatter 解析。
- [ ] 再次运行测试并确认通过。
- [ ] 先写失败测试，覆盖目录标题、README 风格简介和倒序 `note` 引用块。
- [ ] 实现目录 NoteAtom 生成器并确认测试通过。

## Task 2：MCP 客户端与幂等映射

- [ ] 先写失败测试，使用本地假 MCP 客户端验证：有映射时编辑、无映射时私密创建、创建后立即写回映射。
- [ ] 实现无状态 MCP JSON-RPC 客户端，密钥只从 `MOWEN_MCP_URL` 或 `MOWEN_API_KEY` 读取。
- [ ] 实现原子映射写入，避免部分 JSON 覆盖原文件。
- [ ] 实现 `--dry-run`，保证不调用远端、不修改映射。
- [ ] 运行全部单元测试。

## Task 3：Markdown 转换与封面

- [ ] 固定 `md-to-mowen@1.9.1`，先去除 frontmatter，再生成 NoteAtom。
- [ ] 校验生成正文不包含 YAML 元信息，并保留标题、段落、链接、列表、引用和代码块。
- [ ] 准备无文字的编辑型封面并保存到 `assets/mowen/`。
- [ ] 通过墨问 `UploadViaURL` 从 Gitee 同步镜像上传封面；上传前核对远端内容哈希，目录正文首部插入返回的图片 UUID。

## Task 4：私密验证与公开发布

- [ ] 使用 `--create-private` 为尚未映射的 5 篇文章创建私密笔记，第一篇沿用已验证 ID。
- [ ] 使用 `mocli note mine --filter priv` 核对标题、数量、字数和状态。
- [ ] 创建或更新私密目录，核对 `with_ref: true`，且 6 篇文章按最新到最旧排列。
- [ ] 将 6 篇文章设置为公开，再将目录设置为公开。
- [ ] 用 `mocli` 和公开页面逐一验证 URL、标题、正文与目录跳转。

## Task 5：CI 与文档

- [ ] 新增 GitHub Actions，校验 `MOWEN_API_KEY`，安装固定依赖并运行测试。
- [ ] 同步脚本先私密创建并保存映射，再更新和公开笔记，最后重建目录。
- [ ] workflow 将映射变化提交回 `main`；由 `GITHUB_TOKEN` 产生的提交不再次触发 workflow。
- [ ] 更新发布工作流和 Runbook，说明墨问目录、失败恢复和 Secret 配置步骤。
- [ ] 运行 `python3 -m unittest discover -s tests -v`、Wiki dry-run、YAML 解析和 `git diff --check`。

## 安全与失败边界

- MCP URL 和 API Key 不写入仓库、不打印到日志。
- 所有新笔记先以私密状态创建；只有正文、映射和目录验证通过后才改为公开。
- 同一时间只允许一个墨问同步 workflow 运行。
- 若创建后、映射提交前任务中断，最多遗留一篇私密重复笔记，不会自动产生公开重复内容；恢复时先通过 `mocli` 核对并补回映射。
- 第三方转换依赖固定精确版本并提交 lockfile；CI 不运行不受控的 latest 版本。

## 验收标准

- 6 篇 `ready` 文章都有稳定墨问 URL，重跑只编辑原笔记。
- 《AI 长期工作系统》包含项目简介、封面和 6 个原生笔记卡片。
- 目录文章按时间倒序排列；同日文章使用源文件名形成稳定顺序。
- 新增 `ready` 文章后，CI 自动发布文章并把它插入目录最上方。
- GitHub 仓库、Actions 日志和提交历史中不出现墨问密钥。
