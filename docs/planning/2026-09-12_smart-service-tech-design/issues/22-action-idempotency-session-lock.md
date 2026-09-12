# 22: 动作幂等与会话锁

**What to build:** 动作请求带前端生成的 action_id；服务端用 session_actions 表去重，重复请求返回已记录结果并重放事件流（replayed=true）；同会话用 PostgreSQL advisory lock 串行，锁超时 30 s。

**Blocked by:** 07（快照接口与 sessions 投影表）、20（三段式等待节点与 /actions 基本通路）

**Status:** ready-for-agent

- [ ] 同一 action_id 连点两次，第二次返回 200 且 replayed=true，业务状态只推进一次
- [ ] 两个不同动作并发到达同一会话时串行执行
- [ ] session_actions 占位 → 执行 → 回填三步有测试
- [ ] 锁超时返回可重试 error

**设计依据：** 08 §4 步骤 1–2、5；07 §5
