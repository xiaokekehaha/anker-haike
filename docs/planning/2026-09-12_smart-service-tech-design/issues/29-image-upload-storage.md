# 29: 图片上传与会话期存储

**What to build:** Composer 支持选图并在前端压缩到长边 1600 px，multipart 带 purpose=fault；后端拒绝 > 5 MB，写入 session_images（bytea + sha256），状态只存引用；1 小时定时清理。UserBubble 显示缩略图。

**Blocked by:** 21（产品确认卡片 ProductCard 端到端（A2 前半））

**Status:** done（2026-09-12；B 完成后端与前端组件，A 线接手会话收尾：迁移 0002、真实链路手测、票面）

**Owner:** Claude Code B（2026-09-12 认领；后端 `orchestrator/app/images/`、/messages 多部分图片；前端 Composer 选图压缩与 UserBubble 缩略图（Codex 已停，B 接手））

- [x] 上传 6 MB 图片被拒绝且在 Composer 内联提示，不进入对话流（前端 prepareImage 压缩后校验，role=alert 内联提示且不进入 onSend；后端 413 too_large / 415 unsupported_type，不产生 run、事件日志为空；uvicorn + Postgres 实测 6 MB PNG → 413、PDF → 415、timeline 为空）
- [x] image_refs 出现在状态与快照，含 purpose 与 sha256（intake 写 image_refs{image_id, purpose, sha256, mime, size, run_id}；快照 user_message.images 同结构；契约 ImageRefItem 已进 snapshot Schema 与前端类型；GET /sessions/{id}/images/{image_id} 只按会话取，跨会话 404）
- [x] 清理任务删除 1 小时前的图片并有日志（启动时 image-cleanup 任务每 300 s 跑一次，retention 1 h；日志 event=image_cleanup removed=N；内存与 Postgres 实现各有测试）
- [x] 编排服务本地磁盘无图片文件（字节只进 session_images bytea；测试扫描 orchestrator 目录无图片产物；手测后 find 无新图片文件；表结构由迁移 0002_session_images 管理）

**设计依据：** 03 §3.1；04 §1；07 §9；05 §6

**收尾说明（A 线接手会话）：** 票 47 之后业务表以 migrations/ 为准，补 `0002_session_images`（IF NOT EXISTS 收编 store.setup 建好的表），test_db_migrations 的 head 改为 0002 并加迁移与 ImageStore DDL 一致性测试。前端 Composer 的 onSend / UserBubble 尚未接到 App（聊天仍 offline），随票 06 reducer 接入；接口形状已定：onSend(text, files, purpose)。

**实现记录（2026-09-12，Claude Code B）：** 后端 `orchestrator/app/images/`（store.py：校验 / 嗅探 mime / PostgresImageStore / InMemoryImageStore；runtime.py：进程级 store 与清理循环）、router.py post_message 追加 images / purpose、graph.py intake 解析引用、snapshot.py 折叠 images；`tests/test_images.py` 7 项（含真实 Postgres 表）。前端 `frontend/src/lib/image.ts`（checkImage / compressImage 长边 1600 canvas / prepareImage）、`Composer.tsx`（隐藏 file input、附件预览、移除、内联错误、onSend(text, files, purpose)）、`UserBubble.tsx`（缩略图）；`Composer.test.tsx` 7 项，typecheck / build 通过。

**说明：** 前端 App 仍是票 02 的只读壳（`CHAT_OFFLINE = true`），票 06 的 reducer / SSE 客户端未接入 App；Composer 的 onSend 与 UserBubble 已按 /messages 多部分接口就位，接线属票 06 / 21 前端集成范围（Codex 已停，待另行安排）。
