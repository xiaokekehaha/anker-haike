# 22: 动作幂等与会话锁

**What to build:** 动作请求带前端生成的 action_id；服务端用 session_actions 表去重，重复请求返回已记录结果并重放事件流（replayed=true）；同会话用 PostgreSQL advisory lock 串行，锁超时 30 s。

**Blocked by:** 07（快照接口与 sessions 投影表）、20（三段式等待节点与 /actions 基本通路）

**Status:** done（2026-09-12；A 完成主体，A 停止后由接手会话收尾提交）

- [x] 同一 action_id 连点两次，第二次返回 200 且 replayed=true，业务状态只推进一次（顺序与并发两种连点；响应头 X-Action-Replayed / X-Run-Id，事件流逐条相同；prepare_card_calls 仍为 1、只多一个 run；重启后仍可按占位里的 run_id 重放）
- [x] 两个不同动作并发到达同一会话时串行执行（第二个等第一个 run 结束后才校验，拿到 409 而非 run_active；锁持有到 run 结束由后台回填任务释放）
- [x] session_actions 占位 → 执行 → 回填三步有测试（run 进行中记录 status=pending 带 run_id 且 active_run_id 相同；结束后 status=done、version_after=done.version；Postgres 表与内存实现各有测试）
- [x] 锁超时返回可重试 error（503 + Retry-After，体 {code: lock_timeout, recoverable: true, retry_with_same_action: true}；Postgres advisory lock 跨连接超时实测）

**设计依据：** 08 §4 步骤 1–2、5；07 §5
