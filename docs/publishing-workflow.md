# 发布工作流约定

本文记录本仓库的内容源头和展示层同步约定。

## 基本原则

主仓库 Markdown 是唯一内容源头。

```text
content/articles/<series-id>/*.md
  -> GitHub Wiki
  -> Gitee Wiki
  -> 各系列的墨问目录
  -> 未来个人网站
  -> 未来微信公众号 / 知乎 / 其他平台
```

所有展示层只负责展示，不反向修改源文。

如果在 Wiki、个人网站或其他平台发现需要改文章，应该回到主仓库修改 `content/articles/<series-id>/*.md`，再重新同步。

文章正文默认以中文为主。`README-EN.md` 提供英文项目入口和文章导航，文章可以维护 `title_en`、`summary_en` 等英文元信息；完整英文译文按需维护，不作为每篇文章的默认发布要求。

## 内容状态

文章通过 frontmatter 的 `status` 字段表示当前阶段：

- `draft`：草稿阶段，不同步到展示层。
- `review`：发布前审阅阶段，不默认同步到展示层。
- `ready`：发布源稿阶段，可以同步到展示层；推送到 `main` 后会由 CI 发布或刷新到 Wiki。

当前只同步 `status: ready` 的文章到 GitHub Wiki、Gitee Wiki 和墨问。

`status` 描述的是主仓库源稿是否可以进入自动发布链路，不直接等同于 README 里的展示分类：

- README 的 `系列文章 / Article Series` 按 `content/series.json` 分组展示 `status: ready` 的文章，并优先链接到 Wiki 阅读页。
- README 的草稿入口只展示仍在写作中的文章，链接回主仓库源码 Markdown。
- 已经发布过的文章如果继续修改，仍保持 `status: ready`；重新 push 后会覆盖刷新 Wiki 页面。

## 配图判断门禁

新文章进入 `status: review` 前必须完成一次配图必要性判断。目标不是让每篇文章都有图，而是在纯文字难以快速说明关系时，用简单图示降低读者的理解成本。

写作阶段按下面的顺序处理：

1. 大纲阶段标记可能需要图示的段落。
2. 初稿完成后，根据完整正文判断配图是否真的能帮助理解。
3. 如果需要配图，在进入 `review` 前完成图片生成、正文插入和本地预览；Review 看到的应当是图文位置已经确定的文章。
4. 如果不需要配图，在阶段汇总中明确说明“本篇无需配图”及简短理由，不为了统一形式添加装饰图。

优先考虑配图的情况：

- 一个概念包含多个组成部分或层级。
- 存在前后变化、阶段演进、状态流转或因果链路。
- 两种方案、两类记忆或多个角色需要并列对比。
- 纯文字需要较长篇幅才能说明对象之间的关系。
- 一张简单图能够让非程序员更快抓住核心结论。

通常不需要配图的情况：

- 简单列表或短段落已经足够清楚。
- 图片只是重复正文文字，没有增加结构信息。
- 图片主要用于装饰，不能降低理解成本。
- 为了让所有文章形式一致而强行添加图片。

需要配图时，继续遵守本文后面的正文配图路径和发布规则。图示优先使用少量节点、中文显示文本和普通读者能理解的结构，避免专业流程图、时序图或过密信息。

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

同步脚本从主仓库读取 `content/series.json` 和 `content/articles/<series-id>/*.md`。前者保存系列顺序、名称、状态及各平台目录信息；后者所在目录必须与 frontmatter 的 `series` 字段一致。

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

- `scripts/update_readme_index.py` 根据系列目录和 frontmatter 生成 README 和 README-EN 的 `系列文章 / Article Series` 区块。
- 生成或更新本地 Wiki working copy：`.wiki/ai-work-system.wiki/`
- 生成按系列分组的 `Home.md`、`_Sidebar.md` 和各系列目录页。
- 为每篇 `ready` 文章生成一个 Wiki 页面；文章页文件名继续使用全局 `01-`、`02-` 编号，用来保持旧 URL 和 Gitee 左侧页面树顺序稳定。
- 在每篇文章底部生成“上一篇 / 目录 / 下一篇”连续阅读导航；上一篇和下一篇只在当前系列内计算，目录指向当前系列目录页。
- Home 和 Sidebar 使用标准 Markdown 链接，不依赖 GitHub 专属 `[[title|page]]` Wiki 语法，避免 Gitee Wiki 渲染成原始文本。
- 每次同步都会全量重建文章导航；同一系列新增第 n 篇后，该系列第 n-1 篇的“下一篇”也会自动更新。每个系列首篇和末篇缺少相邻文章的导航单元格固定显示为“无”。
- 同步时会清理旧的已生成文章页和系列目录页，避免改名后 Gitee 左侧残留旧页面；没有生成标记的手工 Wiki 页面不会被自动删除。
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
- `main` 分支上 `content/series.json` 有变化。
- `main` 分支上 `scripts/sync_wiki.py` 有变化。
- 手动在 GitHub Actions 页面运行 `Sync Wiki`。

自动同步发生在主仓库 push 成功之后，因此日常只需要维护主仓库 Markdown。只要文章是 `status: ready`，推送到 `main` 后 workflow 会自动运行 `python3 scripts/sync_wiki.py --push`，刷新 Wiki 的 `Home.md`、`_Sidebar.md` 和文章页面。

### Wiki 自动验收

GitHub Wiki 与 Gitee Wiki 共用 `scripts/verify_wiki.py`，在同一条发布流水线中执行两阶段检查：

- 发布前：用标准 YAML 解析 frontmatter，检查 ready 文章配图是否存在、非空、路径编号正确、扩展名与文件签名一致；随后在临时目录全量生成 Wiki，检查页面清单、连续阅读导航和目标平台图片 URL。
- 发布后：重新克隆目标 Wiki 仓库，与本次预期生成的 Markdown 逐页比较；再请求全部正文配图并比较 SHA-256，确认远端不是可访问但内容陈旧的旧图。
- 远端 Wiki 或图片存在短暂可见性延迟时，默认最多检查 6 次、每次间隔 10 秒。超过窗口后 workflow 失败，日志会标明 `pre-publish` / `post-publish` 以及具体页面或图片。

本检查能够证明源文、生成页面、远端 Wiki 文件和远端图片内容一致，但不判断配图是否美观、位置是否自然。视觉与叙事效果仍由人工抽查。

本地可以独立运行发布前检查：

```bash
python -m pip install --requirement requirements-wiki.txt
python scripts/verify_wiki.py \
  --phase pre \
  --site-name "GitHub Wiki" \
  --wiki-base-url "https://github.com/ExDevilLee/ai-work-system/wiki" \
  --asset-base-url "https://raw.githubusercontent.com/ExDevilLee/ai-work-system/main"
```

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

默认命令只完成所有 `ready` 文章的 Markdown 转换验证，不访问墨问。`--register-private` 只为缺少映射的新文章创建私密笔记，不覆盖已经公开的文章；`--publish` 只更新内容哈希发生变化的文章，确保文章公开后再重建其所属系列目录。正文和目录均未变化时会跳过编辑，避免浪费墨问 API 配额。

墨问接口可能根据账号套餐和统计周期限制 API 调用。若出现 `403 QUOTA` 或 `quota exceed`，停止连续重跑，等待平台额度恢复。CI 即使因额度失败，也会尝试提交本轮已经产生的 `publishing/mowen-notes.json` 进度，并通过 `[skip ci]` 避免进度提交再次触发发布。脚本下次运行时会根据源文、内容哈希和持久映射跳过已完成项目，继续处理剩余任务。具体额度以平台最新规则和服务端响应为准。

若墨问在公开文章时返回 `403 RISKY`，脚本会保留已经创建或更新的私密笔记，在映射中记录 `publication_blocked`，并避免对同一内容重复创建笔记或重复请求公开。被阻塞的文章不会进入公开系列目录。该状态代表平台内容风控，不通过修改接口调用方式绕过；需要人工检查墨问私密笔记、平台审核状态和正文表达。人工确认文章已经公开后，再把映射中的 `published` 更新为 `true` 并移除 `publication_blocked`，后续流水线会把文章加入系列目录。

同步日志只记录本轮已尝试和已成功的 MCP 调用次数，不根据固定数字估算剩余额度，也不把额度写入 `publishing/mowen-notes.json`。服务端明确返回 `403 QUOTA` 时，以服务端结果为准并停止重跑。

当新文章发布与旧文章更新同时存在时，墨问按“新文章正文与配图 -> 立即更新目录 -> 旧文章更新”的顺序执行。这样当前可用额度不足以完成全部欠账时，新文章仍优先进入公开目录；旧文章配图留到额度恢复或下一次运行继续处理。

墨问系列目录规则：

- 每个系列使用 `content/series.json` 中登记的目录标题和介绍。
- 正文包含系列介绍、可选封面和本系列所有文章的原生笔记卡片。
- 单篇文章在墨问展示时按系列内时间正序添加两位编号，例如 `01-标题`、`02-标题`；新系列从 `01-` 重新开始，仓库源 Markdown 标题保持不变。
- 文章按日期倒序排列；最新文章显示在最上方。
- 目录底部提供 GitHub Wiki 首发地址，便于读者返回系列文章入口。
- `publishing/mowen-notes.json` 的 `directories.<series-id>` 分别保存目录笔记 ID，保证重跑时编辑原笔记而不是重复创建。
- 当前 `--cover-url` 和 `assets/mowen/ai-work-system-cover.jpg` 只用于第一系列；脚本从 Gitee 同步镜像读取图片，并先核对两边文件哈希再决定是否重新上传。

新系列第一篇文章进入 `ready` 前，先在墨问创建对应目录，并把 `note_id`、公开 URL 与发布状态登记到 `publishing/mowen-notes.json` 的 `directories.<series-id>`。系列 ID 必须先存在于 `content/series.json`；不要让两个文件使用不同标识。

GitHub Actions 需要仓库 Secret `MOWEN_API_KEY`。Secret 只通过环境变量传给官方 MCP 接口，不写入仓库或日志。

新文章首次发布时，workflow 会先私密创建笔记并更新映射，再公开文章和目录。若任务在创建后、映射提交前中断，可能遗留私密重复笔记；恢复前先使用 `mocli note mine --filter priv` 核对，再补回或修正映射。

### 正文配图

文章配图与 Markdown 源文放在同一内容目录下，例如：

```text
content/articles/
  long-term-ai-work-system/
    2026-07-09-minimum-project-memory-system.md
    images/04/minimum-project-memory-system.png
```

每个系列使用 frontmatter 中稳定的 `series id` 作为目录名，不使用可能变化或需要 URL 编码的系列展示名称。系列目录内的源文统一使用 `images/<系列内文章编号>/<文件名>` 相对路径，例如：

```markdown
![最小项目记忆系统结构图](images/04/minimum-project-memory-system.png)
```

文章编号按系列内顺序计算，每个新系列都可以从 `01` 重新开始；文章所在系列目录必须与 frontmatter 的 `series` 一致。这样既能避免不同系列的 `01`、`02` 图片互相覆盖，也能保证 Codex 和 VS Code 直接本地预览。发布时不要求作者手工切换地址：

- GitHub Wiki 同步脚本把相对路径改写为 GitHub Raw 地址。
- Gitee Wiki 同步脚本把相对路径改写为 Gitee Raw 地址。
- 墨问同步脚本先通过 `UploadViaURL` 上传图片，把转换器生成的临时图片 UUID 替换为真实 UUID，再编辑正文。
- Gitee Raw 暂时返回 `404` 时会等待重试，处理 workflow 完成后仍可能存在的短暂缓存延迟。
- `publishing/mowen-notes.json` 按文章保存图片哈希、来源 URL 和墨问 UUID；图片内容未变化时直接复用，避免重复上传和消耗接口额度。

`md-to-mowen --dry-run` 生成的图片 UUID 仅用于本地转换占位，不能直接发送给墨问 `EditRichNote`。如果忽略上传和替换步骤，远端会返回 `OPEN_MCP_NOTE_EDIT_FAIL`。

## 后续扩展

未来可以继续增加展示层：

- 个人网站：从 `content/articles/<series-id>/*.md` 构建静态站。
- 微信公众号：从 Markdown 生成排版 HTML，人工确认后发布。
- 知乎或其他平台：生成平台适配版本。

这些展示层都应该从主仓库生成，不直接成为源稿。
