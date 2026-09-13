# bake-off 结果（models.yaml 2026-09-13.2，bakeoff.yaml 2026-09-12.1，repeats=3）

| task | 候选 | 模型 | Schema 通过率 | 字段准确率 | 延迟 P50 | 成本 ¥/次 | 裁决 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| query.rewrite | qwen-flash | dashscope/qwen3.7-flash | 100% | 100% | 706 ms | 0.0001 | **主** |
| query.rewrite | deepseek | deepseek/deepseek-flash | 100% | 88% | 841 ms | 0.0009 | 未达标（accuracy 88% < 90%） |
| query.rewrite | glm | zhipu/glm-4.7 | 100% | 38% | 796 ms | 0.0009 | 未达标（accuracy 38% < 90%） |

## 裁决
- query.rewrite：主 = qwen-flash，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）

## 一次 A1 对话成本：无法估算（缺 intake, reply.stream, diagnose.synthesize, guide.step, escalate.summary 的主模型成本）
