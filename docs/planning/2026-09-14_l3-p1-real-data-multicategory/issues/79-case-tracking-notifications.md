# 79: 案件跟踪状态回写与主动告知

**What to build:** 模拟后端状态推进入口（`haike-backends advance <service_order_no|tracking_no> --to <status>` 与 admin 页按钮，演示用）；`CaseService.sync_external()`：会话恢复 / 新 run 开始时读取外部状态，变化则写 case_events 并在首条可见消息前追加确定性告知句（「您的换货单已发出，单号 …」）；终态（delivered / completed）→ 询问是否解决 → RatingCard → 结案；`confirm_received` 意图直接结案；超时未变化（配置天数）→ case 标 `stalled` 进 HITL 队列。不做推送渠道（无外部通知通道）。

**Blocked by:** P0 57, 59, 60

**Status:** todo

**Owner:** —

- [ ] 推进状态后用户下一条消息收到告知句；case_events 有记录
- [ ] delivered → 用户「收到了」→ closed；「没收到」→ reopened + HITL
- [ ] stalled 判定单测（可配置阈值）

**设计依据：** 05 §2 结案条件；02 §2.1 track
