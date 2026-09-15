# 85: 多副本运行协调（扩容前 P0）

**What to build:** `manager.subscribe` / cancel / 孤儿 run 收尾跨实例化：run 归属表（`run_owners`：run_id、instance_id、heartbeat），SSE 订阅在非归属实例时通过 PG LISTEN/NOTIFY 或 Redis pub/sub 转发事件；取消请求路由到归属实例（或写取消标记由归属实例轮询）；心跳超时判孤儿并由任一实例收尾；会话锁改为 PG advisory lock；健康检查含 instance_id；Compose 增 `orchestrator` 2 副本 + 负载均衡演练。

**Blocked by:** P0 66；部署计划包含多副本时提升为发布前 P0

**Status:** todo

**Owner:** —

- [ ] 双副本下：A 实例跑 run，B 实例订阅 SSE 收到全部事件；B 发起取消生效
- [ ] 杀掉归属实例 → 另一实例在心跳超时内收尾孤儿 run，前端可恢复
- [ ] 单副本行为不变（回归）

**设计依据：** weknora-design-lessons §1「多副本运行协调」
