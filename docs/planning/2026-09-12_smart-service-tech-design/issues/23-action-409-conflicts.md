# 23: 版本冲突 409 与前端重建

**What to build:** expected_version 不符、interrupt_id / card_id 过期、kind 不在允许时机三种情况返回 409 并附最新快照；前端据快照重建状态；error 事件的 retry_with_same_action 决定是否复用 action_id 重试。卡片事件按 card_id 幂等更新。

**Blocked by:** 22（动作幂等与会话锁）

**Status:** done（2026-09-12 原始验收；2026-09-13 票 37 纠错联动验收补齐；余下两项为 2026-09-12 已有测试覆盖的复述，见下）

- [x] 三种 409 各有错误码 stale_version / stale_card / not_allowed_now，响应体含快照（校验顺序按 08 §4：run_active → 全局 kind 分流 → version → pending 存在 → card/interrupt → kind 允许时机；契约 ActionConflict.code 由 version_mismatch 改为 stale_version 并重生成 Schema / TS）
- [x] 前端收到 409 后 UI 与快照一致，不出现重复卡片（后端侧：409 体内快照按 card_id 折叠、卡片带 selected_sku，有测试；前端 reducer/useSession 回归通过）
- [x] interrupt 重跑导致的重复 step_card 在前端只显示一张（后端侧：重发同 card_id，快照折叠成一张，票 20 已验证；前端 reducer/useSession 回归通过）
- [x] recoverable + retry_with_same_action 时前端自动复用 action_id 重试一次（后端侧已就位：动作 run 的 node_failed / deadline_exceeded 带 recoverable=true、retry_with_same_action=true，占位撤销；原样重发同一 action_id 时服务端识别「动作已接收、apply_action 未成功」并从该节点继续，不校 version；取消的动作 run 同理。前端已实现同一请求体与 action_id 最多重试一次，成功/失败/不允许重试均有测试）

**追加验收（2026-09-12，待联动验证，不改变上述已完成项）：**

- [x] 未知 kind / 非法 payload 返回 422，阶段不允许 / 过期卡片返回相应 409 与快照；没有任何模型调用、游标推进或业务计数增加（test_sessions_actions::test_action_conflicts_and_validation、test_sessions_conflicts；票 37 补：rediagnose 空载荷 / 未知 image_ids 422、阶段不允许 409，均不产生 run；test_product_correction_… 断言 409 后 counters 不变）
- [x] 路由表测试验证合法 step_feedback(not_solved) → verify、request_human → escalate；端到端验证实际结果，不能仅测试枚举名称（test_guide::test_not_solved_advances_to_next_step_and_counts 断言 cp_verify 计数与下一张卡；test_sessions_human 断言 request_human → R3 摘要与 done；均为端到端事件流）
- [x] 纠正产品后的旧卡点击与刷新恢复同样遵守版本 / 卡片校验，前端不自动把旧动作改发给新卡（联动票 37：test_product_correction_goes_through_disambiguate_and_invalidates_old_card——旧版本 stale_version、版本对但卡旧 stale_card，均附快照且 counters 不变；前端 useSession.act 只在服务端明确 retry_with_same_action 时原样重试一次，不改发新卡）

**设计依据：** 08 §4 步骤 3 与动作失败边界；09 §1.1；05 §2

**前端接续（Codex，2026-09-12）：** 409 使用随响应返回的权威快照，存在 active_run 时立即续接；旧 action 不改发到新卡。事件按 seq 去重，重发卡片保留用户结果；动作快速连点仅提交一次。自动重试要求当前动作收到 recoverable=true、retry_with_same_action=true 和 done(error)，不依据普通网络异常猜测重试。完成动作后重读快照展示 selected_sku 等结果。追加的实际 verify / rediagnose 联动仍保留未勾选。
