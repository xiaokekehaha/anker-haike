# 62: 看图结构化故障定位、图片可用性与 RetakeCard

**What to build:** `diagnose.vision` 输出 `FaultLocalization{findings[part, location, phenomenon, severity, confidence, quote_region], image_quality{usable, reasons}, model_hint, conflicts_with_text}`，prompt 版本 2026-09-14.1；`config/vision_vocab.yaml`（部件 / 现象受控词表、retake_guidance）；词表外归「其他」并保留 raw；`observations` 派生保证 CP-in 安全匹配不变（observation_terms 增中文词）；`fault_cards.faults[].signatures[{part, phenomenon}]` 确定性命中提高先验；`model_hint` 进 disambiguate 候选；`usable=false` 且无其他可用图 → `prepare_retake → await_input` 发 `retake_card`，`skip_retake` → 文字流程，计 clarification(reason=image)；`conflicts_with_text` 非空 → clarify(conflict)。视觉链失败行为不变。

**Blocked by:** 51

**Status:** todo

**Owner:** —

- [ ] A9：滚刷照片 → findings 命中 (滚刷, 缠绕) → rv_suction_hair_wrap 先验提升且 synthesize 引用证据；模糊图 → retake_card → 跳过继续
- [ ] 铭牌图 model_hint=「X10 Pro」→ disambiguate 单命中免追问
- [ ] 安全：烧焦图 observations 派生含 burnt → R4 升级（既有测试通过）
- [ ] `data/eval/vision/cases.yaml` ≥ 20 张；bake-off 新 schema 对 deepseek / qwen-vl / glm-v（及 sonnet / gemini 若有 key）重跑并更新 models.yaml 链序
- [ ] 前端 `RetakeCard.tsx`：原因、拍摄指引、上传 / 跳过

**设计依据：** 06 §1；00 D-L3-11
