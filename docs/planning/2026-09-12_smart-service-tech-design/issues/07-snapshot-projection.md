# 07: 快照接口与 sessions 投影表

**What to build:** 提供会话权威快照接口：从 checkpoint 与事件日志派生 version、stage、active_run、pending_input，并把事件日志折叠成 timeline。sessions 投影表可丢弃后重建。

**Blocked by:** 05（会话创建与 SSE 基础流）

**Status:** done（2026-09-12）

- [x] 快照字段与契约 §6 一致（响应模型直接用 haike_contracts.SessionSnapshot；version = 最新 checkpoint step + 1）
- [x] timeline 由事件日志按 seq 重放折叠：消息合并为完整文本、卡片带用户已选结果、工具行保留（snapshot.fold_timeline；message_start(replaces) 替换旧消息；卡片按 card_id 幂等；用户已选结果读 checkpoint 状态 card_results）
- [x] 删除投影表后调用重建命令，快照结果与删除前一致（`make sessions-rebuild ARGS="<id>|--all"`；真实 Postgres 实测删行 → 快照字节一致 → 重建后行与快照一致）
- [x] 业务逻辑不直接读投影表（代码审查项：snapshot.py 只读 session_events 与 graph.aget_state；投影表仅用作 active_run 并发守卫与存在性判断，且存在性同时看事件日志）

**设计依据：** 08 §2、§6

**实现记录（2026-09-12，Claude Code A）：** `app/sessions/snapshot.py`（build_snapshot / fold_timeline / rebuild_projection）、`app/sessions/cli.py`（haike-sessions-rebuild）、router 新增 `GET /sessions/{id}`，409 run_active 响应体改为完整快照。store 新增 list_event_records / list_session_ids / upsert_projection / delete_projection / session_exists；session_events 去掉对 sessions 的外键（否则删投影会级联删日志），DDL 里 drop constraint 兼容已建库。runner 的 done.version 与投影 version 统一改为 checkpoint 推导，票 05 的「每 run +1」随之退役。图状态新增 run_id / at / card_results 字段：用户消息按 run 归入 timeline，卡片结果留给票 20/21 的 apply_action 写入。测试：test_sessions_snapshot.py 7 项 + pg 重建 1 项。

**与设计的差异：** 08 §6 timeline 含用户消息，但事件协议无 user_message 类型，用户消息取自 checkpoint 状态 messages（带 run_id）；active_run.started_at 取 run_started 事件的 created_at。仅创建未发消息的会话既无事件也无 checkpoint，投影行被删后无法重建（也无内容可恢复）。
