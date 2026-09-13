# bake-off 结果（models.yaml 2026-09-13.2，bakeoff.yaml 2026-09-12.1，repeats=1）

| task | 候选 | 模型 | Schema 通过率 | 字段准确率 | 延迟 P50 | 成本 ¥/次 | 裁决 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| retrieve.grade | glm-flash | zhipu/glm-4.5-flash | 25% | 25% | 7242 ms | 0.0000 | 未达标（schema_pass 25% < 95%；accuracy 25% < 90%） |

## 裁决
- retrieve.grade：主 = —，备 = —；无候选达到主模型门槛（见各候选 reasons）；按 §3.8 需降低门槛并记录原因

## 一次 A1 对话成本：无法估算（缺 intake, reply.stream, diagnose.synthesize, guide.step, escalate.summary 的主模型成本）
