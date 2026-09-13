# 巡检报告 2026-09-13T00:35:47.611354+00:00

- git `4abcd4e` · mode `stub` · 通过 29/29 · 全部通过
- 延迟（运行器 run_metric 口径）：first_visible_ms p50/p95/max = 10/24/24（n=15）；card_ready_ms p50/p95/max = 14/32/78（n=18）
- 5 并发：通过率 100%，总墙钟 36 ms，card_ready_ms=[32, 31, 31, 31, 31]

| 场景 | 组 | 结果 | 耗时 | 说明 |
| --- | --- | --- | --- | --- |
| duplicate_action | boundary | ✅ | 99 ms | {"runs": 2, "replayed": true, "version": 9, "card_ready_ms": [31, 1], "first_visible_ms": [8]} |
| cannot_do_x3 | boundary | ✅ | 74 ms | {"counters": {"executed": 0, "advanced": 0, "skipped": 3, "plans_exhausted": 1}, "escalate_reason": "R1b", "steps_executed": 3} |
| safety_first_sentence | boundary | ✅ | 42 ms | {"rule": "R4", "model_calls": 0, "elapsed_ms": 4, "first_visible_ms": [3]} |
| safety_mid_text | boundary | ✅ | 56 ms | {"rule": "R4", "steps_in_summary": 1} |
| safety_image_observation | boundary | ✅ | 46 ms | {"rule": "R4", "source": "observation", "model_calls": ["intake", "diagnose.vision"]} |
| wrong_device_receipt | boundary | ✅ | 72 ms | {"receipt_status": "order_product_mismatch", "conflicts": ["订单商品 EUFY-S1-PRO 与当前设备 EUFY-X9-PRO 不一致"]} |
| low_confidence_order_hit | boundary | ✅ | 71 ms | {"receipt_status": "needs_manual_check", "confidence": 0.5} |
| disconnect_refresh_after_feedback | boundary | ✅ | 54 ms | {"resumed_events": 5, "counters": {"executed": 1, "advanced": 1, "skipped": 0, "plans_exhausted": 0}, "card_ready_ms": [0]} |
| restart_recovery | boundary | ✅ | 71 ms | {"orphans_fixed": 1, "last_error": "server_restarted", "continued": true} |
| weknora_down | boundary | ✅ | 61 ms | {"knowledge_status": "unavailable", "mode": "standard_flow", "first_visible_ms": [8], "card_ready_ms": [12]} |
| all_models_down | boundary | ✅ | 144 ms | {"model_calls_attempted": 5, "alert_fired": 2, "done": "awaiting_input", "card_ready_ms": [78]} |
| replay_mismatch | boundary | ✅ | 8 ms | {"case": "a1_hair_wrap", "problems_on_tamper": ["prompt_ver: recorded='2026-09-12.1' current='tampered'"]} |
| vague_input | routing | ✅ | 49 ms | {"clarification": {"reason": "product", "attempts": 1, "asked_run_id": "c22d99f142df4ae681dba3ef4279c094"}, "question": "为了准确排查，请告诉我设备的品类或型号，例如「扫地机 X10 Pro」或「S1… |
| product_ambiguity | routing | ✅ | 43 ms | {"candidates": ["EUFY-S1-PRO", "EUFY-BP-S1-PRO"], "card_ready_ms": [3]} |
| user_correction_and_stale_button | routing | ✅ | 69 ms | {"new_sku": "EUFY-X10-PRO-OMNI", "codes": ["stale_version", "stale_card"]} |
| request_human_anytime | routing | ✅ | 54 ms | {"rule": "R3", "elapsed_ms": 4} |
| two_clarifications_then_r7 | routing | ✅ | 51 ms | {"attempts": 2, "rule": "R7"} |
| rejected_actions_do_not_advance | routing | ✅ | 52 ms | {"codes": [422, 422, "stale_version", "not_allowed_now"], "version": 6} |
| rewrite_decision_table | rewrite | ✅ | 0 ms | {"normal_no_match": "triggered", "disabled": "disabled", "has_hits": "has_hits", "partial_unavailable": "unavailable", "empty_scope": "empty_scope", "unknown_pr… |
| rewrite_off_no_call | rewrite | ✅ | 53 ms | {"rewrite_enabled": false, "invokes": 3, "rewrite_invokes": 0, "retrieval_rounds": 1, "rewrite_used": false, "decision": {"triggered": false, "reason": "disable… |
| rewrite_on_no_match_rescued | rewrite | ✅ | 59 ms | {"rewrite_enabled": true, "invokes": 5, "rewrite_invokes": 1, "retrieval_rounds": 2, "rewrite_used": true, "decision": {"triggered": true, "reason": "eligible"}… |
| rewrite_on_empty_scope | rewrite | ✅ | 62 ms | {"rewrite_enabled": true, "invokes": 3, "rewrite_invokes": 0, "retrieval_rounds": 1, "rewrite_used": false, "decision": {"triggered": false, "reason": "empty_sc… |
| rewrite_on_partial_unavailable | rewrite | ✅ | 66 ms | {"rewrite_enabled": true, "invokes": 3, "rewrite_invokes": 0, "retrieval_rounds": 1, "rewrite_used": false, "decision": {"triggered": false, "reason": "unavaila… |
| rewrite_on_invalid_candidate | rewrite | ✅ | 66 ms | {"rewrite_enabled": true, "invokes": 4, "rewrite_invokes": 1, "retrieval_rounds": 1, "rewrite_used": true, "decision": {"triggered": true, "reason": "eligible"}… |
| rewrite_on_second_round_empty | rewrite | ✅ | 61 ms | {"rewrite_enabled": true, "invokes": 4, "rewrite_invokes": 1, "retrieval_rounds": 2, "rewrite_used": true, "decision": {"triggered": true, "reason": "eligible"}… |
| rewrite_on_budget_insufficient | rewrite | ✅ | 0 ms | {"reason": "budget:7999ms", "min_remaining_ms": 8000} |
| rewrite_on_image_contention | rewrite | ✅ | 65 ms | {"rewrite_enabled": true, "invokes": 5, "rewrite_invokes": 0, "retrieval_rounds": 2, "rewrite_used": true, "decision": {"triggered": false, "reason": "has_hits"… |
| late_result_after_cancel | rewrite | ✅ | 1573 ms | {"cancel_ms": 5, "events_after_cancel": ["run_started", "progress", "done"], "continued": true} |
| five_concurrent_a1 | concurrency | ✅ | 71 ms | {"n": 5, "pass_rate": 1.0, "wall_ms": 36, "card_ready_ms": [32, 31, 31, 31, 31], "first_visible_ms": [24, 23, 22, 23, 24]} |

## 改写开关巡检（stub 路由测试，不代表改写语义质量）

| 场景 | rewrite_enabled | invoke | rewrite invoke | 检索轮数 | 第二轮延迟 | 回退 | 知识状态 | 决策 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rewrite_off_no_call | False | 3 | 0 | 1 | 0 ms | standard_flow | no_match | disabled |
| rewrite_on_no_match_rescued | True | 5 | 1 | 2 | 0 ms | evidence | ok | eligible |
| rewrite_on_empty_scope | True | 3 | 0 | 1 | 0 ms | standard_flow | no_match | empty_scope |
| rewrite_on_partial_unavailable | True | 3 | 0 | 1 | 0 ms | standard_flow | no_match | unavailable |
| rewrite_on_invalid_candidate | True | 4 | 1 | 1 | 0 ms | standard_flow | no_match | eligible |
| rewrite_on_second_round_empty | True | 4 | 1 | 2 | 0 ms | standard_flow | no_match | eligible |
| rewrite_on_image_contention | True | 5 | 0 | 2 | 0 ms | evidence | ok | has_hits |
