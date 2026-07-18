# 文献证据台账

本文献台账在实验和写作期间持续维护。只有已经核对原始来源、且正文实际使用的条目，才进入公开文章末尾的“参考文献”。

| ID | 候选来源 | 可能支持的论点 | 原始入口 | 核对状态 | 正文使用状态 |
| --- | --- | --- | --- | --- | --- |
| SRC-001 | Packer, C., et al. (2023). *MemGPT: Towards LLMs as Operating Systems*. arXiv:2310.08560. | 有限上下文促使 Agent 区分主上下文与外部上下文；外部信息需要被明确移入主上下文后才能参与推理。 | <https://arxiv.org/abs/2310.08560> | 2026-07-17 已核对摘要、架构概览、2.1 节和上下文管理说明 | 已用于解释分层与按需加载的研究背景，不用于证明本文 POC 的实验结果 |
| SRC-002 | Park, J. S., et al. (2023). *Generative Agents: Interactive Simulacra of Human Behavior*. Proceedings of the 36th Annual ACM Symposium on User Interface Software and Technology. | Agent 可以分别记录经历、检索相关记忆、形成更高层反思并用于计划；不同记忆操作承担不同职责。 | <https://arxiv.org/abs/2304.03442> | 2026-07-17 已核对摘要、架构概览、第 4 节 memory stream 与 4.2 节 reflection | 已用于说明“保存、检索、提炼”不是同一种操作，不用于把项目文件结构等同于论文架构 |
| SRC-003 | Lewis, P., et al. (2020). *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*. Advances in Neural Information Processing Systems, 33. | RAG 把模型参数中的知识与外部文档索引结合，说明外部资料检索可以作为独立的系统职责。 | <https://arxiv.org/abs/2005.11401> | 2026-07-17 已核对摘要、第 1 节、方法概览及外部文档索引说明 | 已用于解释“可索引资料”层的检索职责；不声称该论文证明“检索不是记忆” |
| SRC-004 | Atkinson, R. C., & Shiffrin, R. M. (1968) | 不同记忆存储与控制过程的经典模型，可作为“分层”类比的理论背景 | <https://doi.org/10.1016/S0079-7421(08)60422-3> | 2026-07-17 已确认 DOI 可达；待阅读全文核对 | 未使用 |
| SRC-005 | Baddeley, A. D., & Hitch, G. (1974) | 工作记忆不是单一永久存储，可辅助解释当前工作状态与长期信息的职责差异 | <https://doi.org/10.1016/S0079-7421(08)60452-1> | 2026-07-17 已确认 DOI 可达；待阅读全文核对 | 未使用 |

## 核对字段

每个被使用的来源需要保留：

- 完整书目信息。
- DOI、arXiv 或官方永久链接。
- 访问日期。
- 支持的具体论点。
- 原文页码、章节或可定位段落。
- 必要的原文摘录。
- 在文章中的引用位置。

## 已核对摘录与写作边界

### SRC-001：MemGPT

- 摘要将有限上下文视为长对话和长文档分析的限制，并提出受操作系统分层存储启发的 virtual context management。
- 架构将信息区分为 main context 和 external context；2.1 节说明外部信息必须显式移入主上下文，才能在推理时被模型使用。
- 系统说明还包含记忆层级及各自用途，以及访问或修改记忆的函数说明。
- 正文只能据此说明“分层和按需移入上下文已有相关研究”；本文的三份 Markdown 文件是更轻量的项目实践，不是 MemGPT 的复现。

### SRC-002：Generative Agents

- 摘要说明系统保存经历记录、动态检索相关记忆，并把经历综合为更高层反思，用于计划行为。
- 架构概览把 memory stream、reflection 和 planning 分开描述。
- 第 4 节说明 memory stream 保存经历记录，并从中检索与当前情境相关的内容；4.2 节说明 reflection 会形成更高层推论。
- 正文只能据此说明“记录、检索和提炼承担不同职责”；不能把本文的文件命名或实验数据归因于该论文。

### SRC-003：RAG

- 摘要和第 1 节说明 RAG 结合参数化记忆与非参数化记忆，后者在该系统中是由检索器访问的 Wikipedia 稠密向量索引。
- 方法概览明确区分检索器、文档索引和生成器。
- 论文还讨论了外部索引可更新、原始文本可读和可编辑等特点。
- 正文将其作为“外部资料检索是一种独立职责”的例子。“稳定长期记忆”和“可索引资料”分层是本项目的工程判断，不写成 RAG 论文的结论。

访问日期：2026-07-17。
