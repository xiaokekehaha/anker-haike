# 剩余工作总清单（2026-10-08）

来源：全仓残留扫描（旧 SKU / 计划 id / 旧知识库 / 中文写死 / 评测回放 / 前端 / 文档 / CI）+ 本会话计划。开发开始后本文只追加勾选，不改写；勘误写 addendum.md。

当前状态：
- 已提交：S1 官方数据、S2/S3 订单质保物流服务单（805cc56）、规划文档（b74d6aa）。
- 工作树未提交：产品目录 8 PN、QAIndex（错误码 + PN 精确索引、Q&A → 指南）、首封解析（message.py）、WeKnora `haike_kb_qa` 入库（872 条，旧三库已删）、adapter/search 单库化、Makefile kb-ingest 末尾 REINDEX。
- 全量后端测试：133 failed / 10 errors（911 passed），全部集中在下面 B1–B4 尚未替换的旧排障链路及其测试。

说明：严重度 **阻断**＝不做则真实工单跑不通或演示出错；**必要**＝赛题能力 / SOP 要求；**收尾**＝清理与文档。

## A. 知识库

| # | 项 | 状态 | 严重度 |
| --- | --- | --- | --- |
| A1 | 官方 Q&A 入库 haike_kb_qa（一条一知识、1500 字不父子、元数据 pn/codes/kind） | 完成 | — |
| A2 | 删除旧三库（manual / faq / tickets） | 完成（快照 20261008T062043Z） | — |
| A3 | 批量删除后 BM25 索引失效 → kb-ingest 末尾 REINDEX | 完成 | — |
| A4 | 删除旧语料目录：data/knowledge/kb_manual、kb_tickets、scripts/gen_tickets.py、sources/anker_official.yaml、snapshots 中旧快照（保留 20261008 一份） | 待做 | 收尾 |
| A5 | 删除旧知识模块：faq.py（LocalFaqIndex）、official.py、official_verify.py、anchors.py、reachability.py；ingest.py 先抽出 sku_list_of / EMBEDDING_DIM / IngestReport / wait_parsed / write_manifest 再删其余 | 待做 | 必要 |
| A6 | search.py / adapter.py 去掉 kb_faq 分支、counter_evidence / case_outcome（工单反证）死代码 | 待做 | 必要 |
| A7 | snapshot.py 改为按 kb_qa 导出 / 导入（或删除，导入本身已幂等可重建） | 待做 | 收尾 |
| A8 | haike-kb CLI：删 anchors 子命令、kb_faq 特判；search 子命令改单库 | 待做 | 收尾 |
| A9 | 检索评测：data/eval/retrieval 换成「自由描述工单 → 金标 qa_id」，按语种统计 recall@5；eval.py 去旧库逻辑 | 待做 | 必要 |
| A10 | 中文客户查询的跨语言召回：客户写中文时检索英文 Q&A，需验证或加英文现象改写 | 待做 | 必要 |

## B. 后端：排障链路（替换手写计划）

| # | 项 | 状态 | 严重度 |
| --- | --- | --- | --- |
| B1 | GuideLibrary 取代 PlanLibrary：Q&A 指南（steps / answer / warranty）生成 plan 视图；guide/steps.py 原文与主引用改取 Guide.Step（qa_id 即主证据）；verify 线性推进；observations 机制删除 | 待做 | 阻断 |
| B2 | 删除 config/plans.yaml、fault_cards.yaml、symptom_taxonomy.yaml 及 app/faultcards、app/plans/store、conversation/taxonomy；settings / Dockerfile 去 PLANS / FAULT_CARDS 路径；main.py 启动校验改为 QAIndex 加载 | 待做 | 阻断 |
| B3 | retrieve 重写：首封解析的 PN 锁产品、错误码先查 QAIndex 精确命中；未收录码不套相近码（T13 5116 → 追问 / R5）；无码走 kb_qa 语义检索，synthesize 枚举改为本轮候选 qa_id | 待做 | 阻断 |
| B4 | 症状判定：去掉症状码 / 判别题；无码无现象时追问一次现象；候选分歧时出「候选现象」选择卡（Q&A 标题 + 都不是） | 待做 | 阻断 |
| B5 | 质保类条目（63 条 warranty + 步骤里带质保标记）→ 跳过 / 结束排障直接进 L3 质保判断（T14 4090） | 待做 | 阻断 |
| B6 | R1 改为「指南耗尽 → 询问换货 / 退款」，R1c 放宽为跨指南累计 10 步 | 待做 | 必要 |
| B7 | 首封解析接入 intake：PN → product_confirmed（S1 Pro 同名直接锁定），SN → SOP 证据，订单号 / 国家 / 商家 → 业务上下文与经销商判定，language → 回复语言 | 待做 | 阻断 |
| B8 | vision_vocab 拆分：保留 quality / retake 段（images/quality.py 依赖）；signatures → rv_ 计划映射删除；diagnose/localization 跟改 | 待做 | 必要 |
| B9 | rewrite.py / expand.py 的错误码与灯态正则换成 QAIndex 抽取；retrieval.yaml 中文同义词与 faq 段删除 | 待做 | 必要 |
| B10 | operation_conditions / clarify / intake 示例里的充电宝、耳机等旧品类词；「S1 Pro」现为扫地机 + 吸奶器双义，intake 示例重写 | 待做 | 必要 |
| B11 | seed_cli：删 plans / fault_cards seed 与 plans-schema；products seed 保留；数据库 plans / sku_fault_cards 表由迁移删除 | 待做 | 收尾 |
| B12 | 情绪 / 投诉词（complaint_terms.yaml）补英荷德法西；操作条件回复词表多语 | 待做 | 必要 |
| B13 | 安全 R4 前置：Q&A 步骤里的高危动作（拆解、断电等）与 caution 校验沿用 rules，确认对英文步骤生效 | 待做 | 必要 |

## C. 后端：多语言回复（D2）

| # | 项 | 状态 | 严重度 |
| --- | --- | --- | --- |
| C1 | 契约：消息事件 / 快照加 `language` 与 `translation_zh`；步骤卡加原文 + 译文；make contracts | 待做 | 必要 |
| C2 | prompts（system / reply / guide）去掉「用中文」，按客户语言输出；system 角色层去掉 20 品类表述 | 待做 | 必要 |
| C3 | 固定模板（l3.py 约 23 处 say、logistics.py、gate 证据标签、receipt NEXT_STEP、clarify FIXED_QUESTIONS、graph closing_text、reply ACK / OFFER_HUMAN、answers LABELS）改为按语言渲染：中英两套写死 + 其余语言模型翻译（校验数字 / 订单号 / URL 不变） | 待做 | 必要 |
| C4 | Q&A 英文步骤原样发布 + 客户语言译文（只翻译任务，不改写含义）；约 29 条客服口吻改第二人称 | 待做 | 必要 |
| C5 | 转人工摘要、后台保持中文 | 不改 | — |

## D. 评测与回放

| # | 项 | 状态 | 严重度 |
| --- | --- | --- | --- |
| D1 | 63 单评测集：每单标意图、SOP 分支、语言、首张步骤卡 qa_id 或终点（补发单 / 调查单 / 质保拒绝 / 换货单 / 转人工）、禁止承诺；确定性评估 + 模型抽检 | 待做 | 必要 |
| D2 | data/eval：删 symptom；conversation / intent / routing 金标里 DEMO 编号与旧产品替换、补多语样本；evaluation/cli.py KINDS 同步；.github backend.yml 的 haike-eval all 同步 | 待做 | 必要 |
| D3 | bakeoff：tests/fixtures/bakeoff 10 份旧产品 / 旧计划 fixture 重写；bakeoff 报告作废重跑 | 待做 | 收尾 |
| D4 | replay：a1–a8 录制包与 scenarios.py 删除，按 D6 主案例（T55）与分支（T8、T2、T29、T45、T14、T13）重写场景并重录；replay/cli.py 的 confirm_context 分支删除 | 待做 | 必要 |
| D5 | inspection：scenarios.py 37 个场景与 harness 用 X9 / EUFY- / rv_ / kb_manual，改为官方 PN 与 Q&A；product_ambiguity 期望按 S1 Pro 双候选 | 待做 | 必要 |
| D6 | 单测：63/103 个文件引用旧数据；随 B1–B4 删除或重写（test_knowledge_faq / official / anchors / ingest、test_faultcards、test_plans 直接删） | 待做 | 阻断（CI） |
| D7 | data/demo-photos 4 张合成图 → 改用 data/official/attachments（test_rules 引用） | 待做 | 收尾 |
| D8 | contracts samples / fixtures 中 category=charger 样例 | 待做 | 收尾 |

## E. 前端

| # | 项 | 状态 | 严重度 |
| --- | --- | --- | --- |
| E1 | 首屏品类 chip：20 个旧品类 → 3 个（扫地机 / 吸奶器 / 安防摄像头），改为后端下发目录 | 待做 | 阻断（演示） |
| E2 | 示例 prompt 与输入框占位：充电宝 / 耳机 → 真实工单原文（英文、App 报告格式、荷兰语各一） | 待做 | 阻断（演示） |
| E3 | 「载入真实工单」入口：选 T1–T63 作为首封消息（含附件图），演示与回归共用 | 待做 | 必要 |
| E4 | 双语显示：客户语言原文 + 中文译文（消息、步骤卡），配 C1 契约 | 待做 | 必要 |
| E5 | 步骤卡：展示 Q&A 的图片 / 视频（Step.media），引用指向 qa_id；证据抽屉 SOURCE 加「官方 Q&A」，删 kb_manual / kb_tickets / fault_card / approved_plan | 待做 | 必要 |
| E6 | record.ts、admin Sessions 品类标签与筛选跟随新目录；Board / Sessions 按 plan 维度的筛选改为 qa_id | 待做 | 必要 |
| E7 | 前端测试：StepCard / ObservationCard（pb_737）/ admin / pages 等约 13 个测试文件旧数据 | 待做 | 阻断（CI） |
| E8 | 候选现象选择卡（B4）复用 ProductCard 或 ObservationCard 样式 | 待做 | 必要 |

## F. 文档、CI 与部署

| # | 项 | 状态 | 严重度 |
| --- | --- | --- | --- |
| F1 | README：产品范围、官方数据来源、演示用例、版本锁定补数据版本（official sha、kb_ver） | 待做 | 收尾 |
| F2 | docs/runbook/l3-demo.md、database.md 仍写 DEMO 订单 / backends_mock / seed backends | 待做 | 收尾 |
| F3 | docs/runbook/official-knowledge.md 改写为官方 Q&A 入库与 REINDEX 说明 | 待做 | 收尾 |
| F4 | Makefile：删 kb-official-*、kb-anchors、seed plans / fault_cards、plans-schema | 待做 | 收尾 |
| F5 | docker-compose：删 ./data/knowledge/kb_manual 挂载；Dockerfile 删 PLANS / FAULT_CARDS 环境变量 | 待做 | 必要 |
| F6 | scripts/release.sh / release-check.sh 版本表：plans / symptom_taxonomy → products / official qa / kb_ver | 待做 | 收尾 |
| F7 | deploy/observability/smoke.py 用 kb_manual / rv_ 计划 | 待做 | 收尾 |
| F8 | 全部完成后跑 scripts/ci-local.sh；grep 门禁 `EUFY-|ANKER-A|SOUNDCORE-|\b(rv|bp|pb|chg|eb|spk|cam|hd)_[a-z]|kb_manual|kb_tickets` 为 0 | 待做 | 收尾 |

## 执行顺序

1. B1 + B2 + B3 + B5（替换排障链路；同一批改，单独提交）→ D6 对应单测同批改；A5 / A6 / B8 / B9 顺带。
2. B4 + B6 + B7（首封解析接入、症状判定、R1 语义）。
3. E1 + E2 + E5 + E6 + E7（前端目录与步骤卡，不依赖多语）。
4. C1–C4 + E4（多语回复与双语显示）。
5. D1 + D2 + E3（63 单评测集与载入工单入口）。
6. D4 + D5 + D3（回放、巡检、bake-off 重做）。
7. A4 / A7 / A8 / B10–B13 / D7 / D8 / F1–F8 收尾，跑 ci-local 与 grep 门禁。
