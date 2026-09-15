# 84: 案件级定时与长流程（本地调度器 / Step Functions）

**What to build:** 案件级定时任务：外部状态轮询（P1 79 的 sync 由「用户回来时」改为「定时」）、审批超时提醒（awaiting_approval > N 小时 → 队列升级 priority）、stalled 判定、评分催评一次；实现 A：进程内 APScheduler / asyncio 定时 + PG 任务表（`case_timers`），幂等、单副本；实现 B（aws 通道成立时）：Step Functions 状态机 + EventBridge 定时，回调编排服务 HTTP；两者共用 `CaseTimerService` 接口。

**Blocked by:** P1 79；85（多副本时定时器需去重）

**Status:** todo

**Owner:** —

- [ ] 定时触发写 case_events，用户下次进入看到告知；重复触发幂等
- [ ] 审批超时 → priority high；stalled → HITL 队列
- [ ] 实现 B 仅在 D-L3-2 成立时做，含最小状态机定义与回调鉴权

**设计依据：** 02 §4；00 D-L3-4；05 §2
