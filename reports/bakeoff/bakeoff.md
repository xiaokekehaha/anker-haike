# bake-off 结果（models.yaml 2026-09-13.2，bakeoff.yaml 2026-09-12.1，repeats=3）

| task | 候选 | 模型 | Schema 通过率 | 字段准确率 | 延迟 P50 | 成本 ¥/次 | 裁决 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| intake | qwen-flash | dashscope/qwen3.7-flash | — | — | — | — | 未跑：missing env DASHSCOPE_API_KEY |
| intake | deepseek | deepseek/deepseek-flash | 100% | 100% | 968 ms | 0.0017 | **主** |
| intake | glm | zhipu/glm-4.7 | 100% | 99% | 1951 ms | 0.0016 | 达标 |
| disambiguate.clarify | qwen-flash | dashscope/qwen3.7-flash | — | — | — | — | 未跑：missing env DASHSCOPE_API_KEY |
| disambiguate.clarify | deepseek | deepseek/deepseek-flash | 100% | 100% | 892 ms | 0.0010 | **主** |
| disambiguate.clarify | glm-flash | zhipu/glm-4.5-flash | 92% | 100% | 1783 ms | 0.0000 | 未达标（schema_pass 92% < 95%） |
| diagnose.synthesize | qwen-max | dashscope/qwen3.8-max | — | — | — | — | 未跑：missing env DASHSCOPE_API_KEY |
| diagnose.synthesize | deepseek | deepseek/deepseek-flash | 100% | 100% | 1163 ms | 0.0024 | **主** |
| diagnose.synthesize | glm-v | zhipu/glm-4.6v | 100% | 92% | 2742 ms | 0.0012 | 达标 |
| guide.step | qwen-max | dashscope/qwen3.8-max | — | — | — | — | 未跑：missing env DASHSCOPE_API_KEY |
| guide.step | deepseek | deepseek/deepseek-flash | 100% | 97% | 957 ms | 0.0011 | **主** |
| guide.step | glm | zhipu/glm-4.7 | 100% | 89% | 1549 ms | 0.0010 | 未达标（accuracy 89% < 90%） |
| reply.stream | qwen-plus | dashscope/qwen3.7-plus | — | — | — | — | 未跑：missing env DASHSCOPE_API_KEY |
| reply.stream | deepseek | deepseek/deepseek-flash | 100% | 100% | 1032 ms | 0.0005 | **备** |
| reply.stream | glm-flash | zhipu/glm-4.5-flash | 100% | 98% | 724 ms | 0.0000 | **主** |
| escalate.summary | deepseek | deepseek/deepseek-flash | 100% | 100% | 960 ms | 0.0006 | **备** |
| escalate.summary | glm-v | zhipu/glm-4.6v | 100% | 100% | 939 ms | 0.0003 | **主** |
| escalate.summary | qwen-flash | dashscope/qwen3.7-flash | — | — | — | — | 未跑：missing env DASHSCOPE_API_KEY |
| query.rewrite | qwen-flash | dashscope/qwen3.7-flash | — | — | — | — | 未跑：missing env DASHSCOPE_API_KEY |
| query.rewrite | deepseek | deepseek/deepseek-flash | 100% | 0% | 882 ms | 0.0009 | 未达标（accuracy 0% < 90%） |
| query.rewrite | glm | zhipu/glm-4.7 | 100% | 0% | 1580 ms | 0.0009 | 未达标（accuracy 0% < 90%） |
| diagnose.vision | qwen-vl | dashscope/qwen3-vl-plus | — | — | — | — | 未跑：missing env DASHSCOPE_API_KEY |
| diagnose.vision | deepseek | deepseek/deepseek-flash | 100% | 90% | 1095 ms | 0.0017 | **主** |
| diagnose.vision | glm-v | zhipu/glm-4.6v | 100% | 77% | 1222 ms | 0.0010 | 未达标（accuracy 77% < 80%） |
| warranty.receipt_ocr | qwen-vl | dashscope/qwen3-vl-plus | — | — | — | — | 未跑：missing env DASHSCOPE_API_KEY |
| warranty.receipt_ocr | deepseek | deepseek/deepseek-flash | 100% | 100% | 1167 ms | 0.0027 | **主** |
| warranty.receipt_ocr | glm-v | zhipu/glm-4.6v | 100% | 100% | 2749 ms | 0.0015 | 达标 |

## 裁决
- intake：主 = deepseek，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）
- disambiguate.clarify：主 = deepseek，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）
- diagnose.synthesize：主 = deepseek，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）
- guide.step：主 = deepseek，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）
- reply.stream：主 = glm-flash，备 = deepseek
- escalate.summary：主 = glm-v，备 = deepseek
- query.rewrite：主 = —，备 = —；无候选达到主模型门槛（见各候选 reasons）；按 §3.8 需降低门槛并记录原因
- diagnose.vision：主 = deepseek，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）
- warranty.receipt_ocr：主 = deepseek，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）

## 一次 A1 对话成本：¥0.0076（门槛 ¥0.5，达标）
