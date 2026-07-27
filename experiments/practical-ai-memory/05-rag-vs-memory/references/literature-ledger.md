# 文献引用台账

本文件记录第五篇文章使用的外部原始资料及允许支持的主张。文章只引用下列论文的公开页面，不把论文主张扩大为本 POC 已经验证的结论。

## SRC-001 Retrieval-Augmented Generation

- Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., Kuttler, H., Lewis, M., Yih, W., Rocktaschel, T., Riedel, S., & Kiela, D. (2020). *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*. NeurIPS 2020. <https://arxiv.org/abs/2005.11401>
- 原始资料状态：arXiv 摘要与版本信息已于 2026-07-27 核对。
- 可支持：RAG 原论文把稠密向量索引称为显式的 non-parametric memory，并将其与参数化模型结合用于生成。
- 不可支持：RAG 自动维护项目决定的批准状态、适用范围或生命周期。

## SRC-002 Cognitive Architectures for Language Agents

- Sumers, T. R., Yao, S., Narasimhan, K., & Griffiths, T. L. (2023). *Cognitive Architectures for Language Agents*. Transactions on Machine Learning Research. <https://arxiv.org/abs/2309.02427>
- 原始资料状态：arXiv v3 摘要与 TMLR camera-ready 说明已于 2026-07-27 核对。
- 可支持：CoALA 用模块化记忆、结构化行动空间和决策过程描述语言 Agent，记忆与行动选择不是同一个模块。
- 不可支持：本 POC 的三种条件就是 CoALA 的标准实现。

## SRC-003 MemGPT

- Packer, C., Wooders, S., Lin, K., Fang, V., Patil, S. G., Stoica, I., & Gonzalez, J. E. (2023). *MemGPT: Towards LLMs as Operating Systems*. <https://arxiv.org/abs/2310.08560>
- 原始资料状态：arXiv v2 摘要已于 2026-07-27 核对。
- 可支持：MemGPT 使用受操作系统分层内存启发的 virtual context management，在有限上下文窗口内管理不同记忆层级。
- 不可支持：分层上下文管理本身已经解决批准、冲突、范围和生命周期治理。

## 写作边界

- “RAG 找回资料不等于形成可指导当前行动的长期记忆”是本 POC 在冻结协议下的项目结论，不是上述论文的原句。
- 本文不主张 RAG 论文中的 non-parametric memory 用词错误，也不主张向量数据库不能保存状态字段。
- 本文不比较 embedding、rerank、召回率或向量数据库性能。
