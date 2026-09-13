# 巡检报告 2026-09-13T00:36:49.735164+00:00

- git `4abcd4e` · mode `stub+live` · 通过 0/1 · **失败：live_a1_real_model**
- 延迟（运行器 run_metric 口径）：first_visible_ms p50/p95/max = None/None/None（n=0）；card_ready_ms p50/p95/max = None/None/None（n=0）

| 场景 | 组 | 结果 | 耗时 | 说明 |
| --- | --- | --- | --- | --- |
| live_a1_real_model | live | ❌ | 319 ms | AssertionError: 真实 A1 未出步骤卡：['run_started', 'progress', 'error', 'done'] |
