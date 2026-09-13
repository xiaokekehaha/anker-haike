# bake-off 结果（models.yaml 2026-09-13.4，bakeoff.yaml 2026-09-12.1，repeats=3）

| task | 候选 | 模型 | Schema 通过率 | 字段准确率 | 延迟 P50 | 成本 ¥/次 | 裁决 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| intake | qwen-flash | dashscope/qwen3.7-flash | 100% | 100% | 1136 ms | 0.0002 | **主** |
| disambiguate.clarify | qwen-flash | dashscope/qwen3.7-flash | 100% | 100% | 886 ms | 0.0001 | **主** |
| diagnose.synthesize | qwen-max | dashscope/qwen3.8-max | 100% | 100% | 2511 ms | 0.0100 | **主** |
| guide.step | qwen-max | dashscope/qwen3.8-max | 100% | 97% | 964 ms | 0.0046 | **主** |
| reply.stream | qwen-plus | dashscope/qwen3.7-plus | 100% | 100% | 1188 ms | 0.0003 | **主** |
| escalate.summary | qwen-flash | dashscope/qwen3.7-flash | 100% | 100% | 644 ms | 0.0001 | **主** |
| query.rewrite | qwen-flash | dashscope/qwen3.7-flash | 100% | 100% | 643 ms | 0.0001 | **主** |
| retrieve.grade | qwen-flash | dashscope/qwen3.7-flash | 100% | 96% | 1184 ms | 0.0002 | **主** |
| diagnose.vision | qwen-vl | dashscope/qwen3-vl-plus | 100% | 80% | 1877 ms | 0.0018 | **主** |
| warranty.receipt_ocr | qwen-vl | dashscope/qwen3-vl-plus | 100% | 100% | 3843 ms | 0.0029 | **主** |

## 裁决
- intake：主 = qwen-flash，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）
- disambiguate.clarify：主 = qwen-flash，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）
- diagnose.synthesize：主 = qwen-max，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）
- guide.step：主 = qwen-max，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）
- reply.stream：主 = qwen-plus，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）
- escalate.summary：主 = qwen-flash，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）
- query.rewrite：主 = qwen-flash，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）
- retrieve.grade：主 = qwen-flash，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）
- diagnose.vision：主 = qwen-vl，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）
- warranty.receipt_ocr：主 = qwen-vl，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）

## 一次 A1 对话成本：¥0.0252（门槛 ¥0.5，达标）
