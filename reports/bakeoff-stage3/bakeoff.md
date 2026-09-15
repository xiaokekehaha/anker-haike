# bake-off 结果（models.yaml 2026-09-15.2，bakeoff.yaml 2026-09-12.1，读图提示词 2026-09-15.2，词表 2026-09-15.6，repeats=3）

| task | 候选 | 模型 | Schema 通过率 | 字段准确率 | 延迟 P50 | 成本 ¥/次 | 裁决 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| diagnose.vision | deepseek | deepseek/deepseek-flash | 100% | 94% | 1386 ms | 0.0051 | **主** |
| diagnose.vision | qwen-vl | dashscope/qwen3-vl-plus | 100% | 92% | 5354 ms | 0.0062 | 达标 |
| diagnose.vision | glm-v | zhipu/glm-4.6v | 100% | 91% | 4731 ms | 0.0038 | 达标 |

## 字段级指标（分母为该指标适用的样本数）
| task | 候选 | 部件准确率 | 现象准确率 | plan 命中率 | 铭牌读出率 | 无幻觉率 | 未过度弃答率 | 安全召回 | 可用判定准确率 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| diagnose.vision | deepseek | 100% (7) | 100% (7) | 100% (6) | 100% (4) | 100% (6) | 93% (14) | 100% (2) | 100% (6) |
| diagnose.vision | qwen-vl | 100% (7) | 100% (7) | 100% (6) | 100% (4) | 100% (6) | 93% (14) | 100% (2) | 100% (6) |
| diagnose.vision | glm-v | 100% (7) | 86% (7) | 83% (6) | 100% (4) | 100% (6) | 100% (14) | 100% (2) | 100% (6) |

> 安全召回用的是合成烧灼图。合成图画不出烧焦的材质感（模型一致读成污渍 / 破损），**该列在换上真实照片前不具备参考价值**。文字侧 R4（text_terms 冒烟 / 烧焦 / 鼓包）不依赖视觉，仍然生效。

## 裁决
- diagnose.vision：主 = deepseek，备 = —；无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）

## 一次 A1 对话成本：无法估算（缺 intake, reply.stream, diagnose.synthesize, escalate.summary 的主模型成本）
