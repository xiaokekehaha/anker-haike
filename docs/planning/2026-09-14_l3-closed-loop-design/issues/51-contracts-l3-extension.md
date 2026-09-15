# 51: 契约扩展一次落地（Stage / Intent / Emotion / 动作 / 事件 / 快照 / TS 生成）

**What to build:** 在 `contracts/haike_contracts/` 一次性扩展并重新生成 TS + JSON Schema：`Stage += consult|context|propose|execute|track|awaiting_human`；`PendingKind += confirm_context|confirm_proposal|upload_retake|rate_satisfaction`；`ActionKind += confirm_context|confirm_proposal|decline_proposal|skip_retake|rate_satisfaction` 及载荷；`EmotionLevel = calm|dissatisfied|angry|complaint_risk`，`EmotionStrategy += direct_resolution|de_escalate_and_offer_human`；事件 `context_card / proposal_card / execution_card / retake_card / rating_card / case_changed`；快照 items 对应六种；`EscalationSummary` 增量字段（case_id / policy_decision_brief / recommended_options / gate_result / task_queue / emotion_track / draft_reply，全部可选）；`PolicyDecision / RemedyDecision / Clause / FaultLocalization / Receipt` 共享模型。前端 `reducer.ts` upsert 分支与 `Timeline.tsx` 占位组件（先渲染 JSON 摘要，正式组件在各票）。

**Blocked by:** —

**Status:** done

**Owner:** —

- [ ] `make contracts` 通过，`contracts:check` CI 通过；旧事件 / 快照 fixture 全部仍能解析（向后兼容：新字段全可选）
- [ ] `EmotionLevel` 旧值 `anxious` 的处理：契约保留 `anxious` 为兼容别名映射到 `dissatisfied`（reduce 层转换），前端旧快照不报错
- [ ] 前端全量测试通过；reducer 新分支各一测（upsert 保留用户结果字段）
- [ ] 文档：08_session-execution-contract §4/§5 追加新动作 / 事件表

**设计依据：** 02 §2.3–2.4；03 §6；05 §3；06 §1/§4；00 D-L3-16
