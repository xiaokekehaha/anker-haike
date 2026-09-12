# 23: 版本冲突 409 与前端重建

**What to build:** expected_version 不符、interrupt_id / card_id 过期、kind 不在允许时机三种情况返回 409 并附最新快照；前端据快照重建状态；error 事件的 retry_with_same_action 决定是否复用 action_id 重试。卡片事件按 card_id 幂等更新。

**Blocked by:** 22（动作幂等与会话锁）

**Status:** ready-for-agent

- [ ] 三种 409 各有错误码 stale_version / stale_card / not_allowed_now，响应体含快照
- [ ] 前端收到 409 后 UI 与快照一致，不出现重复卡片
- [ ] interrupt 重跑导致的重复 step_card 在前端只显示一张
- [ ] recoverable + retry_with_same_action 时前端自动复用 action_id 重试一次

**设计依据：** 08 §4 步骤 3；05 §2
