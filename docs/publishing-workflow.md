# 发布工作流约定

本文记录本仓库的内容源头和展示层同步约定。

## 基本原则

主仓库 Markdown 是唯一内容源头。

```text
content/articles/*.md
  -> GitHub Wiki
  -> 未来个人网站
  -> 未来微信公众号 / 知乎 / 其他平台
```

所有展示层只负责展示，不反向修改源文。

如果在 Wiki、个人网站或其他平台发现需要改文章，应该回到主仓库修改 `content/articles/*.md`，再重新同步。

## 内容状态

文章通过 frontmatter 的 `status` 字段表示当前阶段：

- `draft`：草稿阶段，不同步到展示层。
- `review`：发布前审阅阶段，不默认同步到展示层。
- `ready`：发布源稿阶段，可以同步到展示层；推送到 `main` 后会由 CI 发布或刷新到 Wiki。

第一阶段只同步 `status: ready` 的文章到 GitHub Wiki 和 Gitee Wiki。

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
- 为每篇 `ready` 文章生成一个 Wiki 页面
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

Gitee 侧 Wiki 通过 Gitee Go 流水线同步：

```text
.workflow/sync-gitee-wiki.yml
```

同步链路：

```text
GitHub main
  -> GitHub Actions 同步主仓库到 Gitee main
  -> Gitee Go 监听 Gitee main push
  -> 运行 scripts/sync_wiki.py
  -> 推送到 https://gitee.com/ExDevilLee/ai-work-system.wiki.git
```

Gitee Go 需要配置流水线变量或密钥：

- `WIKI_PUSH_TOKEN`：具备推送 Gitee Wiki 仓库权限的 token。
- `WIKI_PUSH_USERNAME`：可选，默认 `ExDevilLee`。
- `WIKI_PUSH_EMAIL`：可选，默认 `gitee-go@users.noreply.gitee.com`。

在 Gitee Go 中，先到 `通用变量` 创建 `WIKI_PUSH_TOKEN`，并勾选 `密文`；然后进入 `Sync Gitee Wiki` 流水线编辑页，把该通用变量关联到流水线。只创建通用变量但不关联流水线时，构建环境可能拿不到该变量。

不要使用 `GITEE_` 或 `GO_` 作为自定义变量前缀；这些前缀在 Gitee Go 中属于系统变量命名空间，容易和平台内置参数冲突。

Gitee Wiki 使用同一个同步脚本，但指定不同远端和展示层名称：

```bash
python3 scripts/sync_wiki.py --push \
  --site-name "Gitee Wiki" \
  --wiki-dir ".wiki/ai-work-system.gitee-wiki" \
  --remote "https://gitee.com/ExDevilLee/ai-work-system.wiki.git"
```

## 后续扩展

未来可以继续增加展示层：

- 个人网站：从 `content/articles/*.md` 构建静态站。
- 微信公众号：从 Markdown 生成排版 HTML，人工确认后发布。
- 知乎或其他平台：生成平台适配版本。

这些展示层都应该从主仓库生成，不直接成为源稿。
