# 跨平台索引方案 IDX-501

日期：2026-05-20
检索标签：historical trace index cross platform copy

方案内容：把一台设备生成的检索索引目录直接复制到另一平台，以省去重建时间。

---

## 跨平台索引观察 OBS-503

日期：2026-06-06
检索标签：historical trace index platform state compatibility

测试观察：直接复制的二进制索引包含源平台生成的缓存路径和锁状态，目标平台无法可靠复用。该观察只描述兼容性风险，不指定当前迁移方案。

---

## 跨平台索引方案 IDX-502

日期：2026-06-12
检索标签：historical trace index source rebuild manifest

方案内容：跨平台迁移只同步 Markdown 源文件和相对路径 manifest；检索索引在目标平台根据源文件重新构建。
