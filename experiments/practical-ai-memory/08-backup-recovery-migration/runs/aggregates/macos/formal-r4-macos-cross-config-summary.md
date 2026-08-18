# P8 双配置正式矩阵汇总

## 总结果

两个 macOS 请求配置共完成 108 次正式尝试，最终为 **99/108 通过**。

| 请求配置 | 通过 | 失败 | 语义失败 | deadline | 主线程中断 |
| --- | ---: | ---: | ---: | ---: | ---: |
| GLM-5.2 / max | 52 | 2 | 1 | 1 | 0 |
| DeepSeek-V4-Flash / max | 47 | 7 | 1 | 5 | 1 |
| 合计 | 99 | 9 | 2 | 6 | 1 |

响应侧不能独立确认实际模型和推理强度，因此这里描述的是请求配置结果，不是观察到的模型身份。

## 按任务汇总

| 任务 | 通过 | 总数 |
| --- | ---: | ---: |
| `clean-restore` | 17 | 18 |
| `partial-backup` | 15 | 18 |
| `integrity-mismatch` | 16 | 18 |
| `target-divergence` | 17 | 18 |
| `derived-index` | 18 | 18 |
| `rollback-receipt` | 16 | 18 |

## 按条件汇总

| 条件 | 通过 | 总数 |
| --- | ---: | ---: |
| `source-only` | 34 | 36 |
| `backup-inventory` | 31 | 36 |
| `recovery-gated-bundle` | 34 | 36 |

第二轮为 36/36；第一轮为 35/36；第三轮为 28/36。第三轮同时出现两个真实语义失败、多个
deadline 和一个主线程中断，因此不能把总失败简单归因于恢复门禁本身。

## 正式化发现

- r3 运行发现 integrity report 与 backup manifest 对同一 `source_manifest_sha256` 使用不同哈希
  语义；r4 已统一为源清单真实文件哈希，并增加 validator 与回归测试。
- 旧 Pilot 的否定关键词 scorer 会误判 Forbidden 段。正式 scorer 改为任务正向硬门禁、
  condition-aware 证据检查和全量只读 Review 三层组合。
- 两个真实语义失败都发生在“条件材料不足但任务描述暗示事实存在”的场景：一次无 receipt 却
  声称 receipt failed，一次无 backup hash 却把 source 自哈希推进为恢复资格。这支持文章强调
  “显式门禁仍需证据可见性检查和失败样本保留”。

## 文章口径

第八篇可以从“双 Pilot”升级为“双配置 macOS 正式矩阵”，但必须写明 **99/108**，并分别披露
2 个语义失败、6 个 deadline 和 1 个主线程中断。不得写成全部通过、真实备份可靠性、跨平台复现
或模型优劣比较。
