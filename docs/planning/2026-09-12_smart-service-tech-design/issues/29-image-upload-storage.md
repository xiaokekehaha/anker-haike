# 29: 图片上传与会话期存储

**What to build:** Composer 支持选图并在前端压缩到长边 1600 px，multipart 带 purpose=fault；后端拒绝 > 5 MB，写入 session_images（bytea + sha256），状态只存引用；1 小时定时清理。UserBubble 显示缩略图。

**Blocked by:** 21（产品确认卡片 ProductCard 端到端（A2 前半））

**Status:** ready-for-agent

- [ ] 上传 6 MB 图片被拒绝且在 Composer 内联提示，不进入对话流
- [ ] image_refs 出现在状态与快照，含 purpose 与 sha256
- [ ] 清理任务删除 1 小时前的图片并有日志
- [ ] 编排服务本地磁盘无图片文件

**设计依据：** 03 §3.1；04 §1；07 §9；05 §6
