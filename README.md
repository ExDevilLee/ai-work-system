# AI Work System

这是一个用于公开写作和发布实验的仓库，主题是：如何搭建一个长期持续成长、理解个人工作方式、能够沉淀经验的个人 AI 工作系统。

English version: [README-EN.md](README-EN.md)

## 这个仓库用来做什么

这个仓库会逐步沉淀：

- 关于长期 AI 协作的系列文章。
- 从真实实践中抽象出来的方法论和笔记。
- 记忆、工作流、发布流程相关的模板。
- 面向个人网站的轻量静态站发布流水线。
- 面向微信公众号、知乎、短内容平台、视频脚本等渠道的导出格式。

核心主题：

> 从一次性 AI 聊天，走向有记忆、有流程、有证据、有复盘的长期 AI 工作系统。

## 初步文章方向

- 为什么普通 AI 聊天用久了还是会失忆？
- 我是怎么给 AI 建长期记忆和工作习惯的？
- 一个不会从零开始的 AI 助手，实际能帮我做什么？
- 从 prompt 到 workflow：我如何把 AI 变成个人工作系统？
- 人和 AI 长期协作后，真正改变的不是效率，而是工作方式。

## 已发布文章

<!-- articles:index:start -->
- [我不是在使用 AI 工具，而是在搭建长期工作系统](https://github.com/ExDevilLee/ai-work-system/wiki/%E6%88%91%E4%B8%8D%E6%98%AF%E5%9C%A8%E4%BD%BF%E7%94%A8-AI-%E5%B7%A5%E5%85%B7%EF%BC%8C%E8%80%8C%E6%98%AF%E5%9C%A8%E6%90%AD%E5%BB%BA%E9%95%BF%E6%9C%9F%E5%B7%A5%E4%BD%9C%E7%B3%BB%E7%BB%9F) — 已发布到 GitHub Wiki 和 Gitee Wiki（[Gitee Wiki](https://gitee.com/ExDevilLee/ai-work-system/wikis/%E6%88%91%E4%B8%8D%E6%98%AF%E5%9C%A8%E4%BD%BF%E7%94%A8%20AI%20%E5%B7%A5%E5%85%B7%EF%BC%8C%E8%80%8C%E6%98%AF%E5%9C%A8%E6%90%AD%E5%BB%BA%E9%95%BF%E6%9C%9F%E5%B7%A5%E4%BD%9C%E7%B3%BB%E7%BB%9F)，[源码 Markdown](content/articles/2026-07-07-long-term-ai-work-system.md)）
<!-- articles:index:end -->

## 当前草稿

- [为什么 AI 总是失忆？](content/articles/2026-07-08-why-ai-keeps-forgetting.md) — 大纲草稿阶段

## 发布原则

Markdown 是内容源头。

未来可能支持的发布目标：

- 个人网站
- 微信公众号
- 知乎
- 短内容平台
- 视频口播大纲

第一阶段会优先保证个人网站自动部署；微信公众号等平台先采用人工确认或半自动发布，避免误发。

## 发布工作流

当前约定见 [docs/publishing-workflow.md](docs/publishing-workflow.md)。
日常发布检查见 [docs/publishing-runbook.md](docs/publishing-runbook.md)。

第一阶段先接入 GitHub Wiki 和 Gitee Wiki：

```bash
python3 scripts/update_readme_index.py
python3 scripts/sync_wiki.py
```

脚本只同步 `status: ready` 的文章。默认只更新本地 Wiki working copy；发布到远端 Wiki 时显式加 `--push`。

## 授权协议

除非另有说明，本仓库内容采用 [Creative Commons Attribution 4.0 International License](LICENSE) 授权。

你可以分享、转载、改编，也可以用于商业场景，但需要保留署名和来源。
