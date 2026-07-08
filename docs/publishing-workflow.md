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
- `ready`：可发布稿阶段，可以同步到展示层。

第一阶段只同步 `status: ready` 的文章到 GitHub Wiki。

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
python3 scripts/sync_wiki.py
```

默认行为：

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

## 后续扩展

未来可以继续增加展示层：

- 个人网站：从 `content/articles/*.md` 构建静态站。
- 微信公众号：从 Markdown 生成排版 HTML，人工确认后发布。
- 知乎或其他平台：生成平台适配版本。

这些展示层都应该从主仓库生成，不直接成为源稿。
