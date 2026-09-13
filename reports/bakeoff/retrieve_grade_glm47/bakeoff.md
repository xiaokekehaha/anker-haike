# bake-off 结果（models.yaml 2026-09-13.4，bakeoff.yaml 2026-09-12.1，repeats=5）

| task | 候选 | 模型 | Schema 通过率 | 字段准确率 | 延迟 P50 | 成本 ¥/次 | 裁决 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| retrieve.grade | glm | zhipu/glm-4.7 | 100% | 91% | 2054 ms | 0.0020 | **主** |

## 裁决
- retrieve.grade：主 = glm，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）

## 一次 A1 对话成本：无法估算（缺 intake, reply.stream, diagnose.synthesize, guide.step, escalate.summary 的主模型成本）
