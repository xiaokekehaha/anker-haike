# 22: 动作幂等与会话锁

**What to build:** 动作请求带前端生成的 action_id；服务端用 session_actions 表去重，重复请求返回已记录结果并重放事件流（replayed=true）；同会话用 PostgreSQL advisory lock 串行，锁超时 30 s。

**Blocked by:** 07（快照接口与 sessions 投影表）、20（三段式等待节点与 /actions 基本通路）

**Status:** done（2026-09-12；A 完成主体，A 停止后由接手会话收尾提交）

- [x] 同一 action_id 连点两次，第二次返回 200 且 replayed=true，业务状态只推进一次（顺序与并发两种连点；响应头 X-Action-Replayed / X-Run-Id，事件流逐条相同；prepare_card_calls 仍为 1、只多一个 run；重启后仍可按占位里的 run_id 重放）
- [x] 两个不同动作并发到达同一会话时串行执行（第二个等第一个 run 结束后才校验，拿到 409 而非 run_active；锁持有到 run 结束由后台回填任务释放）
- [x] session_actions 占位 → 执行 → 回填三步有测试（run 进行中记录 status=pending 带 run_id 且 active_run_id 相同；结束后 status=done、version_after=done.version；Postgres 表与内存实现各有测试）
- [x] 锁超时返回可重试 error（503 + Retry-After，体 {code: lock_timeout, recoverable: true, retry_with_same_action: true}；Postgres advisory lock 跨连接超时实测）

**设计依据：** 08 §4 步骤 1–2、5；07 §5

**实现记录（2026-09-12，Claude Code A）：** `app/sessions/locks.py`（PostgresSessionLock：独占一条池连接 pg_try_advisory_lock(hashtext(session_id)) 轮询到超时；InMemorySessionLock 供测试）；store 新增 session_actions 表与 try_insert_action / get_action / set_action_result；router /actions 顺序：锁 → 去重重放 → 校验 → manager.start → 占位 → 后台 `_finish_action` 等 run 结束回填并释放锁；重放 / 409 / 异常路径在 finally 释放。测试 tests/test_sessions_idempotency.py 8 项 + pg 表与 advisory lock 1 项。

**给前端（票 23 / Codex）：** 重放响应仍是 SSE（同一 run 的全部事件），用响应头 `X-Action-Replayed` 判断是否重放；`X-Action-Id` / `X-Run-Id` 一并返回。503 lock_timeout 时按 body 的 retry_with_same_action 复用 action_id 重试。

**与设计的差异：** 08 §4 写「锁超时 30 s」，实现为可配置常量（默认 30 s）。锁在 run 期间一直持有（同会话动作串行到 run 结束），因此第二个动作的等待时间上限 = 前一 run 的 deadline（25–40 s）≈ 锁超时，需在票 23 / 45 巡检里确认前端体验；POST /messages 未加锁，仍由 active_run 守卫直接 409。
