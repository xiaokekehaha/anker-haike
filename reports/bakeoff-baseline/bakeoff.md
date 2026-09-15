# bake-off 结果（models.yaml 2026-09-13.5，bakeoff.yaml 2026-09-12.1，repeats=1）

| task | 候选 | 模型 | Schema 通过率 | 字段准确率 | 延迟 P50 | 成本 ¥/次 | 裁决 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| diagnose.vision | deepseek | deepseek/deepseek-flash | 100% | 65% | 1371 ms | 0.0040 | 未达标（accuracy 65% < 80%） |
| diagnose.vision | qwen-vl | dashscope/qwen3-vl-plus | 100% | 80% | 4106 ms | 0.0044 | **主** |
| diagnose.vision | glm-v | zhipu/glm-4.6v | 93% | 69% | 3891 ms | 0.0025 | 未达标（schema_pass 93% < 95%；accuracy 69% < 80%） |

## 字段级指标（分母为该指标适用的样本数）
| task | 候选 | 部件准确率 | 现象准确率 | plan 命中率 | 铭牌读出率 | 无幻觉率 | 安全召回 | 可用判定准确率 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| diagnose.vision | deepseek | 83% (6) | 67% (6) | 67% (6) | 67% (3) | 83% (6) | 0% (2) | 100% (2) |
| diagnose.vision | qwen-vl | 83% (6) | 83% (6) | 83% (6) | 100% (3) | 100% (6) | 0% (2) | 100% (2) |
| diagnose.vision | glm-v | 83% (6) | 67% (6) | 67% (6) | 0% (3) | 100% (6) | 0% (2) | 100% (2) |

## 裁决
- diagnose.vision：主 = qwen-vl，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）

## 一次 A1 对话成本：无法估算（缺 intake, reply.stream, diagnose.synthesize, escalate.summary 的主模型成本）
