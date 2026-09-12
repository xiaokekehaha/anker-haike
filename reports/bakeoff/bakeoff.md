# bake-off 结果（models.yaml 2026-09-13.1，bakeoff.yaml 2026-09-12.1，repeats=3）

| task | 候选 | 模型 | Schema 通过率 | 字段准确率 | 延迟 P50 | 成本 ¥/次 | 裁决 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| intake | deepseek | deepseek/deepseek-flash | 100% | 100% | 903 ms | 0.0017 | **主** |
| disambiguate.clarify | deepseek | deepseek/deepseek-flash | 100% | 100% | 892 ms | 0.0010 | **主** |
| diagnose.synthesize | deepseek | deepseek/deepseek-flash | 100% | 100% | 917 ms | 0.0024 | **主** |
| guide.step | deepseek | deepseek/deepseek-flash | 100% | 97% | 861 ms | 0.0011 | **主** |
| reply.stream | deepseek | deepseek/deepseek-flash | 100% | 100% | 963 ms | 0.0005 | **主** |
| escalate.summary | deepseek | deepseek/deepseek-flash | 100% | 100% | 800 ms | 0.0006 | **主** |
| query.rewrite | deepseek | deepseek/deepseek-flash | 100% | 0% | 871 ms | 0.0009 | 未达标（accuracy 0% < 90%） |
| diagnose.vision | deepseek | deepseek/deepseek-flash | 100% | 87% | 1059 ms | 0.0017 | **主** |
| warranty.receipt_ocr | deepseek | deepseek/deepseek-flash | 100% | 100% | 1135 ms | 0.0027 | **主** |

## 裁决
- intake：主 = deepseek，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）
- disambiguate.clarify：主 = deepseek，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）
- diagnose.synthesize：主 = deepseek，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）
- guide.step：主 = deepseek，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）
- reply.stream：主 = deepseek，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）
- escalate.summary：主 = deepseek，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）
- query.rewrite：主 = —，备 = —；无候选达到主模型门槛（见各候选 reasons）；按 §3.8 需降低门槛并记录原因
- diagnose.vision：主 = deepseek，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）
- warranty.receipt_ocr：主 = deepseek，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）

## 一次 A1 对话成本：¥0.0098（门槛 ¥0.5，达标）
