# macOS 正式实验报告（deepseek-v4-flash 对照 · 06-current-memory-map）

日期：2026-08-07

## 实验配置

- 模型：`deepseek-v4-flash`。
- 推理强度：`max`。
- 执行器：`codex-cli 0.146.1`。
- 平台：macOS，Apple Silicon。
- 会话：每次使用独立 `--ephemeral` 新会话。
- 沙箱：`read-only`。
- 样本：5 个任务 × 3 个条件共 45 次预定义正式运行（formal-01/02/03 各 15 次；每个条件恰好 15 次，每个任务 9 次）。排程与 06 冻结聚合要求的 45-run 矩阵一致（`aggregate_results.py` 校验 `formal-01..03 × 15 格`）。

本对照使用与 POC 既有协议相同的夹具与同一份 rubric/answers（每任务 5 条标准、单任务满分 5、整矩阵满分 225）。不同模型的数据没有并入同一聚合，聚合产物按模型独立命名（`data/formal-macos-deepseek-v4-flash-max.{json,csv}`）。

基线说明：

- macOS gpt 基线：`data/formal-macos-gpt-5.6-sol-medium.{json,csv}`，45 次（5 任务 × 3 条件 × 3 次），`gpt-5.6-sol`，推理强度 `medium`，`codex-cli 0.145.0`。该数据此前仅存在于 POC worktree 工作目录、未提交主仓库；本会话已恢复入库。两个模型配置都得到 225/225，本报告聚焦 deepseek 配置的过程与协议细节，双配置总分对照见文章第 6 节。

## 协议有效性

全部 45 次运行满足协议门禁：

- 退出码：45/45 为 0。
- 运行时工具访问（`runtime_tool_access_calls`）：45/45 为 0。
- 环境隔离：45/45 为 `protocol_environment_isolated: true`。
- 输出产物：45/45 均生成 final.md 与 metadata.json。
- 工作区指标覆盖完整且输出字节可靠：45/45。

`protocol_valid` 判定全部为 `yes`。

说明：06 的合规分类器比 05 更严格（命令链、组合短标志如 `rg -il` 会判为 unknown/external 而触发门禁失败）。本次 45 次正式运行中约半数格子经历过门禁失败重试（夹具、提示与 rubric 全部冻结未变，仅重跑被拒的格子；失败原因均为工具调用形态不合规，与答案正确性无关）。重试不改变协议判定口径：最终计入的 45 次全部满足上述门禁。

## 正确性（人工评分）

条件合计（deepseek-v4-flash 45 次，满分 225）：

| 条件 | deepseek-v4-flash |
| --- | ---: |
| source-only | 75/75（100%） |
| flat-index | 75/75（100%） |
| state-projection | 75/75（100%） |
| 合计 | 225/225（100%） |

格子明细（15 格全部满分）：

| 任务:条件 | deepseek-v4-flash |
| --- | ---: |
| active-decision:source-only | 15/15（n=3） |
| active-decision:flat-index | 15/15（n=3） |
| active-decision:state-projection | 15/15（n=3） |
| superseded-rule:source-only | 15/15（n=3） |
| superseded-rule:flat-index | 15/15（n=3） |
| superseded-rule:state-projection | 15/15（n=3） |
| unresolved-conflict:source-only | 15/15（n=3） |
| unresolved-conflict:flat-index | 15/15（n=3） |
| unresolved-conflict:state-projection | 15/15（n=3） |
| scope-boundary:source-only | 15/15（n=3） |
| scope-boundary:flat-index | 15/15（n=3） |
| scope-boundary:state-projection | 15/15（n=3） |
| pending-observation:source-only | 15/15（n=3） |
| pending-observation:flat-index | 15/15（n=3） |
| pending-observation:state-projection | 15/15（n=3） |

零丢分，无失败模式可归类。五个任务的判分要点全部稳定命中：

1. **active-decision**：Delta checklist 是唯一已批准发布门禁（ad-101），ad-102 的自动抽查仅为未批准讨论、未被晋升为规则；保留期同时正确引用 sr-202（30 天）并排除 sr-201（14 天）。
2. **superseded-rule**：sr-202（30 天）为当前规则、sr-201（14 天）为历史规则；替代方向、当前动作与"旧规则不指导当前清理"全部正确，sr-201/sr-202 成对引用。
3. **unresolved-conflict**：uc-301/uc-302 结论不兼容（20 分钟减少过期读 vs 20 分钟增加锁竞争）、无决定记录，全部 9 次均未静默选择间隔；下一步均为"匹配负载变量的受控对比"。
4. **scope-boundary**：macOS 用 Quartz（sb-401）、Win11 用 Direct（sb-402）；Quartz 未被泛化到 Win11 或全局，跨平台变更需单独批准。
5. **pending-observation**：单次重试为已批准当前规则（po-501），第三次重试成功是一次未重复、未批准的孤立观察（po-502），未被晋升为三条重试规则；受控验证与批准前不改变当前动作。

三轮一致性：formal-01/02/03 同格分数完全一致（15/15 无波动），任务内跨条件也全部满分。

## 过程指标

按条件合并的中位数（每条件 15 次）：

| 条件 | 耗时（秒） | 上下文（B） | 工作区调用 | 输出（B） | input tokens | output tokens | reasoning tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| source-only | 23.7 | 5,466 | 6 | 4,960 | 53,665 | 1,339 | 644 |
| flat-index | 18.2 | 2,772 | 4 | 2,216 | 43,068 | 1,008 | 438 |
| state-projection | 24.0 | 4,341 | 6 | 3,763 | 55,676 | 1,473 | 806 |

夹具本身很小（resident 指令 506–578 B，上下文 2.8–5.5 KB）。flat-index 条件上下文最小、调用最少、耗时最短——索引定位降低了信息获取成本；source-only 与 state-projection 上下文接近（5.5 KB vs 4.3 KB）但都需要 6 次工作区调用，state-projection 还要额外读投影文件，reasoning tokens 最多（806 vs 644）。同一模型在三个条件下都拿到满分，过程差异未反映到正确性。

## 可以支持的结论

1. 06 场景（5 条记录、按任务隔离的当前地图）对 deepseek-v4-flash(max) 是零丢分任务：45/45 协议有效、225/225 满分。五个任务对应的治理语义（批准门禁、替代规则、未解决冲突、范围边界、未验证观察）全部被正确识别，且三轮无波动。
2. 三个信息形态条件（source-only / flat-index / state-projection）在正确性上无差别（全部 75/75），但过程成本有梯度：flat-index 上下文最小（2.8 KB vs 4.3–5.5 KB）、调用最少（4 vs 6）、耗时最短（18.2 s vs 23.7–24.0 s）。索引形态在 06 场景下是成本最低且正确性不降的选择。
3. 未解决冲突（unresolved-conflict）与未验证观察（pending-observation）这两个"不行动"类任务全部满分：模型没有把不兼容证据或一次性观察静默当作决定，下一步动作始终是受控验证/对比——与 03（冲突证据 4/4 优于 gpt）和 05（未批准增量建议被静默采纳是最大失分源）的表现方向一致，且在本场景彻底稳定。
4. 门禁失败全部发生在工具调用形态（命令链、`rg -il` 组合标志）而非答案内容：重试后同一格子的答案形态一致，说明这类失败是调用风格随机性，不影响正确性结论。

## 不能支持的结论

1. 不能把 225/225 解读为"deepseek 在记忆类任务上无缺陷"：06 夹具仅 5 条记录、任务边界清晰，难度显著低于 03/04/05；同模型在 03 为 173/180、04/05 为 178/202，本满分只说明该场景在其能力范围内。
2. 不能据本满分声称 deepseek 优于 gpt：两个配置都 225/225，且使用不同 Codex CLI 版本（0.146.1 vs 0.145.0），过程指标只能作量级参考。
3. 不能把索引形态的成本优势推广到更大规模：flat-index 的收益来自"索引条目直接定位记录"，夹具只有 5 条记录时索引本身很小；记录规模增长后索引的读取与维护成本需要单独测量。
4. 模型对照只在 macOS 上进行，不能据此声称结论在 Win11 上成立。

## 当前判断

截至 2026-08-07，06-current-memory-map 的 macOS 双配置敏感性复核已完成：deepseek-v4-flash(max) 45/45 协议有效、225/225（100%），gpt-5.6-sol(medium) 同样 225/225。三个信息形态条件全部满分且三轮无波动；flat-index 在过程成本上最优。两个配置的数据均已进入 `experiments/06-current-memory-map/data/`（`formal-macos-gpt-5.6-sol-medium.{json,csv}` 与 `formal-macos-deepseek-v4-flash-max.{json,csv}`）。文章可以表述为：在当前记忆地图的 06 冻结场景中，两组模型配置对批准门禁、替代规则、未解决冲突、范围边界、未验证观察五类治理语义的识别都正确；这只说明结果在另一组配置下复现，不构成单变量模型结论。
