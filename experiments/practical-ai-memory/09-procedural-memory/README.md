# 程序性记忆 POC

这是“AI 长期记忆实战”系列第九篇的实验入口，研究事实之外的规则、Skill 和工作流能否成为可复用的程序性记忆。

当前阶段是 `formal-matrix-complete-review-complete`：旧双配置 Pilot 保留为协议演进证据；新任务表上的双配置正式矩阵与逐格边界 Review 已完成，合计 224/270 通过。45 格因三个 15 格批次的 JSON 结构错误失败，另有 1 格禁止自动晋升字段失真。公开文章已升级为正式矩阵口径，不把三条件通过率解释为载体优劣。

## 核心问题

在一组同类、可重复且使用合成资料的任务中，稳定的 Guide/Skill 是否比每次重新给临时提示词带来更少的重复说明、返工和人工 Review，同时不扩大适用范围或自动固化偶然经验？

## 当前边界

- 只使用合成任务、合成项目文件和脱敏的过程指标。
- 对比 `prompt-only`、`guide-assisted` 和 `skill-workflow` 三种条件。
- 不把外部 Skill 采用率当作效果证据。
- 不把一次成功直接晋升为长期规则；晋升必须经过重复证据、适用范围和人工 Review。
- 以 macOS 双配置正式矩阵为主体，不声明跨平台复现。

## 文档入口

- [设计说明](DESIGN.md)
- [冻结实验协议](EXPERIMENT.md)
- [实施计划](IMPLEMENTATION-PLAN.md)
- [静态协议校验器](validate_design.py)
- [Pilot 证据分析](runs/aggregates/macos/pilot-01-analysis.md)
- [第二模型复核 Review](runs/aggregates/macos/pilot-deepseek-v4-flash-max-review.md)
- [第二模型复核证据汇总](runs/aggregates/macos/pilot-deepseek-v4-flash-max-analysis.md)
- [DeepSeek-V4-Flash Max 验证提示词](DEEPSEEK-V4-FLASH-MAX-PILOT-PROMPT.md)
- [公开证据包](evidence/README.md)
- [公开主张矩阵](evidence/claim-matrix.md)
- [公开证据校验器](validate_public_evidence.py)
- [Terra 正式矩阵 Review](runs/aggregates/macos/formal-r2-terra-medium-readonly-review.md)
- [DeepSeek 正式矩阵 Review](runs/aggregates/macos/formal-r3-deepseek-max-readonly-review.md)
- [正式矩阵合并汇总](runs/aggregates/macos/formal-cross-config-summary.md)

## 已接受的证据边界

- 第二模型的 45 格脱敏 final 已进入公开 manifest，并展开 9 个代表样本。
- Terra Pilot 的原始 final 当时只写入临时目录，当前公开包只保留聚合 Review、修复 Review 与分析报告；manifest 将其明确标记为 `aggregate-only`，不补造逐格记录。
- 文章可以讨论两组配置出现不同首轮边界结果，但不能把差异归因于模型、推理强度或执行路径中的单一变量。
- 本 POC 只覆盖 macOS 合成任务，不支持真实项目、生产率、跨平台或普遍模型能力声明。
- 正式矩阵统一保存两组 raw final 与 metadata；公开数据只保留脱敏聚合，私有事件流不提交。
