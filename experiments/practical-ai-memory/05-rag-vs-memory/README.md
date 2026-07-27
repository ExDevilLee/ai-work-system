# RAG 与长期记忆行动治理 POC

本实验为“AI 长期记忆实战”系列第五篇提供证据，验证一个刻意收窄的问题：当相关资料已经被正确检索出来以后，仅有检索结果是否足以支持当前行动，还是仍然需要状态、范围和来源治理。

## 当前阶段

实验夹具、验证器、隔离运行器、矩阵调度、评分和聚合工具已经完成实现。Pilot 01 暴露条件不可区分问题，Pilot 02 验证了主要条件差异但发现历史任务缺少技术原因证据，修订后的 Pilot 03 通过全部门禁后，已按冻结协议完成 45 次 macOS 正式运行、真实计时 Review、评分和聚合。

正式结果：

- 45/45 运行通过协议门禁，15 个任务/条件组合均为 `n=3`。
- `rag-only`：75/84。
- `rag-with-recency`：69/84。
- `memory-governed`：84/84。
- 45/45 工作区指标覆盖完整且输出可靠。
- 正式矩阵只验证相同 Top-K 证据下的行动治理，不评价召回算法。

详细结果见 [`analysis/formal-macos.md`](analysis/formal-macos.md)。第五篇文章已根据 macOS 结果进入 `review`，Win11 尚未复现。

已确认的实验边界：

- 正式矩阵使用冻结的相同 Top-K 检索包，不比较 embedding、rerank 或召回算法。
- Pilot 增加一次 SQLite FTS5/BM25 召回核验，验证冻结检索包能够由普通检索获得；该结果不进入正式评分。
- 对比 `rag-only`、`rag-with-recency` 和 `memory-governed` 三种行动治理条件。
- 使用 5 类任务，同时覆盖 RAG 擅长的静态事实检索和需要当前状态判断的行动问题。
- macOS 是首轮主体平台，冻结协议后再由 Win11 复现。

Pilot Review 记录：

- [`analysis/pilot-01.md`](analysis/pilot-01.md)：条件不可区分。
- [`analysis/pilot-02.md`](analysis/pilot-02.md)：形成差异，但历史原因证据缺失。
- [`analysis/pilot-03.md`](analysis/pilot-03.md)：通过，建议冻结正式矩阵。
- [`analysis/formal-macos.md`](analysis/formal-macos.md)：45 次正式运行、评分与结果边界。

完整研究问题、条件定义、评分结构和停止门禁见 [`EXPERIMENT.md`](EXPERIMENT.md)。

## 结论边界

当前目录只记录已经确认的实验设计，不代表以下主张已经获得验证：

- RAG 不能形成长期记忆。
- `memory-governed` 一定优于另外两组。
- 向量数据库不能承载记忆状态。
- 一份当前状态索引足以解决真实项目中的全部记忆问题。

当前阶段性结论仅适用于冻结协议、当前模型配置和 macOS 工具链。Win11 复现完成前，不形成跨平台结论。
