# 12: 限流退避与全局有界队列

**What to build:** 429 采用 1 / 2 / 4 s 加抖动的指数退避；全局并发队列上限 50，满时立即返回 recoverable error 让用户稍后重试而不是堆积。

**Blocked by:** 11（降级链与 task 预算）

**Status:** done（2026-09-12）

**Owner:** Claude Code B（模型层线）

- [x] 并发压测下队列满时请求快速失败，返回 error(recoverable=true)（`app/models/queue.py` BoundedGate：上限 `concurrency.max_in_flight`=50，满即抛 `CapacityExceeded`，`as_error_fields()` 给出 code=model_capacity_exceeded / recoverable=true / retry_with_same_action=true；单测 8 并发 × 上限 5：3 个 50 ms 内被拒，5 个放行后成功，门归零后新请求可进）
- [x] 退避时间与抖动范围有单元测试（`backoff_seconds`：429 按 1 / 2 / 4 s，其余 1 s，抖动 [0, 0.5)；429 同模型最多 `retry.rate_limit_max`=3 次且受预算约束，测试断言 sleeps == [1, 2, 4] 与预算 4.5 s 时在第二次退避后停止）
- [x] 队列长度、拒绝次数有结构化日志（logger `models.queue`，`extra` 含 event / task / in_flight / limit / peak / admitted_total / rejected_total；`snapshot()` 供票 44 指标）

**设计依据：** 07 §13；04 §1

**实现记录（2026-09-12，Claude Code B）：** `app/models/queue.py`（BoundedGate / CapacityExceeded）；`router.py` 的 `invoke` 外层加 `gate.slot(task)`，429 走 `rate_limit_max`；`config.py` 新增 `retry.rate_limit_max`、`concurrency.max_in_flight`（models.yaml 已写入）；`tests/test_models_queue.py` 7 项。会话层（票 05 / 13）收到 `CapacityExceeded` 时按 `as_error_fields()` 发 error → done(reason=error)。
