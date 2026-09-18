# 巡检报告 2026-09-17T12:28:27.496196+00:00

- git `a460530` · mode `stub` · 通过 27/36 · **失败：cannot_do_x3, safety_mid_text, wrong_device_receipt, low_confidence_order_hit, disconnect_refresh_after_feedback, all_models_down, vague_input, product_ambiguity, two_clarifications_then_r7**
- 延迟（运行器 run_metric 口径）：first_visible_ms p50/p95/max = 62/62/62（n=1）；card_ready_ms p50/p95/max = 80/412/413（n=15）
- 5 并发：通过率 100%，总墙钟 416 ms，card_ready_ms=[413, 409, 411, 412, 409]

| 场景 | 组 | 结果 | 耗时 | 说明 |
| --- | --- | --- | --- | --- |
| duplicate_action | boundary | ✅ | 305 ms | {"runs": 2, "replayed": true, "version": 2, "card_ready_ms": [178, 17]} |
| cannot_do_x3 | boundary | ❌ | 258 ms | AssertionError: no awaiting_input in ['run_started', 'input_received', 'progress', 'issue_changed', 'pending_changed', 'message_start', 'message', 'message_end', 'escalation_summary', 'summary_updated', 'done'] |
| safety_first_sentence | boundary | ✅ | 157 ms | {"rule": "R4", "model_calls": 1, "elapsed_ms": 63, "first_visible_ms": [62]} |
| safety_mid_text | boundary | ❌ | 286 ms | AssertionError: 应走 rediagnose：[('intake', None), ('escalate', 'summarize')] |
| safety_image_observation | boundary | ✅ | 226 ms | {"rule": "R4", "source": "observation", "model_calls": ["intake", "diagnose.vision"]} |
| wrong_device_receipt | boundary | ❌ | 228 ms | AssertionError: no awaiting_input in ['run_started', 'input_received', 'progress', 'issue_changed', 'pending_changed', 'message_start', 'message', 'message_end', 'escalation_summary', 'summary_updated', 'done'] |
| low_confidence_order_hit | boundary | ❌ | 242 ms | AssertionError: no awaiting_input in ['run_started', 'input_received', 'progress', 'issue_changed', 'pending_changed', 'message_start', 'message', 'message_end', 'escalation_summary', 'summary_updated', 'done'] |
| disconnect_refresh_after_feedback | boundary | ❌ | 236 ms | AssertionError: 重试应重放 |
| restart_recovery | boundary | ✅ | 187 ms | {"orphans_fixed": 1, "last_error": "server_restarted", "continued": true} |
| weknora_down | boundary | ✅ | 232 ms | {"knowledge_status": "unavailable", "mode": "standard_flow", "card_ready_ms": [80]} |
| all_models_down | boundary | ❌ | 111 ms | AssertionError: 产品可由规则查表确认、检索有证据 → 仍应出卡（改写用原文） |
| replay_mismatch | boundary | ✅ | 18 ms | {"case": "a1_hair_wrap", "problems_on_tamper": ["prompt_ver: recorded='system=2026-09-14.1;interpret=2026-09-14.8;reply=2026-09-12.1;guide=2026-09-12.1;clarify=… |
| vague_input | routing | ❌ | 113 ms | AssertionError: 我暂时无法完成这次理解，已有信息仍会保留。请指出要查询的信息或要继续的步骤。 |
| product_ambiguity | routing | ❌ | 113 ms | AssertionError: 应出产品卡：['run_started', 'input_received', 'progress', 'progress', 'issue_changed', 'message_start', 'message', 'message_end', 'done'] |
| user_correction_and_stale_button | routing | ✅ | 240 ms | {"new_sku": "EUFY-X10-PRO-OMNI", "codes": ["stale_version", "stale_card"]} |
| request_human_anytime | routing | ✅ | 212 ms | {"rule": "R3", "elapsed_ms": 32} |
| two_clarifications_then_r7 | routing | ❌ | 139 ms | AssertionError: 应 R7：None clar=None |
| rejected_actions_do_not_advance | routing | ✅ | 216 ms | {"codes": [422, 422, "stale_version", "not_allowed_now"], "version": 1} |
| rewrite_decision_table | rewrite | ✅ | 1 ms | {"normal_no_match": "triggered", "disabled": "disabled", "has_hits": "has_hits", "partial_unavailable": "unavailable", "empty_scope": "empty_scope", "unknown_pr… |
| rewrite_off_no_call | rewrite | ✅ | 161 ms | {"rewrite_enabled": false, "invokes": 1, "rewrite_invokes": 0, "retrieval_rounds": 1, "rewrite_used": false, "decision": {"triggered": false, "reason": "disable… |
| rewrite_on_no_match_rescued | rewrite | ✅ | 170 ms | {"rewrite_enabled": true, "invokes": 3, "rewrite_invokes": 1, "retrieval_rounds": 2, "rewrite_used": true, "decision": {"triggered": true, "reason": "eligible"}… |
| rewrite_on_empty_scope | rewrite | ✅ | 161 ms | {"rewrite_enabled": true, "invokes": 1, "rewrite_invokes": 0, "retrieval_rounds": 1, "rewrite_used": false, "decision": {"triggered": false, "reason": "empty_sc… |
| rewrite_on_partial_unavailable | rewrite | ✅ | 160 ms | {"rewrite_enabled": true, "invokes": 1, "rewrite_invokes": 0, "retrieval_rounds": 1, "rewrite_used": false, "decision": {"triggered": false, "reason": "unavaila… |
| rewrite_on_invalid_candidate | rewrite | ✅ | 161 ms | {"rewrite_enabled": true, "invokes": 2, "rewrite_invokes": 1, "retrieval_rounds": 1, "rewrite_used": true, "decision": {"triggered": true, "reason": "eligible"}… |
| rewrite_on_second_round_empty | rewrite | ✅ | 164 ms | {"rewrite_enabled": true, "invokes": 2, "rewrite_invokes": 1, "retrieval_rounds": 2, "rewrite_used": true, "decision": {"triggered": true, "reason": "eligible"}… |
| rewrite_on_budget_insufficient | rewrite | ✅ | 1 ms | {"reason": "budget:7999ms", "min_remaining_ms": 8000} |
| rewrite_on_image_contention | rewrite | ✅ | 225 ms | {"rewrite_enabled": true, "invokes": 3, "rewrite_invokes": 0, "retrieval_rounds": 2, "rewrite_used": true, "decision": {"triggered": false, "reason": "quota_use… |
| late_result_after_cancel | rewrite | ✅ | 1725 ms | {"cancel_ms": 3, "events_after_cancel": ["input_received", "progress", "done"], "continued": true} |
| five_concurrent_a1 | concurrency | ✅ | 510 ms | {"n": 5, "pass_rate": 1.0, "wall_ms": 416, "card_ready_ms": [413, 409, 411, 412, 409], "first_visible_ms": []} |
| l3_forged_authorization | l3 | ✅ | 15 ms | {"unauthorized_writes": 0} |
| l3_idempotent_execution | l3 | ✅ | 67 ms | {"created": 1, "replayed": 5} |
| l3_hitl_reject | l3 | ✅ | 0 ms | {"status": "rejected"} |
| l3_backend_faults | l3 | ✅ | 27 ms | {"statuses": ["failed", "failed"]} |
| l3_complaint_escalation | l3 | ✅ | 7 ms | {"levels": ["dissatisfied", "angry", "complaint_risk"]} |
| l3_blurry_image | l3 | ✅ | 3 ms | {"usable": false, "model_accuracy": "not_evaluated"} |
| l3_task_continuation | l3 | ✅ | 3 ms | {"next": "logistics_query"} |

## 改写开关巡检（stub 路由测试，不代表改写语义质量）

| 场景 | rewrite_enabled | invoke | rewrite invoke | 检索轮数 | 第二轮延迟 | 回退 | 知识状态 | 决策 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rewrite_off_no_call | False | 1 | 0 | 1 | 0 ms | standard_flow | no_match | disabled |
| rewrite_on_no_match_rescued | True | 3 | 1 | 2 | 0 ms | evidence | ok | eligible |
| rewrite_on_empty_scope | True | 1 | 0 | 1 | 0 ms | standard_flow | no_match | empty_scope |
| rewrite_on_partial_unavailable | True | 1 | 0 | 1 | 0 ms | standard_flow | no_match | unavailable |
| rewrite_on_invalid_candidate | True | 2 | 1 | 1 | 0 ms | standard_flow | no_match | eligible |
| rewrite_on_second_round_empty | True | 2 | 1 | 2 | 0 ms | standard_flow | no_match | eligible |
| rewrite_on_image_contention | True | 3 | 0 | 2 | 0 ms | evidence | ok | quota_used |
