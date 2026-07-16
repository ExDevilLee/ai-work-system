# 发布 Runbook

本文用于在日常写作和发布时快速检查链路，不替代完整约定文档：[publishing-workflow.md](publishing-workflow.md)。

## 日常发布步骤

1. 在 `content/articles/*.md` 写文章。
1. 草稿阶段保持 `status: draft`。
1. 初稿完成后判断配图是否能明显降低理解成本；需要时先生成图片、插入正文并完成本地预览，不需要时在阶段汇总中说明理由。
1. 完成配图判断后，发布前审阅时可改为 `status: review`。
1. 确认可公开后改为 `status: ready`。
1. 运行文章索引更新：

```bash
python3 scripts/update_readme_index.py
```

1. 本地验证 Wiki 同步范围：

```bash
python3 scripts/sync_wiki.py --dry-run
```

1. 提交并 push 到 `main`。
1. 等待自动链路完成：

```text
GitHub main
  -> GitHub Actions 同步到 GitHub Wiki
  -> GitHub Actions 镜像主仓库到 Gitee main
  -> GitHub Actions 发布到 Gitee Wiki
  -> GitHub Actions 发布到墨问并重建受影响的系列目录
```

1. 打开 GitHub Wiki 和 Gitee Wiki 检查文章阅读页。
1. 从 README 的“墨问系列目录”进入对应系列，检查新文章是否位于目录最上方。

## 新系列首次发布

1. 在 `content/series.json` 登记稳定的系列 ID、中英文标题、顺序、Wiki 系列页和墨问目录信息。
2. 在墨问创建该系列的独立目录笔记，并完成需要的封面和公开设置。
3. 在 `publishing/mowen-notes.json` 的 `directories.<series-id>` 登记目录 `note_id`、`url` 和 `published` 状态。
4. 确认系列 ID 与文章 frontmatter 的 `series` 完全一致，再把第一篇文章推进到 `status: ready`。
5. 运行本文的本地 Wiki 与墨问转换检查后再 push。

第一系列的 Wiki 页面仍使用全局 `01-` 至 `15-` 编号，旧链接不会因新增系列改变。新系列的 Wiki 页面继续使用全局编号，但上一篇、下一篇和目录只在当前系列内导航；墨问文章编号则从 `01-` 重新开始。

## 墨问首次配置

在 GitHub 仓库的 `Settings -> Secrets and variables -> Actions` 中添加：

- Name：`MOWEN_API_KEY`
- Secret：墨问开放平台 API Key，只填写 Key 本身，不填写完整 MCP URL。

本地只验证转换，不访问远端：

```bash
python3 -m pip install -r requirements-mowen.txt
npm ci --ignore-scripts
python3 -m unittest tests.test_sync_mowen -v
python3 scripts/sync_mowen.py
```

不要把 API Key 放进命令参数、配置样例、终端截图或提交记录。

## 快速排障

### README 文章列表不对

先运行：

```bash
python3 scripts/update_readme_index.py
git diff -- README.md README-EN.md
```

如果文章没有出现在“系列文章”中，检查文章 frontmatter 是否为 `status: ready`，并确认 `series` 已登记在 `content/series.json`。

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

如果 GitHub 到 Gitee 的镜像失败，Gitee Wiki 发布也不会继续执行。

### Gitee Wiki 没有更新

检查 GitHub Actions 的 `Sync to Gitee` workflow 是否成功。该 workflow 会在镜像主仓库到 Gitee 后同步 Gitee Wiki。

常见原因：

- GitHub Secrets 中的 `GITEE_USERNAME` 或 `GITEE_TOKEN` 缺失、权限不足或已失效。
- `GITEE_REPO` 配置错误，导致主仓库镜像没有推到目标 Gitee 仓库。
- Gitee Wiki 仓库权限不足，导致 `scripts/sync_wiki.py --push` 无法推送。

### Wiki 页面内容不对

不要直接修改 Wiki 页面。

回到主仓库修改 `content/articles/*.md`，保持源文为唯一内容源头，然后重新 push 触发同步。

### 墨问文章或目录没有更新

检查 `Sync MoWen` workflow，并确认仓库 Secret `MOWEN_API_KEY` 存在且有效。

常见原因：

- 文章不是 `status: ready`。
- `publishing/mowen-notes.json` 缺少已有笔记 ID，或包含错误 ID。
- 封面尚未推送到 `main`，导致 `UploadViaURL` 无法读取公开图片 URL。
- workflow 创建了私密笔记，但在映射提交前中断。
- 墨问返回 `403 RISKY`，文章已创建为私密笔记，但平台拒绝公开。

发生中断时先运行：

```bash
mocli note mine --filter priv --recent 1d --count 20
```

确认是否已有同名私密笔记，再修正映射后重跑；不要直接再次创建公开笔记。

如果映射包含 `publication_blocked.reason: RISKY`：

1. 通过映射里的 `url` 打开对应私密笔记。
2. 检查墨问审核状态，并尝试在平台界面人工公开。
3. 不通过替换字符、拆词或改变接口调用来规避平台风控。
4. 人工确认已经公开后，将该条映射的 `published` 改为 `true`，并删除 `publication_blocked`。
5. 重新运行同步，让公开系列目录纳入这篇文章。
