# bake-off 结果（models.yaml 2026-09-13.5，bakeoff.yaml 2026-09-12.1，repeats=3）

| task | 候选 | 模型 | Schema 通过率 | 字段准确率 | 延迟 P50 | 成本 ¥/次 | 裁决 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| reply.stream | glm-flash | zhipu/glm-4.5-flash | 67% | 65% | 12126 ms | 0.0000 | 未达标（schema_pass 67% < 95%；accuracy 65% < 90%；latency_p50 12126 ms > 3000 ms） |

## 裁决
- reply.stream：主 = —，备 = —；无候选达到主模型门槛（见各候选 reasons）；按 §3.8 需降低门槛并记录原因

## 一次 A1 对话成本：无法估算（缺 intake, reply.stream, diagnose.synthesize, guide.step, escalate.summary 的主模型成本）
