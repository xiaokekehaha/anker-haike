# bake-off 结果（models.yaml 2026-09-13.5，bakeoff.yaml 2026-09-12.1，repeats=3）

| task | 候选 | 模型 | Schema 通过率 | 字段准确率 | 延迟 P50 | 成本 ¥/次 | 裁决 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| intake | qwen-flash | dashscope/qwen3.7-flash | 100% | 98% | 1051 ms | 0.0002 | **主** |
| intake | deepseek | deepseek/deepseek-flash | 100% | 100% | 953 ms | 0.0016 | **备** |
| intake | glm | zhipu/glm-4.7 | 100% | 97% | 1364 ms | 0.0016 | 达标 |
| disambiguate.clarify | qwen-flash | dashscope/qwen3.7-flash | 100% | 100% | 752 ms | 0.0001 | **主** |
| disambiguate.clarify | deepseek | deepseek/deepseek-flash | 100% | 100% | 990 ms | 0.0010 | **备** |
| disambiguate.clarify | glm | zhipu/glm-4.7 | 100% | 100% | 965 ms | 0.0009 | 达标 |
| diagnose.synthesize | deepseek | deepseek/deepseek-flash | 100% | 100% | 1162 ms | 0.0023 | **主** |
| diagnose.synthesize | qwen-max | dashscope/qwen3.8-max | 100% | 100% | 2179 ms | 0.0094 | 达标 |
| diagnose.synthesize | glm-v | zhipu/glm-4.6v | 100% | 88% | 2320 ms | 0.0011 | 未达标（accuracy 88% < 90%） |
| guide.step | deepseek | deepseek/deepseek-flash | 100% | 97% | 929 ms | 0.0011 | **主** |
| guide.step | qwen-max | dashscope/qwen3.8-max | 100% | 94% | 998 ms | 0.0047 | **备** |
| guide.step | glm | zhipu/glm-4.7 | 100% | 89% | 1130 ms | 0.0011 | 未达标（accuracy 89% < 90%） |
| reply.stream | qwen-plus | dashscope/qwen3.7-plus | 100% | 98% | 900 ms | 0.0003 | 达标 |
| reply.stream | deepseek | deepseek/deepseek-flash | 100% | 98% | 1084 ms | 0.0005 | 达标 |
| reply.stream | glm | zhipu/glm-4.7 | 100% | 98% | 582 ms | 0.0002 | **主** |
| escalate.summary | qwen-flash | dashscope/qwen3.7-flash | 100% | 100% | 648 ms | 0.0001 | **主** |
| escalate.summary | deepseek | deepseek/deepseek-flash | 100% | 100% | 899 ms | 0.0006 | **备** |
| escalate.summary | glm-v | zhipu/glm-4.6v | 100% | 100% | 723 ms | 0.0003 | 达标 |
| query.rewrite | qwen-flash | dashscope/qwen3.7-flash | 100% | 75% | 535 ms | 0.0001 | 未达标（accuracy 75% < 90%） |
| query.rewrite | deepseek | deepseek/deepseek-flash | 100% | 75% | 915 ms | 0.0009 | 未达标（accuracy 75% < 90%） |
| query.rewrite | glm | zhipu/glm-4.7 | 100% | 62% | 851 ms | 0.0008 | 未达标（accuracy 62% < 90%） |
| retrieve.grade | qwen-flash | dashscope/qwen3.7-flash | 100% | 92% | 1193 ms | 0.0002 | **主** |
| retrieve.grade | deepseek | deepseek/deepseek-flash | 100% | 100% | 1105 ms | 0.0018 | **备** |
| retrieve.grade | glm | zhipu/glm-4.7 | 100% | 100% | 2135 ms | 0.0020 | 达标 |
| diagnose.vision | deepseek | deepseek/deepseek-flash | 100% | 83% | 1188 ms | 0.0017 | **主** |
| diagnose.vision | qwen-vl | dashscope/qwen3-vl-plus | 100% | 83% | 1554 ms | 0.0018 | **备** |
| diagnose.vision | glm-v | zhipu/glm-4.6v | 93% | 77% | 1261 ms | 0.0010 | 未达标（schema_pass 93% < 95%；accuracy 77% < 80%） |
| warranty.receipt_ocr | deepseek | deepseek/deepseek-flash | 100% | 100% | 1218 ms | 0.0027 | **主** |
| warranty.receipt_ocr | qwen-vl | dashscope/qwen3-vl-plus | 100% | 100% | 3355 ms | 0.0029 | 达标 |
| warranty.receipt_ocr | glm-v | zhipu/glm-4.6v | 100% | 100% | 2958 ms | 0.0015 | 达标 |

## 裁决
- intake：主 = qwen-flash，备 = deepseek
- disambiguate.clarify：主 = qwen-flash，备 = deepseek
- diagnose.synthesize：主 = deepseek，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）
- guide.step：主 = deepseek，备 = qwen-max
- reply.stream：主 = glm，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）
- escalate.summary：主 = qwen-flash，备 = deepseek
- query.rewrite：主 = —，备 = —；无候选达到主模型门槛（见各候选 reasons）；按 §3.8 需降低门槛并记录原因
- retrieve.grade：主 = qwen-flash，备 = deepseek
- diagnose.vision：主 = deepseek，备 = qwen-vl
- warranty.receipt_ocr：主 = deepseek，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）

## 一次 A1 对话成本：¥0.0068（门槛 ¥0.5，达标）
