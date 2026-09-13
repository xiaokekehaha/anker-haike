# bake-off 结果（models.yaml 2026-09-13.4，bakeoff.yaml 2026-09-12.1，repeats=3）

| task | 候选 | 模型 | Schema 通过率 | 字段准确率 | 延迟 P50 | 成本 ¥/次 | 裁决 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| diagnose.vision | qwen-vl | dashscope/qwen3-vl-plus | 100% | 80% | 1541 ms | 0.0018 | **备** |
| diagnose.vision | deepseek | deepseek/deepseek-flash | 100% | 80% | 1160 ms | 0.0017 | **主** |
| warranty.receipt_ocr | qwen-vl | dashscope/qwen3-vl-plus | 100% | 100% | 4110 ms | 0.0029 | 达标 |
| warranty.receipt_ocr | deepseek | deepseek/deepseek-flash | 100% | 100% | 1230 ms | 0.0027 | **主** |

## 裁决
- diagnose.vision：主 = deepseek，备 = qwen-vl
- warranty.receipt_ocr：主 = deepseek，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）

## 一次 A1 对话成本：无法估算（缺 intake, reply.stream, diagnose.synthesize, guide.step, escalate.summary 的主模型成本）
