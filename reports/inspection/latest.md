# 巡检报告 2026-09-12T21:43:14.200722+00:00

- git `6eb6adc` · mode `stub+live` · 通过 30/30 · 全部通过
- 延迟（运行器 run_metric 口径）：first_visible_ms p50/p95/max = 5/18/4254（n=16）；card_ready_ms p50/p95/max = 7/24/5753（n=19）
- 5 并发：通过率 100%，总墙钟 26 ms，card_ready_ms=[24, 23, 23, 23, 23]

| 场景 | 组 | 结果 | 耗时 | 说明 |
| --- | --- | --- | --- | --- |
| duplicate_action | boundary | ✅ | 67 ms | {"runs": 2, "replayed": true, "version": 9, "card_ready_ms": [17, 0], "first_visible_ms": [4]} |
| cannot_do_x3 | boundary | ✅ | 52 ms | {"counters": {"executed": 0, "advanced": 0, "skipped": 3, "plans_exhausted": 1}, "escalate_reason": "R1b", "steps_executed": 3} |
| safety_first_sentence | boundary | ✅ | 34 ms | {"rule": "R4", "model_calls": 0, "elapsed_ms": 3, "first_visible_ms": [2]} |
| safety_mid_text | boundary | ✅ | 47 ms | {"rule": "R4", "steps_in_summary": 1} |
| safety_image_observation | boundary | ✅ | 38 ms | {"rule": "R4", "source": "observation", "model_calls": ["intake", "diagnose.vision"]} |
| wrong_device_receipt | boundary | ✅ | 58 ms | {"receipt_status": "order_product_mismatch", "conflicts": ["订单商品 EUFY-S1-PRO 与当前设备 EUFY-X9-PRO 不一致"]} |
| low_confidence_order_hit | boundary | ✅ | 61 ms | {"receipt_status": "needs_manual_check", "confidence": 0.5} |
| disconnect_refresh_after_feedback | boundary | ✅ | 45 ms | {"resumed_events": 5, "counters": {"executed": 1, "advanced": 1, "skipped": 0, "plans_exhausted": 0}, "card_ready_ms": [0]} |
| restart_recovery | boundary | ✅ | 40 ms | {"orphans_fixed": 1, "last_error": "server_restarted", "continued": true} |
| weknora_down | boundary | ✅ | 38 ms | {"knowledge_status": "unavailable", "mode": "standard_flow", "first_visible_ms": [4], "card_ready_ms": [6]} |
| all_models_down | boundary | ✅ | 40 ms | {"model_calls_attempted": 5, "alert_fired": 2, "done": "awaiting_input", "card_ready_ms": [7]} |
| replay_mismatch | boundary | ✅ | 5 ms | {"case": "a1_hair_wrap", "problems_on_tamper": ["prompt_ver: recorded='2026-09-12.1' current='tampered'"]} |
| vague_input | routing | ✅ | 33 ms | {"clarification": {"reason": "product", "attempts": 1, "asked_run_id": "af59dd5b72dc43258a157e44dceeced7"}, "question": "为了准确排查，请告诉我设备的品类或型号，例如「扫地机 X10 Pro」或「S1… |
| product_ambiguity | routing | ✅ | 33 ms | {"candidates": ["EUFY-S1-PRO", "EUFY-BP-S1-PRO"], "card_ready_ms": [2]} |
| user_correction_and_stale_button | routing | ✅ | 50 ms | {"new_sku": "EUFY-X10-PRO-OMNI", "codes": ["stale_version", "stale_card"]} |
| request_human_anytime | routing | ✅ | 42 ms | {"rule": "R3", "elapsed_ms": 3} |
| two_clarifications_then_r7 | routing | ✅ | 40 ms | {"attempts": 2, "rule": "R7"} |
| rejected_actions_do_not_advance | routing | ✅ | 41 ms | {"codes": [422, 422, "stale_version", "not_allowed_now"], "version": 6} |
| rewrite_decision_table | rewrite | ✅ | 0 ms | {"normal_no_match": "triggered", "disabled": "disabled", "has_hits": "has_hits", "partial_unavailable": "unavailable", "empty_scope": "empty_scope", "unknown_pr… |
| rewrite_off_no_call | rewrite | ✅ | 37 ms | {"rewrite_enabled": false, "invokes": 3, "rewrite_invokes": 0, "retrieval_rounds": 1, "rewrite_used": false, "decision": {"triggered": false, "reason": "disable… |
| rewrite_on_no_match_rescued | rewrite | ✅ | 40 ms | {"rewrite_enabled": true, "invokes": 5, "rewrite_invokes": 1, "retrieval_rounds": 2, "rewrite_used": true, "decision": {"triggered": true, "reason": "eligible"}… |
| rewrite_on_empty_scope | rewrite | ✅ | 38 ms | {"rewrite_enabled": true, "invokes": 3, "rewrite_invokes": 0, "retrieval_rounds": 1, "rewrite_used": false, "decision": {"triggered": false, "reason": "empty_sc… |
| rewrite_on_partial_unavailable | rewrite | ✅ | 38 ms | {"rewrite_enabled": true, "invokes": 3, "rewrite_invokes": 0, "retrieval_rounds": 1, "rewrite_used": false, "decision": {"triggered": false, "reason": "unavaila… |
| rewrite_on_invalid_candidate | rewrite | ✅ | 38 ms | {"rewrite_enabled": true, "invokes": 4, "rewrite_invokes": 1, "retrieval_rounds": 1, "rewrite_used": true, "decision": {"triggered": true, "reason": "eligible"}… |
| rewrite_on_second_round_empty | rewrite | ✅ | 39 ms | {"rewrite_enabled": true, "invokes": 4, "rewrite_invokes": 1, "retrieval_rounds": 2, "rewrite_used": true, "decision": {"triggered": true, "reason": "eligible"}… |
| rewrite_on_budget_insufficient | rewrite | ✅ | 0 ms | {"reason": "budget:7999ms", "min_remaining_ms": 8000} |
| rewrite_on_image_contention | rewrite | ✅ | 40 ms | {"rewrite_enabled": true, "invokes": 5, "rewrite_invokes": 0, "retrieval_rounds": 2, "rewrite_used": true, "decision": {"triggered": false, "reason": "has_hits"… |
| late_result_after_cancel | rewrite | ✅ | 1557 ms | {"cancel_ms": 2, "events_after_cancel": ["run_started", "progress", "done"], "continued": true} |
| five_concurrent_a1 | concurrency | ✅ | 58 ms | {"n": 5, "pass_rate": 1.0, "wall_ms": 26, "card_ready_ms": [24, 23, 23, 23, 23], "first_visible_ms": [18, 17, 18, 18, 16]} |
| live_a1_real_model | live | ✅ | 5816 ms | {"session_id": "cc2c024e61514f1ba9797db04b9dd328", "first_visible_ms": 4254, "card_ready_ms": 5753, "step": {"plan_id": "rv_suction_hair_wrap", "step_id": "s1",… |

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

## 真实模型语义样例（--live）

- first_visible_ms=4254 card_ready_ms=5753 step={'plan_id': 'rv_suction_hair_wrap', 'step_id': 's1', 'title': '检查并清理滚刷'} replay=False
