# 巡检报告 2026-09-13T02:31:12.902697+00:00

- git `2381a4f` · mode `stub` · 通过 29/29 · 全部通过
- 延迟（运行器 run_metric 口径）：first_visible_ms p50/p95/max = 4/18/18（n=15）；card_ready_ms p50/p95/max = 6/24/24（n=18）
- 5 并发：通过率 100%，总墙钟 27 ms，card_ready_ms=[24, 23, 24, 23, 23]

| 场景 | 组 | 结果 | 耗时 | 说明 |
| --- | --- | --- | --- | --- |
| duplicate_action | boundary | ✅ | 63 ms | {"runs": 2, "replayed": true, "version": 9, "card_ready_ms": [17, 0], "first_visible_ms": [4]} |
| cannot_do_x3 | boundary | ✅ | 51 ms | {"counters": {"executed": 0, "advanced": 0, "skipped": 3, "plans_exhausted": 1}, "escalate_reason": "R1b", "steps_executed": 3} |
| safety_first_sentence | boundary | ✅ | 35 ms | {"rule": "R4", "model_calls": 0, "elapsed_ms": 3, "first_visible_ms": [2]} |
| safety_mid_text | boundary | ✅ | 47 ms | {"rule": "R4", "steps_in_summary": 1} |
| safety_image_observation | boundary | ✅ | 38 ms | {"rule": "R4", "source": "observation", "model_calls": ["intake", "diagnose.vision"]} |
| wrong_device_receipt | boundary | ✅ | 58 ms | {"receipt_status": "order_product_mismatch", "conflicts": ["订单商品 EUFY-S1-PRO 与当前设备 EUFY-X9-PRO 不一致"]} |
| low_confidence_order_hit | boundary | ✅ | 57 ms | {"receipt_status": "needs_manual_check", "confidence": 0.5} |
| disconnect_refresh_after_feedback | boundary | ✅ | 43 ms | {"resumed_events": 5, "counters": {"executed": 1, "advanced": 1, "skipped": 0, "plans_exhausted": 0}, "card_ready_ms": [0]} |
| restart_recovery | boundary | ✅ | 40 ms | {"orphans_fixed": 1, "last_error": "server_restarted", "continued": true} |
| weknora_down | boundary | ✅ | 39 ms | {"knowledge_status": "unavailable", "mode": "standard_flow", "first_visible_ms": [4], "card_ready_ms": [6]} |
| all_models_down | boundary | ✅ | 41 ms | {"model_calls_attempted": 5, "alert_fired": 2, "done": "awaiting_input", "card_ready_ms": [8]} |
| replay_mismatch | boundary | ✅ | 4 ms | {"case": "a1_hair_wrap", "problems_on_tamper": ["prompt_ver: recorded='2026-09-12.1' current='tampered'"]} |
| vague_input | routing | ✅ | 34 ms | {"clarification": {"reason": "product", "attempts": 1, "asked_run_id": "0a9ef4b81ec94047a5b0cc953459f28f"}, "question": "为了准确排查，请告诉我设备的品类或型号，例如「扫地机 X10 Pro」或「S1… |
| product_ambiguity | routing | ✅ | 33 ms | {"candidates": ["EUFY-S1-PRO", "EUFY-BP-S1-PRO"], "card_ready_ms": [2]} |
| user_correction_and_stale_button | routing | ✅ | 49 ms | {"new_sku": "EUFY-X10-PRO-OMNI", "codes": ["stale_version", "stale_card"]} |
| request_human_anytime | routing | ✅ | 43 ms | {"rule": "R3", "elapsed_ms": 3} |
| two_clarifications_then_r7 | routing | ✅ | 39 ms | {"attempts": 2, "rule": "R7"} |
| rejected_actions_do_not_advance | routing | ✅ | 42 ms | {"codes": [422, 422, "stale_version", "not_allowed_now"], "version": 6} |
| rewrite_decision_table | rewrite | ✅ | 0 ms | {"normal_no_match": "triggered", "disabled": "disabled", "has_hits": "has_hits", "partial_unavailable": "unavailable", "empty_scope": "empty_scope", "unknown_pr… |
| rewrite_off_no_call | rewrite | ✅ | 37 ms | {"rewrite_enabled": false, "invokes": 3, "rewrite_invokes": 0, "retrieval_rounds": 1, "rewrite_used": false, "decision": {"triggered": false, "reason": "disable… |
| rewrite_on_no_match_rescued | rewrite | ✅ | 40 ms | {"rewrite_enabled": true, "invokes": 5, "rewrite_invokes": 1, "retrieval_rounds": 2, "rewrite_used": true, "decision": {"triggered": true, "reason": "eligible"}… |
| rewrite_on_empty_scope | rewrite | ✅ | 38 ms | {"rewrite_enabled": true, "invokes": 3, "rewrite_invokes": 0, "retrieval_rounds": 1, "rewrite_used": false, "decision": {"triggered": false, "reason": "empty_sc… |
| rewrite_on_partial_unavailable | rewrite | ✅ | 40 ms | {"rewrite_enabled": true, "invokes": 3, "rewrite_invokes": 0, "retrieval_rounds": 1, "rewrite_used": false, "decision": {"triggered": false, "reason": "unavaila… |
| rewrite_on_invalid_candidate | rewrite | ✅ | 40 ms | {"rewrite_enabled": true, "invokes": 4, "rewrite_invokes": 1, "retrieval_rounds": 1, "rewrite_used": true, "decision": {"triggered": true, "reason": "eligible"}… |
| rewrite_on_second_round_empty | rewrite | ✅ | 38 ms | {"rewrite_enabled": true, "invokes": 4, "rewrite_invokes": 1, "retrieval_rounds": 2, "rewrite_used": true, "decision": {"triggered": true, "reason": "eligible"}… |
| rewrite_on_budget_insufficient | rewrite | ✅ | 0 ms | {"reason": "budget:7999ms", "min_remaining_ms": 8000} |
| rewrite_on_image_contention | rewrite | ✅ | 39 ms | {"rewrite_enabled": true, "invokes": 5, "rewrite_invokes": 0, "retrieval_rounds": 2, "rewrite_used": true, "decision": {"triggered": false, "reason": "has_hits"… |
| late_result_after_cancel | rewrite | ✅ | 1556 ms | {"cancel_ms": 2, "events_after_cancel": ["run_started", "progress", "done"], "continued": true} |
| five_concurrent_a1 | concurrency | ✅ | 60 ms | {"n": 5, "pass_rate": 1.0, "wall_ms": 27, "card_ready_ms": [24, 23, 24, 23, 23], "first_visible_ms": [18, 17, 18, 17, 17]} |

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
