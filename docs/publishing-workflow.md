# 发布工作流约定

本文记录本仓库的内容源头和展示层同步约定。

## 基本原则

主仓库 Markdown 是唯一内容源头。

```text
content/articles/*.md
  -> GitHub Wiki
  -> Gitee Wiki
  -> 墨问《AI 长期工作系统》
  -> 未来个人网站
  -> 未来微信公众号 / 知乎 / 其他平台
```

所有展示层只负责展示，不反向修改源文。

如果在 Wiki、个人网站或其他平台发现需要改文章，应该回到主仓库修改 `content/articles/*.md`，再重新同步。

文章正文默认以中文为主。`README-EN.md` 提供英文项目入口和文章导航，文章可以维护 `title_en`、`summary_en` 等英文元信息；完整英文译文按需维护，不作为每篇文章的默认发布要求。

## 内容状态

文章通过 frontmatter 的 `status` 字段表示当前阶段：

- `draft`：草稿阶段，不同步到展示层。
- `review`：发布前审阅阶段，不默认同步到展示层。
- `ready`：发布源稿阶段，可以同步到展示层；推送到 `main` 后会由 CI 发布或刷新到 Wiki。

当前只同步 `status: ready` 的文章到 GitHub Wiki、Gitee Wiki 和墨问。

`status` 描述的是主仓库源稿是否可以进入自动发布链路，不直接等同于 README 里的展示分类：

- README 的 `已发布文章 / Published Articles` 只展示 `status: ready` 的文章，并优先链接到 Wiki 阅读页。
- README 的草稿入口只展示仍在写作中的文章，链接回主仓库源码 Markdown。
- 已经发布过的文章如果继续修改，仍保持 `status: ready`；重新 push 后会覆盖刷新 Wiki 页面。

## Wiki 定位

GitHub Wiki 是当前轻量展示层，不是创作源头。

适合放：

- 已经稳定的文章。
- 文章目录。
- 对外阅读入口。

不适合放：

- 初稿、半成品、临时记录。
- 私有记忆、客户信息、密钥、cookie、内部路径。
- 需要频繁协作审阅的源稿。

## 同步规则

同步脚本从主仓库读取 `content/articles/*.md`。

同步范围：

- 只同步 `status: ready` 的文章。
- 已经发布过的文章，如果主仓库文章后续修改，重新运行同步脚本时需要覆盖更新到 Wiki。
- 非 `ready` 状态的文章不会写入 Wiki。

当前脚本：

```bash
python3 scripts/update_readme_index.py
python3 scripts/sync_wiki.py
```

默认行为：

- `scripts/update_readme_index.py` 根据 frontmatter 生成 README 和 README-EN 的 `已发布文章 / Published Articles` 区块。
- 生成或更新本地 Wiki working copy：`.wiki/ai-work-system.wiki/`
- 生成 `Home.md`
- 生成 `_Sidebar.md`
- 为每篇 `ready` 文章生成一个 Wiki 页面；文章页文件名带 `01-`、`02-` 这类阅读序号前缀，用来稳定 Gitee 左侧页面树顺序。
- 在每篇文章底部生成“上一篇 / 目录 / 下一篇”连续阅读导航。
- Home 和 Sidebar 使用标准 Markdown 链接，不依赖 GitHub 专属 `[[title|page]]` Wiki 语法，避免 Gitee Wiki 渲染成原始文本。
- 每次同步都会全量重建文章导航；新增第 n 篇后，第 n-1 篇的“下一篇”也会自动更新。首篇的“上一篇”和末篇的“下一篇”固定显示为“无”。
- 同步时会清理旧的已生成文章页面，避免改名后 Gitee 左侧残留旧页面；没有文章来源标记的手工 Wiki 页面不会被自动删除。
- 不自动 push

发布到远端 Wiki 时显式执行：

```bash
python3 scripts/sync_wiki.py --push
```

如果首次同步时 GitHub 返回 `Repository not found`，说明 GitHub 还没有初始化独立的 Wiki Git 仓库。先在 GitHub Web UI 的 Wiki 页面手动创建第一篇 `Home` 页面，再重新运行：

```bash
python3 scripts/sync_wiki.py --push
```

## 自动触发

仓库已通过 GitHub Actions 自动触发 Wiki 同步：

```text
.github/workflows/sync-wiki.yml
```

触发条件：

- `main` 分支上 `content/articles/**` 有变化。
- `main` 分支上 `scripts/sync_wiki.py` 有变化。
- 手动在 GitHub Actions 页面运行 `Sync Wiki`。

自动同步发生在主仓库 push 成功之后，因此日常只需要维护主仓库 Markdown。只要文章是 `status: ready`，推送到 `main` 后 workflow 会自动运行 `python3 scripts/sync_wiki.py --push`，刷新 Wiki 的 `Home.md`、`_Sidebar.md` 和文章页面。

如果 GitHub 默认 `GITHUB_TOKEN` 无法写入 Wiki 仓库，需要在仓库 Secrets 中添加具备 Wiki 写入权限的 `WIKI_PUSH_TOKEN`，workflow 会优先使用该 token。

## Gitee Wiki 同步

Gitee 仓库由 GitHub Actions 的 `.github/workflows/sync-to-gitee.yml` 从 GitHub `main` 镜像过去。

Gitee Wiki 当前由 GitHub Actions 的 `.github/workflows/sync-to-gitee.yml` 统一同步。该 workflow 会先把主仓库镜像到 Gitee main，再执行一次 Gitee Wiki 同步：

```text
GitHub main
  -> GitHub Actions 同步主仓库到 Gitee main
  -> GitHub Actions 运行 scripts/sync_wiki.py
  -> 推送到 https://gitee.com/ExDevilLee/ai-work-system.wiki.git
```

Gitee Go 发布链路已停用，仓库不再保留 `.workflow/sync-gitee-wiki.yml`。这样可以避免 GitHub Actions 和 Gitee Go 同时推送 Gitee Wiki，减少重复执行和偶发竞态。

GitHub Actions 路径复用同步主仓库到 Gitee 时已有的 GitHub Secrets：

- `GITEE_USERNAME`
- `GITEE_TOKEN`
- `GITEE_REPO`

Gitee Wiki 使用同一个同步脚本，但指定不同远端和展示层名称：

```bash
python3 scripts/sync_wiki.py --push \
  --site-name "Gitee Wiki" \
  --wiki-dir ".wiki/ai-work-system.gitee-wiki" \
  --remote "https://gitee.com/ExDevilLee/ai-work-system.wiki.git" \
  --wiki-base-url "https://gitee.com/ExDevilLee/ai-work-system/wikis"
```

## 墨问同步

墨问由 `.github/workflows/sync-mowen.yml` 发布。为避免正文图片尚未进入 Gitee Raw 地址时就开始上传，墨问 workflow 会等待 `Sync to Gitee` 成功完成后再触发；手动运行入口仍然保留。

Gitee 同步由任意主仓库 push 触发，但墨问只在文章、墨问资源、映射或墨问发布脚本发生变化时继续执行。README、Wiki 生成脚本或普通文档单独变化时，墨问 job 会成功跳过发布步骤，不消耗 API 调用额度。

```bash
python3 scripts/sync_mowen.py
python3 scripts/sync_mowen.py --register-private
python3 scripts/sync_mowen.py --publish \
  --cover-url "https://gitee.com/ExDevilLee/ai-work-system/raw/main/assets/mowen/ai-work-system-cover.jpg"
```

默认命令只完成所有 `ready` 文章的 Markdown 转换验证，不访问墨问。`--register-private` 只为缺少映射的新文章创建私密笔记，不覆盖已经公开的文章；`--publish` 只更新内容哈希发生变化的文章，确保文章公开后再重建《AI 长期工作系统》目录。正文和目录均未变化时会跳过编辑，避免浪费墨问 API 配额。

当前未开通墨问 PRO，现有账号从接口错误信息观察到每天 10 次 API 调用额度。一般日常发布足够使用；若出现 `403 QUOTA` 或 `quota exceed`，当天停止重跑，等待次日额度恢复。CI 即使因额度失败，也会尝试提交本轮已经产生的 `publishing/mowen-notes.json` 进度，并通过 `[skip ci]` 避免进度提交再次触发发布。脚本下次运行时会根据源文、内容哈希和持久映射跳过已完成项目，继续处理剩余任务。只有免费额度持续影响正常发布时，再评估开通 PRO。

墨问目录规则：

- 标题固定为《AI 长期工作系统》。
- 正文包含项目介绍、封面和所有文章的原生笔记卡片。
- 单篇文章在墨问展示时按系列时间正序添加两位编号，例如 `01-标题`、`02-标题`；仓库源 Markdown 标题保持不变。
- 文章按日期倒序排列；最新文章显示在最上方。
- 目录底部提供 GitHub Wiki 首发地址，便于读者返回系列文章入口。
- `publishing/mowen-notes.json` 保存文章和目录的墨问笔记 ID，保证重跑时编辑原笔记而不是重复创建。
- `assets/mowen/ai-work-system-cover.jpg` 是 GitHub 主仓库管理的封面源文件；墨问从 Gitee 同步镜像读取图片，脚本会先核对两边文件哈希，再决定是否重新上传。

GitHub Actions 需要仓库 Secret `MOWEN_API_KEY`。Secret 只通过环境变量传给官方 MCP 接口，不写入仓库或日志。

新文章首次发布时，workflow 会先私密创建笔记并更新映射，再公开文章和目录。若任务在创建后、映射提交前中断，可能遗留私密重复笔记；恢复前先使用 `mocli note mine --filter priv` 核对，再补回或修正映射。

### 正文配图

文章配图与 Markdown 源文放在同一内容目录下，例如：

```text
content/articles/
  2026-07-09-minimum-project-memory-system.md
  images/04/minimum-project-memory-system.png
```

源文使用 `images/<文章编号>/<文件名>` 相对路径，保证 Codex 和 VS Code 可以直接本地预览。发布时不要求作者手工切换地址：

- GitHub Wiki 同步脚本把相对路径改写为 GitHub Raw 地址。
- Gitee Wiki 同步脚本把相对路径改写为 Gitee Raw 地址。
- 墨问同步脚本先通过 `UploadViaURL` 上传图片，把转换器生成的临时图片 UUID 替换为真实 UUID，再编辑正文。
- Gitee Raw 暂时返回 `404` 时会等待重试，处理 workflow 完成后仍可能存在的短暂缓存延迟。
- `publishing/mowen-notes.json` 按文章保存图片哈希、来源 URL 和墨问 UUID；图片内容未变化时直接复用，避免重复上传和消耗接口额度。

`md-to-mowen --dry-run` 生成的图片 UUID 仅用于本地转换占位，不能直接发送给墨问 `EditRichNote`。如果忽略上传和替换步骤，远端会返回 `OPEN_MCP_NOTE_EDIT_FAIL`。

## 后续扩展

未来可以继续增加展示层：

- 个人网站：从 `content/articles/*.md` 构建静态站。
- 微信公众号：从 Markdown 生成排版 HTML，人工确认后发布。
- 知乎或其他平台：生成平台适配版本。

这些展示层都应该从主仓库生成，不直接成为源稿。
