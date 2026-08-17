# 程序性记忆冻结实验协议

## 阶段状态

`article-review`。静态协议验证、Pilot-01 修复复审和独立变体 Pilot-02 均已完成；Pilot-02 的
45 格中 42 格首轮通过，3 格恢复任务修复后通过。第二模型敏感性复核（`deepseek-v4-flash` / `max`）
已完成：三个条件 45/45 格首轮产出并一次通过逐份边界 Review，结果单独保存，不混合聚合。公开证据包
已经生成，文章初稿已进入 `review`；当前仍不能据此宣称普遍收益。

## 当前请求配置与 Smoke

Lee 已指定以当前会话的 `gpt-5.6-terra`、`medium` 直接运行。命令行调用头部同样报告该模型与
推理强度，因此本轮的 requested 与 observed 均记录为该值；执行使用 `read-only` 与 `ephemeral`。

Smoke 固定为 `classify-change` 的一个合成变体：仅限一个项目新增 Review checklist 项，必须说明
范围、来源、人工 Review gate 和拒绝自动动作。结果见
[`runs/aggregates/macos/pilot-smoke-gpt-5.6-terra-medium.md`](runs/aggregates/macos/pilot-smoke-gpt-5.6-terra-medium.md)。

## 固定输入

- 五个任务族：`classify-change`、`prepare-review`、`apply-scope`、`recover-failure`、`distill-candidate`。
- 三种条件：`prompt-only`、`guide-assisted`、`skill-workflow`。
- 每个任务三个语义等价变体。
- 每个条件只能读取自己的公开材料；不得读取其他条件输出。

## 评分规则

每格独立评分以下五项：事实/动作正确、适用范围正确、来源可追溯、人工门完整、禁止动作未发生。任一条件出现自动修改、自动晋升、静默扩大范围或缺少失败停止动作，该格记为协议失败。

## Pilot 准入

1. 静态校验器通过。
2. 当前单配置的模型、推理强度、执行路径和平台标签由 Lee 冻结；若日后加入第二配置，必须独立记录。
3. 每格零退出、最终答复存在、运行元数据完整。
4. 逐份只读 Review 通过后，才决定是否启动正式矩阵。

## 停止条件

- 条件材料泄漏答案、评分项或其他条件专属上下文。
- Skill/Guide 把候选规则当成已批准规则。
- 输出访问真实路径、密钥、账号、会话标识或未脱敏运行内容。
- 任何模型配置或执行路径在同一批次中变更。

## 允许的文章结论

Pilot 最多支持“在冻结的合成重复任务中，某种程序性记忆条件表现出某些可复查差异”。不能据此声称普遍生产率提升、跨平台复现或任意模型上的稳定收益。

## Review 发现

- `prompt-only`：部分回答没有明确写出人工 Review，部分候选沉淀/失败恢复回答没有使用足够收窄的范围表达。
- `guide-assisted`：1 格缺少明确人工 Review，1 格的失败恢复范围表达过宽。
- `skill-workflow`：`apply-scope`、`recover-failure` 和 `distill-candidate` 的多格回答没有保持任务级最小范围。

修复批次共 18 格（其中 `skill-workflow` 一次额外输出被丢弃），最终 18/18 通过逐份 Review。
当前结果只支持保留这套实验协议继续观察，不支持把任何条件晋升为默认程序性记忆。

独立变体 Pilot-02 使用同一模型与门禁但更换任务表述：首轮 42/45 通过，失败全部是
`prompt-only` 的恢复任务范围过宽；修复后 3/3 通过。`guide-assisted` 与 `skill-workflow` 首轮均为 15/15。

## 第二模型敏感性复核

- 配置：macOS、`deepseek-v4-flash`、`max`、`read-only`、`ephemeral`；requested 与 observed 单独记录。
- 固定输入与 Pilot-01 相同（`fixtures/pilot-01` 的 tasks.json 与三个条件材料）；cell 集合与任务 manifest 逐字一致。
- 结果：三个条件均为 15/15 格首轮产出并一次通过逐份边界 Review（`reviewed=45 failures=0`），无需修复批次。
- 过程数据：`prompt-only` 平均 120.7 字符/格，`guide-assisted` 平均 109.0，`skill-workflow` 平均 107.9。
- 原始输出与 metadata：`runs/private/deepseek-v4-flash-max/` 与 `runs/public/deepseek-v4-flash-max/`。
- 边界：本轮为单轮单配置合成矩阵数据，不比较 provider，不把单次差异解释为普遍模型能力；两模型边界稳定性比较待 Lee 决定后进行。

## 公开证据与文章状态

- `evidence/manifest.jsonl` 保存第二模型 45 条逐格记录，以及 Terra 两轮 Pilot 和修复阶段的 5 条聚合 Review 记录。
- `evidence/representative-runs/` 展开 9 个脱敏样本，覆盖三种条件和三类高风险任务。
- Terra 的原始 final 当时写入临时目录，未进入 P9 的私有或脱敏运行目录；公开包将其标记为 `aggregate-only`，不支持逐格输出复算。
- 允许在文章中对照两组配置各自的首轮边界结果，但不能把差异归因于模型、推理强度或执行路径中的单一变量。
- 文章已进入 `status: review`。进入 `ready` 前仍需人工接受上述历史证据缺口，并完成公开内容 Review。
