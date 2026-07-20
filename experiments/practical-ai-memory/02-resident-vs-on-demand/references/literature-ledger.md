# 文献与结论边界

本账本记录第二篇文章使用的外部原始来源。项目实验数据仍以 `data/`、`evidence/` 和 `analysis/formal-macos.md` 为准；论文只用于解释研究背景，不替代本地 POC。

| ID | 来源 | 本文用途 | 不能支持的结论 |
| --- | --- | --- | --- |
| SRC-001 | Packer et al., *MemGPT: Towards LLMs as Operating Systems*, arXiv:2310.08560 | 说明不同记忆层与虚拟上下文管理是已有研究方向 | 不能证明三份 Markdown 或选择性常驻一定更优 |
| SRC-002 | Liu et al., *Lost in the Middle: How Language Models Use Long Contexts*, arXiv:2307.03172 | 说明模型在论文测试任务中不能稳健利用长上下文中的所有位置 | 不能直接证明本 POC 的常驻入口会降低正确性 |
| SRC-003 | Lewis et al., *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*, arXiv:2005.11401 | 说明外部非参数记忆可以通过检索进入生成过程 | 不能把文件索引 POC 等同于完整 RAG 系统 |

核验入口：

- <https://arxiv.org/abs/2310.08560>
- <https://arxiv.org/abs/2307.03172>
- <https://arxiv.org/abs/2005.11401>
