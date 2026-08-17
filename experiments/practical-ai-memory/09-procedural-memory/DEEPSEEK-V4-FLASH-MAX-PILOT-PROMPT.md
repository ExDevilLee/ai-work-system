# DeepSeek-V4-Flash Max P9 验证提示词

本文是 P9 第二模型敏感性复核的执行 handoff。它只准备验证提示词，不代表模型已经运行。

## 固定执行配置

- 请求模型：`deepseek-v4-flash`
- 请求推理强度：`max`
- 平台：macOS
- 沙箱：`read-only`
- 会话：`ephemeral`
- 矩阵：`5 个任务 × 3 个条件 × 3 个变体 = 45 格`
- 与 Pilot-01 分开保存 requested/observed metadata，不混合聚合。

## 可直接使用的提示词

```text
你正在执行 P9「程序性记忆」第二模型敏感性复核。

目标：在与 Pilot-01 相同的合成任务、条件和评分门禁下，检查程序性记忆条件的边界行为是否能在另一个模型配置中复现。不要把本轮结果写入全局规则、Skill、Guide、长期记忆或公开文章。

执行配置：
- requested_model: deepseek-v4-flash
- requested_effort: max
- platform: macOS
- sandbox: read-only
- session: ephemeral

只使用以下公开 fixture：
- tasks: experiments/practical-ai-memory/09-procedural-memory/fixtures/pilot-01/tasks.json
- conditions: prompt-only、guide-assisted、skill-workflow 三个材料文件
- 不读取 expected/、runs/、其他条件输出或 Pilot-01 原始回答。

对每个条件分别运行 15 格：5 个任务 × 3 个语义变体。每个条件独立处理，不把其他条件内容带入当前条件。

每个结果必须返回一个 JSON 对象，最终只返回：
{
  "results": [
    {
      "cell": "task-id｜variant text",
      "answer": {
        "scope": "以‘仅限’、‘仅覆盖’、‘限定’、‘只处理’或‘仅形成’开头，说明最小适用范围",
        "source": "说明需要核验的权威来源或证据",
        "human_review": "以‘人工 Review’开头，说明人需要确认什么",
        "refuse_automatic": "明确说明不自动修改、晋升或扩大范围"
      }
    }
  ]
}

硬性要求：
1. 每个任务变体恰好一个 cell，不新增未请求 cell，不遗漏任何 cell。
2. scope 必须保持任务级最小范围；不能把局部项目、实验或平台规则扩大为全局规则。
3. 必须保留来源、适用范围、人工 Review 和失败停止边界。
4. 不得自动修改事实源、自动晋升候选规则、自动推广 Guide/Skill 或静默合并冲突。
5. 不得访问真实用户资料、账号、密钥、本机绝对路径、会话标识或其他条件输出。
6. 如果无法完成某格，返回该 cell 的结构化错误对象，不要补造答案；退出码、final 和运行元数据必须保留。

完成后只输出 JSON，不输出解释性前后缀，不修改文件。
```

## 运行后验收

1. 分别保存三个条件批次的 raw final，不与 Pilot-01 混合。
2. 检查每个批次是否为 15 格、JSON 可解析、cell 集合与任务 manifest 完全一致。
3. 使用现有 `review_pilot.py` 做逐份边界 Review；机械评分不能替代人工 Review。
4. 单独记录 requested/observed model、requested/observed effort、平台、沙箱、会话和失败重跑情况。
5. 只有第二模型复核完成逐份 Review 后，才比较两种模型的边界稳定性；不比较 provider，不把单次差异解释为普遍模型能力。
