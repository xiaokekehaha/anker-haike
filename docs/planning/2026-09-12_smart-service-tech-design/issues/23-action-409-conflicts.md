# 23: 版本冲突 409 与前端重建

**What to build:** expected_version 不符、interrupt_id / card_id 过期、kind 不在允许时机三种情况返回 409 并附最新快照；前端据快照重建状态；error 事件的 retry_with_same_action 决定是否复用 action_id 重试。卡片事件按 card_id 幂等更新。

**Blocked by:** 22（动作幂等与会话锁）

**Status:** backend-done（2026-09-12；前端三项依赖票 06 reducer，留给 Codex 在 06 之后接入）

- [x] 三种 409 各有错误码 stale_version / stale_card / not_allowed_now，响应体含快照（校验顺序按 08 §4：run_active → 全局 kind 分流 → version → pending 存在 → card/interrupt → kind 允许时机；契约 ActionConflict.code 由 version_mismatch 改为 stale_version 并重生成 Schema / TS）
- [ ] 前端收到 409 后 UI 与快照一致，不出现重复卡片（后端侧：409 体内快照按 card_id 折叠、卡片带 selected_sku，有测试；前端 reducer 待票 06）
- [ ] interrupt 重跑导致的重复 step_card 在前端只显示一张（后端侧：重发同 card_id，快照折叠成一张，票 20 已验证；前端 reducer 待票 06）
- [ ] recoverable + retry_with_same_action 时前端自动复用 action_id 重试一次（后端侧已就位：动作 run 的 node_failed / deadline_exceeded 带 recoverable=true、retry_with_same_action=true，占位撤销；原样重发同一 action_id 时服务端识别「动作已接收、apply_action 未成功」并从该节点继续，不校 version；取消的动作 run 同理。前端自动重试待票 06）

**设计依据：** 08 §4 步骤 3；05 §2
