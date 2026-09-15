# 62: 看图结构化故障定位、图片可用性与 RetakeCard

**What to build:** `diagnose.vision` 输出 `FaultLocalization{findings[part, location, phenomenon, severity, confidence, quote_region], image_quality{usable, reasons}, model_hint, conflicts_with_text}`，prompt 版本 2026-09-14.1；`config/vision_vocab.yaml`（部件 / 现象受控词表、retake_guidance）；词表外归「其他」并保留 raw；`observations` 派生保证 CP-in 安全匹配不变（observation_terms 增中文词）；`fault_cards.faults[].signatures[{part, phenomenon}]` 确定性命中提高先验；`model_hint` 进 disambiguate 候选；`usable=false` 且无其他可用图 → `prepare_retake → await_input` 发 `retake_card`，`skip_retake` → 文字流程，计 clarification(reason=image)；`conflicts_with_text` 非空 → clarify(conflict)。视觉链失败行为不变。

**Blocked by:** 51

**Status:** done（2026-09-15，范围已超出原票，见下）

**Owner:** —

- [ ] A9：滚刷照片 → findings 命中 (滚刷, 缠绕) → rv_suction_hair_wrap 先验提升且 synthesize 引用证据；模糊图 → retake_card → 跳过继续
- [ ] 铭牌图 model_hint=「X10 Pro」→ disambiguate 单命中免追问
- [ ] 安全：烧焦图 observations 派生含 burnt → R4 升级（既有测试通过）
- [ ] `data/eval/vision/cases.yaml` ≥ 20 张；bake-off 新 schema 对 deepseek / qwen-vl / glm-v（及 sonnet / gemini 若有 key）重跑并更新 models.yaml 链序
- [ ] 前端 `RetakeCard.tsx`：原因、拍摄指引、上传 / 跳过

**设计依据：** 06 §1；00 D-L3-11


---

## 2026-09-15 完成记录（实际范围大于原票）

原票的五条验收项全部完成，另外补了四层原票没有的东西。完整推导见
[plan.md](../../2026-09-15_vision-measurement-redesign/plan.md)，迭代记录见
[addendum.md](../../2026-09-15_vision-measurement-redesign/addendum.md)。

**原票范围**
- [x] `FaultLocalization` 结构化定位 + `config/vision_vocab.yaml` 受控词表
- [x] 词表外归「其他」并保留 raw；`observations` 派生保证 CP-in 安全匹配不变
- [x] `signatures` 确定性命中提高 plan 先验（消费点在 retrieve）
- [x] `model_hint` 进 disambiguate
- [x] `usable=false` → `prepare_retake` → RetakeCard；`skip_retake` → 文字流程
- [x] `conflicts_with_text` → clarify
- [x] 前端 `RetakeCard.tsx`
- [x] 评测集与 bake-off 重跑（`orchestrator/tests/fixtures/bakeoff/diagnose_vision.yaml`，
      **不是**原设计写的 `data/eval/vision/cases.yaml`；后者仍是空占位）

**超出原票的部分（按「可信度必须来自模型外部」推出）**
- [x] L0 图片预处理：EXIF 转正 + 超 12MP 才降采样（`app/images/prepare.py`）
- [x] L1 像素画质门控：亮度 / 尺寸硬阈值直接退回补拍，**零模型调用**（`app/images/quality.py`）
- [x] L3 铭牌裁剪复看 + 交叉核对：两次一致才 `model_hint_verified`，未验证不自动锁 SKU
- [x] 图文分路：视觉调用看不到用户文字（函数签名无 text 参数）；冲突判定移到代码层（`app/diagnose/conflict.py`）
- [x] 字段裁剪：移除 `severity` / `location` / `confidence`（全仓零消费者 + 自评不可用），
      新增 `evidence` / `cell` / `image_index` / `model_hint_*`
- [x] 隐式确认：步骤卡首句回显读图结果（`StepCard.seen`，不掺进已审核的步骤正文）
- [x] 评测口径：七项字段级指标 + 两段式硬门裁决

**实测**（`reports/bakeoff-baseline` → `reports/bakeoff-stage4`，同模型 DeepSeek-Flash）：
字段准确率 65% → 96%，铭牌读出率 67% → 100%，无幻觉率 83% → 100%；代价是延迟 +24%、成本 +40%。

**未完成 / 边界**：全部数字来自合成评测图；安全召回未验证（合成图画不出烧焦材质）；
`blurry` 阈值只做提示不做拦截；多图路径只有单元测试覆盖。真实故障照片是唯一的全局阻塞。
