# S4 设计：官方 Q&A 作为唯一知识源

来源：2026-10-08 只读调研（统计均对 `data/official/*.yaml` 实测）。开发开始后本文不改；勘误写 addendum.md。

## 结论

现有排障链路以手写 `config/plans.yaml` 为骨架，WeKnora 只给计划提供证据与排序（`diagnose/synthesize.py:40` 把 plan_id 收窄为计划枚举）。改为由 `qa.yaml` 确定性派生 QAIndex（错误码 / PN / 类型 / 步骤 / 媒体），在进程内生成「指南」，替代 plans / fault_cards / symptom_taxonomy；不再从 Q&A 反向生成 YAML。

## 1. PN 产品目录

- `config/products.yaml` 重写为约 8 行，契约字段 `sku` 的值改为 PN（前端与契约不变）。
- 名称取 Q&A 三级目录；别名取订单 description 与工单 product_name；品类取二级目录（iPath Navigation Series / Breast Pump / SoloCam → robot_vacuum / breast_pump / security_cam）。
- 附属 PN 进 `kb_pns`（T2071/T2070 → S1 Pro；T8171-3/T8162/T8123/T8124/T8130 → S340；T8D02/T8D03 吸奶器配件）。
- C10（T2292）只有 1 条 Q&A：`kb_coverage: minimal`，排障无命中直接 R5，订单物流照常。
- SKU → PN 归一：`T\d{4}` / `T8D\d\d`；T1 的 `E235311B` 容错为 T2353。
- S1 Pro 消歧：文本 PN、多语种品类词（robotstofzuiger / aspirateur / Saugroboter / borstkolf / tire-lait / Milchpumpe / sacaleches）、错误码反查 PN（EB1L 只属 T2080）任一可直接锁定。

## 2. 错误码 + PN 精确索引（先于语义检索）

- 标题抽码必须带锚点：码位于 `has|reports (a )?(warning|error|alert|toast)|error` 之后，或紧跟 `: / - / Error`；形式 `\d{4}` 或 `E[0-9A-Z]{1,3}`；多码以 `/`、` or `、`,` 分隔。避免把机型名 Omni E25 / E28 当成 S1 Pro 的 E25 / E28 码。索引键 `(pn, code) → [qa_id]`，约 418 键。
- 工单抽码：多语种字段名（Problem Code / Probleemcode / Fehlercode / Code du problème / Código）取开头 4 位；S1 Pro 的 8 位内部号忽略，改从 Problem Push / 描述开头 `E..:` 取码。
- 原型：18 单带码工单 17 单唯一命中；T13 的 5116 未收录。
- 未收录码：不做语义近邻，也过滤「标题带其他码」的语义命中；如实告知，追问现象或 R5。

## 3. Q&A → 指南

| 形态 | 条数 | 处理 |
| --- | --- | --- |
| ≥2 条编号步骤 | 335 | 每步一张步骤卡 |
| 无编号 / 单步说明 | 478 | 产品咨询、解释，走 reply 回答 |
| 纯「hardware malfunction / offer our warranty service」 | 58 | 跳过排障，直接进质保分支 |
| 先步骤、末步写硬件故障 | ≥4 | 该步 not_solved 进质保 |

- 步骤解析：`^[\s*•-]*(?:Step\s*)?\d{1,2}[.)、:]`，后续非编号行归入该步；Tips（50 条）进 caution；要求发图或视频的 38 条标 `asks_media`。
- 质保标记：`hardware malfunction|offer (you )?our warranty service|provide warranty service|ship (you )?a replacement|arrange (a )?replacement|replacement part`；build 输出分类报告，误判用 `config/qa_overrides.yaml` 按 qa_id 修正。
- Guide / GuideStep 替代 Plan / PlanStep，契约 `TroubleshootStep` 不变：`plan_id=qa_rv_0147`，`instruction_src=evidence:qa-rv-0147#s2`，主引用即该 Q&A；anchors 作废。
- 推进一律线性：solved → DONE；not_solved / cannot_do → 下一步；末步 → EXHAUSTED；带质保标记的步 → WARRANTY。删除 observations 机制。
- R1 由「满 4 步转人工」改为「指南耗尽 → 询问换货 / 退款」（SOP：排障完仍未解决 → 换货）；R1c 放宽为跨指南累计 10 步的防失控。
- 发布原样英文审核原文；客户可见译文由只翻译任务生成，校验数字与 URL 保留，原文折叠为引用。约 29 条客服口吻改第二人称。3 条 `visible: false` 不对客户输出。

## 4. 候选来源

- 精确码命中 → 该条 Q&A；否则 PN 范围内语义 top-k，`synthesize` 枚举改为本轮检索到的 qa_id。
- 低置信且分歧 → 候选现象选择卡（选项 = Q&A 标题 + 都不是），替代判别题。
- `fault_class`：warranty 标记或指南耗尽 → hardware；R4 → safety。

## 5. WeKnora

- 不用 FAQ 库（v0.8.0 FAQ 库检索返回空，`knowledge/faq.py:3-4`）；新建文档库 `haike_kb_qa`，一条 Q&A 一个 knowledge，content = 标题 + 正文（URL 换成 `[image n]`），metadata 标量 `qa_id, pn, codes, sheet, kind, category, doc_version`。
- 分块按库配置：chunk_size≈1500、关闭父子（正文中位 432 字、p90 1143、最长 2437）。
- 删除 tickets 库；63 单是评测集，不入库。
- 多语言：text-embedding-v4 需用荷兰语 T18 / T22 / T36 / T37 实测；查询拆两路（intake 输出的英文现象 + PN 名，原文），RRF 合并。WeKnora 不可用时在 QAIndex 上做英文标题词法兜底。

## 6. 媒体

470 个 URL（cloudfront 325、support.eufy.com 63、YouTube 10）解析为每步 `media[]`，卡片展示，不进模型上下文；一次性 HEAD 可达性检查，不作运行时依赖。

## 7. 实施顺序

1. QAIndex（离线）+ 分类报告；测试：17 单唯一命中、5116 空、E20 抽出且 E25/E28 机型名不误抽、rv-0481 五步、rv-0273 第 2 步质保标记。
2. PN 目录 + SKU→PN 归一。
3. 首封确定性解析最小版（PN / SN / 码 / 多语种字段），63 单表驱动。
4. GuideLibrary 替换 PlanLibrary（guide / verify / decide_next / R1 / fault_class）。
5. retrieve 重写：精确码 → 语义 → 候选 qa_id 枚举 → code_miss 走 R5。
6. `kb_qa` 入库 + 适配器 + 检索评测（自由描述工单 T20 T31 T34 T36 T37 T39 T40 T43 T54 T57 T61 T62 标金标，按语种 recall@5）。
7. 删除旧模块 / 数据 / 测试 / 回放，grep 门禁 `EUFY-|ANKER-A|SOUNDCORE-|\b(rv|bp|pb|chg|eb|spk|cam|hd)_[a-z]` 为 0。
