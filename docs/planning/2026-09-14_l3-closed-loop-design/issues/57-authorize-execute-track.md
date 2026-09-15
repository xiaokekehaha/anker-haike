# 57: authorize / execute / track 节点、ExecutionCard 与案件创建

**What to build:** `authorize` 节点调 `gate.check`，pass → `execute`，fail → `await_human`（票 60 前落 summarize 并把 checks 进摘要）；`execute` 节点：`executor.run(replacement.create, …, idempotency_key=f"{case_id}:replacement.create:{option_id}")`，成功 → `execution_card` + `CaseService.attach_execution` → case tracking；失败可恢复 → 固定文案 + 人工选项；`track` 节点：读 `get_service_order`，生成用户可见进度句（模板），首次执行后发 `rating_card`（可稍后）。`Stage` 推进 propose → execute → track。案件在 `service_context` 首次进入时 `CaseService.open()`（依赖票 59；先以最小 CaseService 桩落库）。

**Blocked by:** 53, 56, 59

**Status:** todo

**Owner:** —

- [ ] A5 全链 API → SSE → 快照：proposal_card → confirm → tool_call started/finished → execution_card(service_order_no) → case_changed(tracking) → rating_card
- [ ] 中断后重跑同 run：后端只创建一次服务单，回执一致
- [ ] gate fail 时零后端调用（假后端计数）；checks 出现在摘要
- [ ] 故障注入 timeout：用户可见「稍后重试 / 转人工」，case 状态 executing_failed，可重试
- [ ] 前端 `ExecutionCard.tsx`：单号、状态、下一步、幂等键折叠显示

**设计依据：** 02 §2.1、§3；03 §3–§4、§7；05 §2
