# bake-off 结果（models.yaml 2026-09-15.1，bakeoff.yaml 2026-09-12.1，repeats=2）

| task | 候选 | 模型 | Schema 通过率 | 字段准确率 | 延迟 P50 | 成本 ¥/次 | 裁决 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| diagnose.vision | qwen-vl | dashscope/qwen3-vl-plus | 100% | 88% | 4939 ms | 0.0060 | 达标 |
| diagnose.vision | deepseek | deepseek/deepseek-flash | 100% | 93% | 1377 ms | 0.0051 | **主** |
| diagnose.vision | glm-v | zhipu/glm-4.6v | 100% | 82% | 3390 ms | 0.0033 | 达标 |

## 字段级指标（分母为该指标适用的样本数）
| task | 候选 | 部件准确率 | 现象准确率 | plan 命中率 | 铭牌读出率 | 无幻觉率 | 安全召回 | 可用判定准确率 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| diagnose.vision | qwen-vl | 100% (6) | 100% (6) | 100% (6) | 100% (3) | 83% (6) | 50% (2) | 100% (2) |
| diagnose.vision | deepseek | 100% (6) | 100% (6) | 100% (6) | 100% (3) | 83% (6) | 100% (2) | 100% (2) |
| diagnose.vision | glm-v | 100% (6) | 83% (6) | 83% (6) | 67% (3) | 100% (6) | 50% (2) | 100% (2) |

> 安全召回用的是合成烧灼图。合成图画不出烧焦的材质感（模型一致读成污渍 / 破损），**该列在换上真实照片前不具备参考价值**。文字侧 R4（text_terms 冒烟 / 烧焦 / 鼓包）不依赖视觉，仍然生效。

## 裁决
- diagnose.vision：主 = deepseek，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）

## 一次 A1 对话成本：无法估算（缺 intake, reply.stream, diagnose.synthesize, escalate.summary 的主模型成本）
