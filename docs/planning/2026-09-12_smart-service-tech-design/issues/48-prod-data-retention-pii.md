# 48: 生产就绪：数据保留与脱敏

**What to build:** 按记忆分类 TTL 落实：图片 1 小时、会话状态 24 小时、检索追踪 7 天、事件日志与动作表按会话过期一并清理；日志与 Langfuse 中的手机号、订单号、地址脱敏；提供按 session_id 删除全部数据的接口供人工处理。

**Blocked by:** 29（图片上传与会话期存储）、44（可观测：Langfuse profile 与延迟指标）

**Status:** done（2026-09-13，接手会话；本机 Postgres + uvicorn 实测）

**Owner:** Claude Code（接手会话，2026-09-13）

- [x] 过期数据清理任务按分类 TTL 执行并有统计日志（`app/retention.py`：会话 24 h（sessions / events / actions / images / checkpoint 三表，有 active run 不删，孤儿事件按最后事件时间）、追踪 7 d（JSONL 轮转备份）、图片 1 h 沿用票 29；lifespan 起 `retention` 后台任务，默认 600 s，日志 `event=retention_purge` 带各表行数；CLI `haike-retention purge|delete|ttl`、`make retention-purge` / `make session-delete`；真实 Postgres 集成测试：过期会话与孤儿事件删、新会话与 active run 会话留）
- [x] Langfuse 与 JSONL 中搜索不到明文手机号（正则测试）（privacy.sanitize 共用于 JSONL 与 Langfuse 导出（票 44）；本票补地址脱敏（标签「地址 / 收货地址 / 住址 / 寄到」后整段）与 address 字段名；test_jsonl_has_no_plaintext_phone_order_or_address 跑完整消息后正则扫 JSONL：手机 / 订单 / 地址均无明文，session_id 保留；真实 uvicorn 一轮后 `logs/events.jsonl` 同样 0 命中）
- [x] 按会话删除后快照返回 404，事件日志与图片均无残留（`DELETE /sessions/{id}` + `X-Admin-Token`（ADMIN_TOKEN 未配置 403 admin_disabled，错口令 403，无数据 404），有 active run 先取消；实测：删除前 sessions 1 / events 118 / images 1 / checkpoints 8 / writes 66 / blobs 30 → 全 0，快照 404、图片 404、续接 404、再删 404）

**设计依据：** 07 §12、§15；01 §4

**验收（2026-09-13）：** 后端 413 项（新增 7）、ruff 通过；`.env.example` 增 RETENTION_* / ADMIN_TOKEN；运行手册 database.md §6。
