# 海客链路 B：改写、召回排序与诊断上下文评估

日期：2026-09-18。只读源码分析，未改实现、配置或数据库，未调用真实模型。完整阅读 `sessions/graph.py`（2,810 行）及关联 query/rewrite/config/grade/synthesize/decision/search/adapter/rerank、guide/steps、统一 context 与 ModelRouter。下文配置值来自仓库文件，未读取 `.env`，不把仓库默认值当作已核实的线上生效值。

结论：值得借鉴 WeKnora 的“保留足够候选，再排序，再组装完整上下文”；不宜照搬整库检索或默认每轮模型改写。海客已有产品范围、已审核计划和引用锚点约束，应保留。优先处理候选过早截断、补救只识别“没有相关命中”、两轮证据没有统一选择这三处；只开启 rerank / grade / parent_expand 不足以解决。

## 1. 当前链路与 WeKnora 的边界

链路 B 在应用侧编排检索与诊断，调用 WeKnora 的 `hybrid-search` 取候选；它没有运行 WeKnora Quick Answer 的 query_understand → chat_completion，也没有运行原生 ReAct Agent。诊断模型从已允许的预写计划中选择，用户收到的操作文本来自已审核计划原文。[检索编排](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/search.py:108)、[计划选择](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/diagnose/synthesize.py:132)、[步骤发布](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/guide/steps.py:116)

```text
当前用户输入 + issue 有效事实 + 已确认产品
               |
    understand / disambiguate / 可选 vision
               |
    build_query：产品 + 症状规范词 + 有效症状
               |
               +---- 本地故障卡匹配 ---------------------+
               |                                        |
    KnowledgeScope 限定可检索 knowledge_ids              |
               |                                        |
    原 query（可选同义变体）× 手册库 / 工单库，并发          |
               |                                        |
    adapter：请求 3*top_k → 每库截 top_k/字数               |
               |                                        |
    每库多查询 RRF → 每库截 top_k → 可选每库 rerank         |
               |                                        |
    跨库按名次交错，反证工单排后                           |
               |                                        |
    可选 grade：前 8 条，每条 200 字，过滤 irrelevant       |
               |                                        |
    至多一次补查：图片观察优先；否则满足无相关命中条件后改写 |
               |                                        |
    第二轮不 rerank；按 ID 去重，第一轮在前、第二轮追加      |
               |                                        |
    可选手册父块扩展 → 当前证据集合 <----------------------+
               |
    synthesize task_data：前 12 条，子块300字/父块800字
               |
    ModelRouter.prepare_messages / build_context
    + 产品、有效事实、已执行步骤、近期历史、本轮原话
               |
    允许计划内排序 → guide 校验 → 已审核步骤卡
               |
    锚点未被召回：补发 approved_plan 原文并记录来源
```

仓库当前 `query_rewrite/multi_query/faq/rerank/parent_expand/grade` 均为 `false`，`top_k=5`。因此通常是一个规范化 query 并发查两个库；**图片补查不依赖 query_rewrite 开关**，有观察且预算允许仍会触发。[配置](/Users/xiaoke.zhou/Documents/workspace/anker-haike/config/retrieval.yaml:3)、[图片分支](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/sessions/graph.py:1853)

## 2. 查询不是简单把最新一句送向量库

`build_query` 是确定性函数：确认 SKU 时取产品名（无名字才用 SKU），只确认品类时取品类中文名；加入 `symptom_codes` 对应故障名称和有效 `symptoms`，清空白并去重；只有症状为空才回退当前原话。unknown 返回空串。例：已确认 Q45、有效症状“电池掉电很快”，构造带产品词的检索表达；不会直接复制本地 WeKnora 会话那种无产品范围的全库问题。[query.py](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/diagnose/query.py:51)

产品约束另由 `KnowledgeScope` 执行：confirmed_sku 只允许同品类的该 SKU 文档与通用品类文档；category_only 只允许通用品类文档；允许集合为空时不发 HTTP 请求。实际命中再按 knowledge_id 后过滤。模型改写不能更改 scope。[scope](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/adapter.py:198)、[请求与后过滤](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/adapter.py:311)

这比本地 WeKnora 案例不区分耳机/充电宝/摄像头地合并搜索更适合售后。可借鉴它的上下文消歧能力，但海客已经由 issue 事实、症状规范化和产品消歧承担大部分职责，不能据此认定必须对每条消息先做 LLM 改写。

## 3. 首轮候选在哪里丢失，rerank 能救什么

默认每库 `top_k=5`，adapter 向 WeKnora 请求 `match_count=15`；但收到后立即将正文截为 `snippet[:400]`、反证排后、`hits[:5]`，随后执行每库 2,000 字预算。`total_hits` 在 top_k 截断以后计算，`truncated` 只表达字数截断，不能完整代表服务原始返回的 15 条有多少被丢弃。[adapter.py](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/adapter.py:318)

启用 multi_query 时，每个变体也先经历上述截断；本地 RRF（Reciprocal Rank Fusion，按各结果中的名次倒数相加）融合后又截至每库 top_k。可选 rerank 随后才执行，输入只有这些命中的 `snippet`，没有完整子块和标题；只重排手册、工单两库，FAQ 不走这一步。两库 rerank 在 for 循环内依次 await。[RRF](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/search.py:33)、[rerank 调用](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/search.py:198)、[模型文本](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/rerank.py:75)

跨库 `interleave_kbs` 重新依据**库内名次**排序，同名次按手册 > FAQ > 工单破平，反证在末尾；不直接比较 WeKnora RRF 与 rerank 等不同量纲的分数。这是合理的保守设计，但意味着 rerank 改善的是库内名次，不是全局相关性排序。[跨库排序](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/search.py:214)

具体限制：正确片段若为某库初始第 6 名，开启当前 rerank 也看不到它；把错误片段从第 3 名换到第 1 名或反之，不能替代扩大有效候选池。应把 `candidate_k`（召回候选数）、`final_k`（排序后保留数）和 `context_budget`（模型输入预算）拆开；保留完整子块作排序输入，展示摘要单独截断，再比较“库内重排后交错”与“受来源约束的统一重排”。全库统一重排是待评测选项，不能直接宣称更优。

## 4. 补检索的真实触发条件

当前 grade 是相关性评分加硬过滤，不是已实现的充分性补救策略。它最多评前 8 条命中，每条仅 200 字，输出逐条 relevant/irrelevant/unsure 和整体 coverage；正常图路径的父块扩展在 grade 之后，因此 grade 通常看不到扩展正文，也看不到稍后加入的故障卡。[grade 输入](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/diagnose/grade.py:127)、[graph 顺序](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/sessions/graph.py:1800)

`apply_assessment` 删除 irrelevant，默认至少保留 1 条；没有被评到的命中继续保留。被删除的仍作为“检索到的来源”写 SSE/state.evidence，但不进入当前 round_evidence，因此“前端可见”不等于“诊断模型收到”。`keep_min=1` 保留的也不因此变成相关证据。[过滤](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/diagnose/grade.py:106)、[展示与诊断集合](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/sessions/graph.py:1978)

文本改写要求：开关开启、产品范围明确、不在澄清、尚有名额和预算、模型可用；有允许文档的库必须全部 no_match，部分库故障不当作正常空结果。grade 成功且 `relevant_ids` 为空时，仅为补查决策把 ok 临时映射为 no_match；**coverage=insufficient 并不触发补查**。只要还有一条 relevant，或者有故障卡命中，`has_hits` 就阻止改写。[触发函数](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/diagnose/rewrite.py:96)、[调用条件](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/sessions/graph.py:1843)

例：搜到“电池使用注意事项”，能判 relevant，但缺少“待机还是播放时掉电”的关键区分；即使 coverage=insufficient，当前也进入 synthesize。只开 grade 或 query_rewrite 都不能修复这条路径。

图片观察先占用同一个补检索名额；没有图片补查时才考虑文本改写。改写只产 query，代码检查新型号/错误码/数字、否定、未经支持的部件或原因、至少一个症状锚点；失败不再调用另一个模型裁判，不修改事实或 scope。[受控校验](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/diagnose/rewrite.py:174)

第二轮固定 `allow_rerank=False`；按 evidence_id 去重时首轮优先，新命中直接追加。可选第二次 grade 只有首轮已成功 graded 才可能执行，且只评新的命中；默认 `second_round=false`。已有 coverage 可能上调，但不是对合并后的完整证据集重新评估。[第二轮](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/sessions/graph.py:1536)、[合并](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/sessions/graph.py:1648)

已有 [quality-first-retrieval-rescue/spec.md](/Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-09-13_quality-first-retrieval-rescue/spec.md:1) 明确提出：以充分性决定一次补查、insufficient/none 都可补、故障卡参与判断、评分不硬删除首轮证据。这是**已有方案，当前代码尚未实现**，本次建议应接续该方案，不能把开启旧 grade 视为落地。

## 5. synthesize 实际收到什么

任务自己生成的 task_data 只包含：允许计划的 plan_id/故障名/首步标题、有效 symptoms、图片观察、前 12 条证据。每条证据有 evidence_id、source、工单结果标签和正文；正文为 full_text 前 800 字，否则 snippet 前 300 字。这里没有序列化 grade、score、knowledge_title、source_queries 或完整父块来源列表。[synthesize.py](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/diagnose/synthesize.py:118)

但这**不是最终完整模型输入**。`compose_system_prompt` 虽不再插入 state_summary，线上图节点由 `durable_node` 设置 turn_context，ModelRouter 统一重建上下文：

```text
durable_node(retrieve) -- turn_context.set(state)
        |
ModelRouter.invoke -- prepare_messages(task, messages, schema)
        |
build_context
  system：角色/任务规则 + 来源、状态、不同issue隔离规则
  human ：authority JSON
           product + active/disputed facts + steps_executed
           decision + symptom_interview + task_data(检索证据)
           conversation_view + issue索引等
  history：预算内近期完整轮次，默认近6轮
  current：带entry_id/时间/状态的本轮原话或动作
```

所以不能误报“诊断模型没有收到产品/历史/本轮原话”。完整证据链为 [durable_node](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/conversation/effects.py:61) → [Router](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/models/router.py:269) → [prepare_messages](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/context/runtime.py:16) → [authority 组装](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/context/builder.py:162) → [最终消息](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/context/builder.py:307)。直接脱离图调用 synthesize 的测试或工具不一定具有 turn_context，不能以这种局部调用代替线上输入审计。

真实限制是：task_data 在进入统一 context 前已裁切。默认首轮最多手册5+工单5=10条，第二轮新证据追加，synthesize 最多只看前12条；当首轮10条全部保留时，第二轮最多只有前2条可进入文本。若启用 FAQ 后首轮达13条，第二轮可能一条也进不去，后加的故障卡也可能被截掉。这里是静态上限示例，实际数量取决于命中和 grade，不能当作每轮实测数量。

统一 context 默认 8,000 token（intake 单独16,000），先为 schema 预留预算；task_data 属于固定 authority 内容。超预算时先去历史摘要缓存，再缩当前长原话，仍不够抛预算错误；它不会自动从证据池选一组更好的片段。因此需要在进入此层前做有来源、有轮次和支持/反证约束的上下文选择。[预算配置](/Users/xiaoke.zhou/Documents/workspace/anker-haike/config/conversation.yaml:1)、[预算处理](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/context/builder.py:241)

父块扩展只处理前若干手册命中，默认最多3组、每组800字；同 parent 的子块按 chunk_index 拼接、去重叠，没有 parent 时用相邻块。它发生在 evidence 事件生成后，只改内部 synthesize 输入；可以补上下文，不能救回召回或 grade 已删的候选。[扩展实现](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/adapter.py:269)、[调用顺序](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/sessions/graph.py:2008)

## 6. 分值、覆盖率、无命中不能混为一谈

| 字段 | 当前含义 | 不能推断 |
|---|---|---|
| Hit.score | 初始服务分；多查询后可变成本地RRF分；rerank后可变成相关性分 | 不是统一校准的正确概率，不能跨算法/来源直接比较 |
| evidence.score | Hit.score 被压到0–1；故障卡固定0.6；本地已审核计划固定1.0 | 1.0不表示真实召回最好，0.6不表示60%正确 |
| coverage | grade 对其有限输入给 sufficient/insufficient/none | 不是知识库覆盖率，不是召回率，也不是当前真正的补查开关 |
| no_match | scope为空未请求，或请求后过滤无命中；详情需看allowed_count | 不等于“整个库没有答案”；也不等于“命中全部不相关” |
| knowledge_status=ok | 图中仍有检索hits，可能含keep_min留下的irrelevant | 不保证足以支持诊断；fault_card单独命中也不会把外部库改成ok |
| confidence | synthesize模型选择计划的分值；默认计划固定0.3 | 不是检索相关性，也不是执行成功率 |

证据：[score 序列化](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/adapter.py:89)、[故障卡固定分](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/faultcards/library.py:86)、[图汇总状态](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/sessions/graph.py:1968)、[默认计划分](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/diagnose/synthesize.py:58)。单库 unavailable 的信息应以 per-kb trace 保留；图的聚合状态仅全部库 unavailable 才为 unavailable，无hits的部分故障可能聚合成no_match，但 rewrite 决策仍会拒绝该故障路径。

## 7. 有步骤、有引用，不代表检索有效

无证据、router不可用、模型调用失败、输出全部假设不合法/无有效证据ID时，synthesize 返回允许计划的默认顺序，source=standard_flow、confidence=0.3。`filter_hypotheses` 验 plan_id 与 evidence_id 白名单，不能证明证据语义支持计划；未解决工单“只作反证”的限制还依赖任务指令。[降级与校验](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/diagnose/synthesize.py:74)

guide 的主引用先在 state.evidence 中识别同文档的精确锚点/标记/原文；找不到就发布 `source=approved_plan` 的已审核原文，score=1.0，并记 `anchor_not_retrieved`。这是保证操作依据可查的独立能力，发生在排序结束之后；**它不会把原文倒灌给前面的 synthesize，也不证明该原文被 WeKnora 召回**。同理，故障卡 evidence 是本地匹配结果，应单独归因。[主引用补充](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/guide/steps.py:187)、[图记录](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/sessions/graph.py:2230)

因此评测需同时看：正确计划/步骤、检索锚点真实命中、补查产生的有效新增证据、模型实际引用的支持度、standard_flow/fault_card/approved_plan 兜底比例。仅比较“最终有几条引用”会掩盖召回问题。

## 8. 修改优先级与可选复杂度

1. **先把候选池和展示/模型预算拆开。** 当前第6名无法进入rerank，是源码可确定的能力上限。保留排序所需完整子块和标题，候选截断放到排序以后；trace区分原始返回数、范围过滤数、排序前候选数、实际上下文ID。这是让rerank评测有意义的前提。
2. **接续已写的充分性补救方案。** 评价完整的首轮候选与故障卡是否支持适用排障方向，insufficient/none可消耗一次补查；保留原候选，不把旧grade硬过滤当成新策略。保持已确认scope、否定与型号校验、两轮上限，以及外部服务故障的独立状态。
3. **两轮合并后统一选择模型上下文。** 至少防止首轮占满12条而第二轮/故障卡不可见；同时保留正证、反证、来源与轮次。可比较联合rerank、按轮次/来源配额的选择，先用同一标注集证明收益；不直接把“所有库统一一个分数”当作既定方案。
4. **再单独评估 rerank 与父块扩展。** rerank解决候选排序，parent解决已命中片段的上下文缺失，两者各自开关、各自归因；保留海客的范围隔离与工单结果标签，不复制 WeKnora 案例中跨SKU/结果去重与调用方遗漏metadata的问题。

可选复杂度：首轮LLM改写、更丰富多查询、独立FAQ召回、第二轮再次grade、图检索和自主工具循环。当前没有证据表明需要同时引入；先做候选与充分性/上下文修正，避免复杂度掩盖实际增益。

预算也要作为一个整体调整：当前文本run默认25秒；rerank需剩余≥5秒、每库HTTP超时配置2秒；grade需≥6秒/最多4秒；rewrite需≥8秒/最多3秒；第二轮最多3秒；synthesize最多8秒且为后续留约2秒。graph依据输入接收时间和固定25秒计算，runner另有自身deadline；只放宽一个模型超时不能消除前面的跳过条件。若采用既有“效果优先”规格，应统一这些门槛、deadline及取消/恢复口径，仍保持有限调用次数与超时。[graph预算](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/sessions/graph.py:1485)、[runner](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/sessions/runner.py:28)、[当前阈值](/Users/xiaoke.zhou/Documents/workspace/anker-haike/config/retrieval.yaml:32)

本次没有执行A/B或真实会话，因此上述是源码确定的流程限制与待验证优化优先级，不是已经测得的效果提升。
