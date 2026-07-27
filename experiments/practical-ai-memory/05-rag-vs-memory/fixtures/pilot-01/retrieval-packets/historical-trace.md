# 跨平台索引复制旧做法

日期：2026-05-20
检索标签：historical trace derived index cross platform copy

旧做法曾把一台设备生成的检索索引目录直接复制到另一平台，希望省去重建时间。后续发现派生索引包含平台相关状态，不再适合作为当前迁移动作。

---

## 跨平台索引迁移决定

日期：2026-06-12
检索标签：historical trace derived index source rebuild decision

正式决定：跨平台迁移只同步 Markdown 源文件和相对路径 manifest；检索索引作为派生产物，在目标平台根据源文件重新构建。旧的二进制索引复制做法只保留为历史记录，不再指导当前迁移。
