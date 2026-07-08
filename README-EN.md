# AI Work System

A public writing and publishing workspace for building a long-term personal AI work system.

中文说明见 [README.md](README.md).

`CodexClaw` refers to my long-term personal AI work system and collaboration practice built around Codex, not a single standalone product.

## What This Repository Is For

This repository will collect public writing, notes, templates, and publishing workflow experiments about building a personal AI work system that can accumulate context over time.

The core theme:

> From one-off AI chats to a long-term AI work system with memory, workflow, evidence, and review.

## Planned Content

- Essays about long-term AI collaboration.
- Public notes and frameworks distilled from real practice.
- Templates for memory, workflow, and publishing.
- A lightweight static-site publishing pipeline.
- Platform-specific exports for personal websites and other publishing channels.

## Published Articles

<!-- articles:index:start -->
- [I Am Not Just Using AI Tools; I Am Building A Long-Term Work System](https://github.com/ExDevilLee/ai-work-system/wiki/01-%E6%88%91%E4%B8%8D%E6%98%AF%E5%9C%A8%E4%BD%BF%E7%94%A8-AI-%E5%B7%A5%E5%85%B7%EF%BC%8C%E8%80%8C%E6%98%AF%E5%9C%A8%E6%90%AD%E5%BB%BA%E9%95%BF%E6%9C%9F%E5%B7%A5%E4%BD%9C%E7%B3%BB%E7%BB%9F)
- [Why Does AI Keep Forgetting?](https://github.com/ExDevilLee/ai-work-system/wiki/02-%E4%B8%BA%E4%BB%80%E4%B9%88-AI-%E6%80%BB%E6%98%AF%E5%A4%B1%E5%BF%86%EF%BC%9F)
- [Why Does AI Writing Feel Less Artificial Inside A Long-Term Work System?](https://github.com/ExDevilLee/ai-work-system/wiki/03-%E4%B8%BA%E4%BB%80%E4%B9%88%E6%9C%89%E4%BA%86%E9%95%BF%E6%9C%9F%E5%B7%A5%E4%BD%9C%E7%B3%BB%E7%BB%9F%E5%90%8E%EF%BC%8CAI-%E5%86%99%E4%BD%9C%E5%8F%8D%E8%80%8C%E4%B8%8D%E6%98%BE-AI-%E5%91%B3%EF%BC%9F)

Article titles link to the GitHub Wiki reading pages by default; [Gitee Wiki](https://gitee.com/ExDevilLee/ai-work-system/wikis/Home) stays in sync, and source Markdown is available from each Wiki page's source link.

Article bodies are currently written in Chinese first. English titles are provided for navigation; full English translations may be added selectively.
<!-- articles:index:end -->

## Work In Progress

No public draft is currently in progress.

## Publishing Principle

Markdown is the source of truth.

Future publishing targets may include:

- Personal website
- WeChat Official Account
- Zhihu
- Short-form social posts
- Video outlines

## Publishing Workflow

Current workflow notes: [docs/publishing-workflow.md](docs/publishing-workflow.md).
Daily publishing checklist: [docs/publishing-runbook.md](docs/publishing-runbook.md).

The first display layers are GitHub Wiki and Gitee Wiki:

```bash
python3 scripts/update_readme_index.py
python3 scripts/sync_wiki.py
```

The script only syncs articles with `status: ready`. By default it only updates a local wiki working copy; use `--push` to publish to the remote Wiki.

## License

Unless otherwise noted, the content in this repository is licensed under the [Creative Commons Attribution 4.0 International License](LICENSE).

You may share and adapt the content, including for commercial purposes, as long as proper attribution is given.
