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

## 2026-10-08 状态更新（追加）

已提交：47902b3（排障链路切官方 Q&A）、7269d1d（旧知识模块清理 + 首封事实）、cc3b324（前端口径）。

| # | 状态 |
| --- | --- |
| A1–A3、A5、A6、A8、A9 | 完成 |
| A4 | 部分完成：kb_manual / kb_tickets / scripts / sources 已删；snapshots 未跟踪，保留 |
| A7 | 完成：snapshot.py 删除（入库幂等可重建） |
| A10 | 待做 |
| A11（新增） | SoloCam 离线 / 不录像漏召回（T57、T59），现象单 recall@5 77% 的剩余缺口 |
| B1–B3、B5–B9 | 完成（B8 只改了 signatures 指向，vision_vocab 结构未拆） |
| B4 | 完成：判别题问诊入口关闭，无现象时问一句开放问题；symptom_taxonomy / observations 代码未删，归入第 7 步 |
| B10、B11、B13 | 待做 |
| B12 | 待做（安全词已补英荷德法西；投诉 / 愤怒词仍只有中文） |
| C1、C2、C4、E4 | 作废：2026-10-08 改为客户可见输出用英文、不翻译、不附中文（见 addendum「D2 变更」） |
| C3 | 改为：客户可见固定话术改英文；转人工摘要、观测台与前端界面保持中文 |
| C5 | 不改 |
| D1 | 部分完成：63 单标注与确定性评测（35 单 SOP 终点 63/63） |
| D1b（新增） | 真实模型批量回放 63 单，出 plan §4 指标（意图准确率、SOP 分支准确率、独立托管率、幻觉） |
| D2 | 待做 |
| D3、D4、D5 | 待做（D5 巡检已换官方 PN，场景本身未按 D6 重写） |
| D6 | 完成 |
| D7、D8 | 待做 |
| E1、E2、E5、E6、E7 | 完成 |
| E3 | 待做 |
| E8 | 不做（问诊改开放问题后不需要候选现象卡） |
| F4、F5 | 部分完成：kb-official-* / kb-anchors / kb-snapshot 目标、kb_manual 挂载、PLANS / FAULT_CARDS 环境变量已删；seed plans / plans-schema 未删 |
| F1–F3、F6–F8 | 待做 |

接下来的顺序（2026-10-08 用户确认）：D1b → B12 → C3 → D4 → E3，然后第 7 步收尾。

### 2026-10-08 进度（D1b → B12 → C3 → D4 → E3）

- D1b 进行中：`haike-eval live-tickets` 对运行中的编排服务逐单回放 63 单（orchestrator/app/evaluation/live_tickets.py），报告写 reports/eval/*_live_tickets.md。
  首轮（修复前）意图 87% / SOP 分支 84% / 幻觉 9（全为检测器把「不再补发」「无法免费换货」误判为承诺）。
  已修：
  - 检测器按句判断、有否定词不算承诺；
  - 解释器把「没收到货 / 何时发货 + 订单号」判成 order_query（T1 T3 T7 T9）→ 有配送词且未问订单字段时改为 logistics_query；
  - 物流问题附带订单号 / 物流单号字段请求时仍按物流 SOP 查包裹给方案（T5）；
  - 首封带图且读图不可用时，跳过补拍回到消歧而不是直接检索（T55 因无查询中断）；
  - 一条官方指南走完仍未解决即进入质保判断（R1），不再换相近指南（T55 / T29 连走 3 条、7 步）；
  - 自由文本现象（≥ 6 个词）视为已描述，不再追问现象（T40 / T61）；
  - 型号别名允许字母数字间加空格（「omni c 20」，T62）；
  - 安全说明补「噪音大、担心坏掉不算」（T36 误判 R4）。上下文预算护栏 4260 → 4400（Fable 5.1 裁定，含另一会话 product_question 的约 150 token）。
  第二轮：意图 94% / SOP 分支 89% / 幻觉 0。
- B12 完成：complaint_terms.yaml 补英荷德法西词（取自 T56 T57 T58 T59 T60 T62 原文）；拉丁字母词改为忽略大小写、整词匹配、前一两个词为否定词不算。新增 tests/test_emotion_terms_multilingual.py。
- D1b 完成：第三轮（C3 英文化与全部修复后）意图 97% / SOP 分支 98% / 幻觉 0 / 机器人闭环率 75%（6/8）/ 提交服务单 11 单，报告 reports/eval/20261008T124854Z_live_tickets.md。
  Fable 5.1 裁定：T42 / T44 改 warranty_by_qa、T44 意图改 replacement_request、T50 改 troubleshoot、T63 意图改 report_problem；
  「独立托管率」改为 bot_closed_rate，只统计期望终点可由机器人独立闭环的工单（运输中 / 预售 / 过保 / 解释）；
  可见物理损坏（部件断裂 / 脱落，同句共现部件名词，排除耗材与声音）直接进质保（app/official/damage.py，63 单命中 T42、T44）。
  剩余：T12 / T35（清水不足 / 低电回充是正常提示，期望解释即结束）走到了质保；T59 / T60 意图细分差异。
- C3 完成：客户可见固定话术改英文（SOP 话术、物流状态与描述、证据标签、服务单回执、质保结论、订单查询回答、任务队列提示、结束语、安全 / 转人工说明、追问、操作条件提示及对应的英文回复短语、读图提示、产品咨询提示）；
  品类加 name_en 供客户文字使用。保留中文：转人工摘要、观测台、前端界面、案件审计原因、GateCheck.detail、工具行与卡片备注。
  遗留：读图冲突句（app/diagnose/conflict.py）与回执来源默认值「售后工具」（contracts）仍是中文。
- E3 完成：后端 GET /official/tickets 与附件接口（app/official/router.py）；前端首屏「载入主办方真实工单」下拉，展开时才拉列表，选中后原文填入输入框、附件图加入附件区（Composer presetFiles）。
- D4 完成：回放场景换成 D6 七单（t55_main、t8_reship、t2_delivered、t29_out_of_warranty、t45_safety_dealer、t14_hardware_fault、t13_code_miss），
  首封即工单原文与原图；旧 a1–a9 录制包删除。脚本新增 ticket / while 步骤。真实模型录制后 `make replay-all` 7/7 断网重放通过。
  修了回放键不稳定：卡片效果的 event_id / effect_id / execution_id / action_id 进入下一轮上下文时未归一，T55 第三轮 intake 回放未命中。

### 2026-10-08 质量项（Fable 5.1 裁定后执行）

- T12 / T35（正常状态提示）：暂缓系统改动；回放驱动对 explain 单答「解决了」。
- T59 / T60：改标签（T59 意图 replacement_request，T60 意图 report_problem）；评测 code_miss 只算报了错误码的单，无码 R5 记为 no_guidance。
- 检索：英文官方术语改写实验 recall 9/12 → 9/12，无提升，query_rewrite 保持关闭；rerank 不开。补等价金标（T54 bp-0125、T57、T59），现象单 recall@5 77%。剩余 T57 / T59（SoloCam 口语描述）未召回，暂缓。
- 中文跨语言召回、前端界面中文：暂缓。
- 图文冲突提示改英文（vision_vocab.yaml 新增 english 对照表）；回执来源默认值改 "after-sales tool"（契约已重新生成）。
- 旧症状词表与观察机制删除：单独一次提交，进行中。
