# 巡检报告 2026-09-14T10:44:10.175912+00:00

- git `9190d21` · mode `stub` · 通过 7/7 · 全部通过
- 延迟（运行器 run_metric 口径）：first_visible_ms p50/p95/max = None/None/None（n=0）；card_ready_ms p50/p95/max = None/None/None（n=0）

| 场景 | 组 | 结果 | 耗时 | 说明 |
| --- | --- | --- | --- | --- |
| l3_forged_authorization | l3 | ✅ | 10 ms | {"unauthorized_writes": 0} |
| l3_idempotent_execution | l3 | ✅ | 36 ms | {"created": 1, "replayed": 5} |
| l3_hitl_reject | l3 | ✅ | 0 ms | {"status": "rejected"} |
| l3_backend_faults | l3 | ✅ | 17 ms | {"statuses": ["failed", "failed"]} |
| l3_complaint_escalation | l3 | ✅ | 4 ms | {"levels": ["dissatisfied", "angry", "complaint_risk"]} |
| l3_blurry_image | l3 | ✅ | 1 ms | {"usable": false, "model_accuracy": "not_evaluated"} |
| l3_task_continuation | l3 | ✅ | 2 ms | {"next": "logistics_query"} |
