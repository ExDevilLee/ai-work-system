# 《AI 不只要记住事实：规则、Skill 和工作流怎样成为长期记忆？》——事实核查报告

**核查日期**：2026-08-17
**文章版本**：`2026-08-17-how-rules-skills-workflows-become-memory.md`（进入 `review` 的初稿）
**核查范围**：数字、实验配置、否定性边界、仓库链接和主张来源
**风险分布**：🔴 1 项链接阻断，🟡 2 项需人工确认，🟢 主要数字与本地证据一致；本轮新增外部来源 4 条，均已打开核对。

## 来源清单

| ID | 来源 | 类型 | 核查状态 |
| --- | --- | --- | --- |
| SRC-001 | `EXPERIMENT.md`、`DESIGN.md`、`fixtures/pilot-01/tasks.json` | 冻结协议与任务清单 | 🟢 已核对 |
| SRC-002 | `runs/aggregates/macos/pilot-01-review.md`、`pilot-01-repair-review.md`、`pilot-01-final-repair-review.md` | Terra Pilot-01 聚合 Review | 🟢 已核对 |
| SRC-003 | `runs/aggregates/macos/pilot-02-review.md`、`pilot-02-repair-review.md` | Terra 独立变体聚合 Review | 🟢 已核对 |
| SRC-004 | `runs/aggregates/macos/pilot-deepseek-v4-flash-max-review.md`、`pilot-deepseek-v4-flash-max-analysis.md` | 第二模型逐份 Review 与分析 | 🟢 已核对 |
| SRC-005 | `evidence/manifest.jsonl`、`evidence/claim-matrix.md` | 公开逐格记录与主张边界 | 🟢 已核对 |
| SRC-006 | GitHub 仓库链接 | 外部展示层 | 🔴 当前提交前不可用 |
| SRC-007 | Squire (2004), DOI `10.1016/j.nlm.2004.06.005` | 记忆系统综述 | 🟢 DOI 返回 200；只作概念背景 |
| SRC-008 | Anthropic (2024), *Building effective agents* | 工程文章 | 🟢 返回 200；只作设计参考 |
| SRC-009 | Anthropic (2025), *Effective harnesses for long-running agents* | 工程文章 | 🟢 返回 200；只作设计案例 |
| SRC-010 | Shinn et al. (2023), arXiv `2303.11366` | Agent 研究论文 | 🟢 arXiv 返回 200；不采用其 benchmark 作为 P9 证据 |

## 高风险核查

### 🔴 外部链接当前返回 404

- 原文位置：第 179、216、218 行。
- 实测结果：`.../09-procedural-memory` 与 `.../evidence/claim-matrix.md` 返回 HTTP 404；系列策略和公开依据规范链接返回 HTTP 200。
- 原因：P9 目录和公开包尚未提交到 `main`，不是正文事实错误。
- 建议：提交 P9 公开产物后逐条重测；在链接全部返回 200 前保持 `status: review`。

## 中风险核查

- 第 90–104 行的三组通过率与聚合报告一致；其中配置 A 的原始 final 未保留，文章已经明确降级为聚合历史，不应改写为“公开逐格复现”。
- 第 96 行的“条件级零重试”与第二模型 metadata 的 `condition_runs[*].retries = 0` 一致；同句已保留一次外层运行中断限定，没有把两者混为“全程无中断”。
- 第 173、196 行的证据缺口说明与公开包 README 一致；这是截至本次核查的仓库记录，不是对未来是否能恢复临时文件的绝对否定。
- 第 34–43 行已加入 Squire 的概念背景，并明确 AI 载体不等同于人脑记忆系统；这属于 `Keep with attribution`，不能写成神经科学对本 POC 的直接证明。
- 第 47–58 行已明确 Rule、Guide、Skill、Workflow 是本文 POC 的工程分类；Anthropic 的两篇文章只支持“简单模式优先、长任务需要结构化交接”等设计参考，不支持本文的通过率结论。
- 第 125、202 行对 Reflexion 和 Anthropic 文章的使用均已降格为研究背景或设计启发，没有搬用外部 benchmark 数字。

## 外部主张核查六元组

| 原文主张 | 类别 | 置信度 | 核查结果 | 建议口径 | 一手来源 |
| --- | --- | --- | --- | --- | --- |
| 程序性记忆可放在“记忆由多个系统构成”的框架中讨论 | 认知科学背景 | 高 | Squire 综述可支持多系统框架；不直接支持 AI 载体等同人脑机制 | 保留“概念背景”限定 | [Squire (2004)](https://doi.org/10.1016/j.nlm.2004.06.005) |
| 复杂任务应优先从简单、可组合的 workflow/agent 模式开始 | 工程设计参考 | 高 | Anthropic 文章明确区分 workflows 与 agents，并建议按任务需要增加复杂度 | 写成设计启发，不外推为 P9 结果 | [Anthropic (2024)](https://www.anthropic.com/engineering/building-effective-agents) |
| 长程任务可使用初始化、进度产物和结构化交接 | 工程设计案例 | 高 | Anthropic 文章描述了这些 harness 做法；未证明其对 P9 或所有系统普适有效 | 写成案例，不写成通用定律 | [Anthropic (2025)](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) |
| 语言化反馈可以写入 episodic memory buffer 并影响后续决策 | Agent 研究背景 | 高 | Reflexion 论文支持该机制描述；其任务和 benchmark 不属于 P9 的证据 | 只用于对照相关研究，不借用 benchmark 数字 | [Shinn et al. (2023)](https://arxiv.org/abs/2303.11366) |

## 低风险核查

- 第 64–80 行的五类任务、三种条件和四个输出字段与冻结 fixture 和协议一致。
- 第 160–171 行将能力、效率、跨平台和阈值结论明确列为“不支持”，没有发现把过程指标写成生产率的越界。
- 文章没有引用外部厂商基准、论文数字或未经核查的第三方事实，因此没有额外的外部数字核验项。

## 核查清单

- [x] 两组配置分开陈述，没有混合总分。
- [x] 数字可回到本地聚合报告或公开 manifest。
- [x] 否定性边界使用当前 POC 范围，而不是无限期断言。
- [x] 未公开本机路径、会话标识、密钥或提供方标签。
- [x] 外部论文和工程文章已放入参考文献，并在正文相邻位置标明“背景/设计参考”边界。
- [ ] 提交后重新实测 P9 GitHub 目录和公开主张矩阵链接。
- [ ] Lee 确认 Terra 原始临时 JSON 未保留这一证据完整性限制。

## 核查结论

正文的实验数字和限制在当前本地证据范围内可保留；文章可以进入人工 Review，但在公开包提交并完成链接复测前，不应升级为 `ready` 或同步到展示平台。
