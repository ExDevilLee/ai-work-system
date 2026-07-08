# 发布 Runbook

本文用于在日常写作和发布时快速检查链路，不替代完整约定文档：[publishing-workflow.md](publishing-workflow.md)。

## 日常发布步骤

1. 在 `content/articles/*.md` 写文章。
2. 草稿阶段保持 `status: draft`。
3. 发布前审阅时可改为 `status: review`。
4. 确认可公开后改为 `status: ready`。
5. 运行文章索引更新：

```bash
python3 scripts/update_readme_index.py
```

6. 本地验证 Wiki 同步范围：

```bash
python3 scripts/sync_wiki.py --dry-run
```

7. 提交并 push 到 `main`。
8. 等待自动链路完成：

```text
GitHub main
  -> GitHub Actions 同步到 GitHub Wiki
  -> GitHub Actions 镜像主仓库到 Gitee main
  -> Gitee Go 发布到 Gitee Wiki
```

9. 打开 GitHub Wiki 和 Gitee Wiki 检查文章阅读页。

## 快速排障

### README 文章列表不对

先运行：

```bash
python3 scripts/update_readme_index.py
git diff -- README.md README-EN.md
```

如果文章没有出现在 `已发布文章` 中，检查文章 frontmatter 是否为 `status: ready`。

### GitHub Wiki 没有更新

检查 GitHub Actions 中 Wiki 同步 workflow 是否运行。

常见原因：

- 文章没有设为 `status: ready`。
- 变更路径没有命中 workflow 触发条件。
- `WIKI_PUSH_TOKEN` 不存在或权限不足。

本地可先运行：

```bash
python3 scripts/sync_wiki.py --dry-run
```

确认脚本能看到目标文章。

### Gitee 仓库没有同步

检查 GitHub Actions 的同步到 Gitee workflow 是否成功。

如果 GitHub 到 Gitee 的镜像失败，Gitee Go 不会看到新的 push，也就不会触发 Gitee Wiki 发布。

### Gitee Wiki 没有更新

检查 Gitee Go 的 `Sync Gitee Wiki` 流水线。

常见原因：

- `WIKI_PUSH_TOKEN` 只创建在通用变量里，但没有关联到流水线。
- token 权限不足或已失效。
- 自定义变量使用了 `GITEE_` 或 `GO_` 前缀，和平台系统变量冲突。

### Wiki 页面内容不对

不要直接修改 Wiki 页面。

回到主仓库修改 `content/articles/*.md`，保持源文为唯一内容源头，然后重新 push 触发同步。
