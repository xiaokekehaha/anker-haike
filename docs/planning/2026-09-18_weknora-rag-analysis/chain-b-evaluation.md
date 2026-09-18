# 链路 B：海客检索改写、召回与排序的必要性评估

核对日期：2026-09-18。仅阅读源码、设计文档、既存评测报告与 JSON；没有调用模型、检索 API 或修改业务配置。本文中的 B 指海客调用 WeKnora 检索接口的链路；历史报告里的“B 组”特指 `multi_query + faq`，两者不要混淆。

**结论：现有证据不支持直接打开六个可选开关。优先借鉴的是分阶段处理、保留来源和范围约束、对子块排序后再补上下文；不宜直接复制 WeKnora 聊天管线的所有模型步骤。** 当前人工标注只有 2/58；旧对照来自更小的扫地机语料，部分指标会高估效果，且较新模型评测已推翻“改写准确率 100%”的旧依据。

## 1. 现有设计已经覆盖哪些借鉴点

海客设计采用代码控制的检索环：限制轮数、请求数、模型调用数与预算；相关性判断可以交给模型，是否继续、何时停止由代码控制。这不是缺一个通用聊天 Agent，而是已有有界编排中哪些步骤值得启用的问题。[设计定义](/Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-09-13_bounded-agentic-rag/design.md:7)

下图仅表示 **`eval.py` 评测入口的一轮流程**。真实 graph 在 grade 后判断并执行补检索，再做 parent_expand；下图不能代替生产编排图。

```text
评测原话 + 产品范围 + 预填 intake 症状
                    |
                    v
               build_query
                    |
           [可选：确定性多查询]
                    |
       +------------+-------------+
       |                          |
  手册范围过滤                 同 SKU 工单过滤
       |                          |
  WeKnora hybrid_search      WeKnora hybrid_search
  向量 + BM25 -> RRF        向量 + BM25 -> RRF
       |                          |
       +----- 多变体各库合并 ------+
                    |
          [可选：库内 rerank]
                    |
      各库按名次交错 / 反证排后 <--- [可选：本地 FAQ]
                    |
          [可选：父块扩展]
                    |
          [可选：grade 过滤]
                    |
         synthesize 选择故障计划

外层代码另行控制：是否允许补检索、最多两轮、超时、两轮证据合并。
既存 retrieval 评测只覆盖一轮；不覆盖整个外层环。
```

WeKnora 的 `hybrid-search` 已经完成向量与关键词的融合；海客若增加 RRF，应处理不同查询变体，不能把“补一套混合检索”当作尚缺功能。WeKnora 聊天路径中的 rerank、父块扩展不是该检索接口自动提供的步骤，海客必须自行选择是否调用。[上游源码分析](/Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-09-18_weknora-rag-analysis/upstream-retrieval.md:71)

## 2. 按开关给出判断

| 开关 / 能力 | 现有证据 | 当前判断与必要条件 |
| --- | --- | --- |
| `parent_expand`：把命中子块补成较完整上下文 | 单项对照第一条证据含目标标记 36→48 条；无新增模型调用；但总 chunk hit 都是 49/50，没有父块单项 synth 对照 | **最值得先做单项验证**。适合步骤跨块、表格或安全条件被截断的样例。开启前用当前多品类语料验证回答/计划提升、上下文预算和重复去除；不能把标记覆盖直接当作答案质量 |
| `faq`：接入 FAQ 答案源 | 历史人工核对发现许多正确 FAQ 未写入金标，`bin-01`、`chg-03` 已补标；但当前开关是本地 FAQ 索引，不是自动接入全部 WeKnora FAQ | **优先解决内容覆盖并单项评测**。先确认本地索引实际覆盖品类及新增 FAQ。历史“FAQ 取不到”是当时部署现象，不能作为永久绕过上游 FAQ 的依据 |
| `multi_query`：同义词生成多个检索问句 | 历史仅 14/56 样例实际生成变体；与 FAQ 绑定测试，doc hit 无提升；现有测试明确接受“小刷子”→“小滚刷”的部件漂移 | **暂不开**。先修词表的部件歧义与品类作用域，再对真实口语漏召回做单项对照。无需为了复制 WeKnora 改写而对每轮查询强制扩展 |
| `rerank`：对候选段落重新评分排序 | 修复跨库混分后 hit 仍 49/51；相对同配置无 rerank 组，p50 +416 ms、p95 +289 ms；没有独立 synth 收益证据 | **有排序错误时再验证**。当前更大的语料值得重评，旧“无收益”不等于永远没用；但先确认相关片段已在候选池，rerank 不能找回根本未召回的内容 |
| `grade`：模型判相关性并过滤 | 在相同三项开关基础上 plan 41/43→39/43，新增两个退化；7/56 调用失败；额外 p50 1578 ms | **保留关闭**。应先证明拒答/误命中明显改善且不删关键证据。也不能仅为触发 rewrite，先引入一个已有误删证据的模型过滤器 |
| `query_rewrite`：受控改写再检索 | 历史全库同时 no_match 0/56；较新 bake-off 为 75%/75%/62%，三家均未达 90%；retrieval CLI 本身不跑 rewrite | **保留关闭**。先收集真正应补救的漏召回和上下文省略样例，单独验证改写保真，再验证补救后的答案收益；“结构合法”不等于“检索改善” |
| `strict_terms` / `grade.second_round` | 旧严格校验拒绝 6/8 合理改写；第二轮 grade 未单独评测 | 继续 false；均无扩大复杂度的依据 |

开关状态及上限见 [retrieval.yaml](/Users/xiaoke.zhou/Documents/workspace/anker-haike/config/retrieval.yaml:3)。词表漂移有具体回归断言，不能假定融合必能吸收它：[测试](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/tests/test_diagnose_expand.py:50)、[词表](/Users/xiaoke.zhou/Documents/workspace/anker-haike/config/retrieval.yaml:17)。值得保留的确定性范围过滤和跨库按名次融合不依赖打开这六项。

## 3. 历史数字实际说明了什么

### 3.1 召回与排序：先区分混分错误，再比较重排

以下是修复跨库分数量纲后、同一批 56 条的对照。可评分为 51 条；其余 5 条按“无知识命中”计数。

| 报告 | 开关 | doc hit@5 | precision@5 | 无知识返回命中 | 检索 p50 / p95 |
| --- | --- | --- | --- | --- | --- |
| 09-13 03:53:14 A | 全关 | 49/51，96% | 61% | 5/5 | 281 / 615 ms |
| 09-13 03:53:39 B | 多查询 + FAQ | 49/51，96% | 47% | 5/5 | 334 / 827 ms |
| 09-13 03:54:26 B_rerank | B + rerank | 49/51，96% | 46% | 5/5 | 750 / 1116 ms |

来源：[A](/Users/xiaoke.zhou/Documents/workspace/anker-haike/reports/retrieval/20260913T035314Z_A.md:9)、[B](/Users/xiaoke.zhou/Documents/workspace/anker-haike/reports/retrieval/20260913T035339Z_B.md:9)、[B_rerank](/Users/xiaoke.zhou/Documents/workspace/anker-haike/reports/retrieval/20260913T035426Z_B_rerank.md:9)。分子由同名 JSON 的逐样例布尔值汇总。

更早一次 rerank 报告跌到 23/51=45%，当时直接比较了 WeKnora RRF 约 0.016、本地 FAQ 0.3–1、reranker 0–1，发生跨库挤占。这是**融合口径错误的证据**，不能归结成“reranker 能力差”。修正后回到 49/51。旧速查表写的 rerank“p50 +470 ms”比较的是全关 A；隔离 rerank 的边际成本应比较 B→B_rerank，得到 +416 ms。[历史原因与对照](/Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-09-13_bounded-agentic-rag/findings.md:43)

FAQ 加入后 precision 下降也不能直接判定变差：金标主要写整份手册或某个工单 ID，没有完整记录正确 FAQ、同因工单。`bin-01` 标注示范就发现 FAQ q5、同因工单均相关；`chg-03` 则把错误的排障手册金标改成 FAQ/同因工单。[bin-01](/Users/xiaoke.zhou/Documents/workspace/anker-haike/data/eval/retrieval/cases.yaml:76)、[chg-03](/Users/xiaoke.zhou/Documents/workspace/anker-haike/data/eval/retrieval/cases.yaml:129)

### 3.2 父块：证明上下文覆盖，尚未隔离答案收益

单项 A/P 对照都为 doc hit 49/51、chunk hit 49/50；第一条证据含目标标记从 36 条增加到 48 条。旧文档的 36/49→48/49 以“已经命中目标的 49 条”为分母；若以全部 50 条 chunk 可评分样例为分母，应写 36/50→48/50。p50 为 239→230 ms、p95 为 388→434 ms，因此不能宣称“父块让系统更快”。[A](/Users/xiaoke.zhou/Documents/workspace/anker-haike/reports/retrieval/20260913T040609Z_A.md:9)、[P](/Users/xiaoke.zhou/Documents/workspace/anker-haike/reports/retrieval/20260913T040625Z_P.md:9)

父块变长后更容易包含标记，这是符合机制的上下文覆盖收益，不是更精确的语义排序。判断是否开仍应看跨块操作是否完整、错误计划是否减少。历史只有 3 份手册、13 个子块，缓存和上下文成本也不能按比例忽略到更大语料。[旧规模和扩展方式](/Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-09-13_bounded-agentic-rag/findings.md:62)

### 3.3 模型侧：三项合开只改善一例，grade 增加两个错误

| 组 | 开关 | plan 正确 | outcome 正确 | synth 降级数 | synth p50 |
| --- | --- | --- | --- | --- | --- |
| A_synth | 全关 | 40/43 | 49/51 | 13 | 3645 ms |
| C_nograde | 多查询 + FAQ + 父块 | 41/43 | 50/51 | 14 | 3291 ms |
| C | 上组 + grade | 39/43 | 50/51 | 14 | 3206 ms，另有 grade 1578 ms |

来源：[A](/Users/xiaoke.zhou/Documents/workspace/anker-haike/reports/retrieval/20260913T043547Z_A_synth.md:9)、[C_nograde](/Users/xiaoke.zhou/Documents/workspace/anker-haike/reports/retrieval/20260913T043926Z_C_nograde_synth.md:9)、[C](/Users/xiaoke.zhou/Documents/workspace/anker-haike/reports/retrieval/20260913T045339Z_C_synth.md:9)。JSON 表明三组各 56 次 synth 均为 `dashscope/qwen3.8-max`。当前 domestic 配置已把 deepseek 置于 synth 首位，因此旧模型结果也不能直接作为当前运行效果；实际还需记录当次使用的 lane 和 model。[当前 synth 路由](/Users/xiaoke.zhou/Documents/workspace/anker-haike/config/models.yaml:72)

逐样例核对：A 的 plan 错误为 `safe-04`、`neg-03`、`typo-01`；C_nograde 修正 `neg-03`；grade 又让 `a2-01`、`sb-03` 出错。旧 findings 把 `cat-05`、`exact-02` 混进 plan 错误叙述，实际它们是 outcome 对照问题；`exact-02.expected_plan=null` 根本不参加 plan 分母。应以逐样例报告/JSON 为准。[旧叙述及误删分析](/Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-09-13_bounded-agentic-rag/findings.md:83)

三个开关绑定只改善 1/43 个计划，不能确定贡献来自哪项，也没有多轮重复的置信区间。C 的 synth p50 低 85 ms 不抵消串行 grade 的 1578 ms；各步骤中位数也不能直接相加当作整链路中位数。现有报告没有整链路 P95 证明。

### 3.4 较新基线已经变动，但没有相应的开关对照

09-16 final 使用 `2026-09-16.draft2`：58 条、人工标注仍 2 条、报告所列开关全关，doc hit 53/54=98%、chunk hit 51/53=96%、precision 48%、no_match 0、无知识返回命中 4/4，检索 p50 207 ms / p95 561 ms。唯一 doc miss 是 `ctr-03`；chunk miss 为 `chg-03` 与 `multi-02`。[最新既存报告](/Users/xiaoke.zhou/Documents/workspace/anker-haike/reports/retrieval/20260916T114451Z_final.md:3)

这些数字不能与 09-13 直接当 A/B：样例从 56→58；`cat-05` 因手册变为品类可见，从“无知识”改成正例；`chg-03` 金标已修；可见文档集合与顺序也变了。09-16 的中间 `titlerevert2` 组 doc hit 48/54、final 53/54，且开关都关，已经说明数据/范围/索引等基础变动可显著改变效果。[中间报告](/Users/xiaoke.zhou/Documents/workspace/anker-haike/reports/retrieval/20260916T114345Z_titlerevert2.md:9)、[cat-05 当前金标](/Users/xiaoke.zhou/Documents/workspace/anker-haike/data/eval/retrieval/cases.yaml:177)

本轮主代理只读核对的实际库为手册 35 份、工单 380 份、FAQ 116 条，已不等于旧“3 份手册/13 子块”的测试环境；旧“语料小所以不需要重排/评分”的结论只能作为历史基线。58 条当前样例的显式品类只有 `robot_vacuum`，50 条为扫地机 SKU、8 条为品类状态，尚未覆盖多品类线上分布。

### 3.5 改写的 100% 已被更新数据推翻

`reports/bakeoff/query_rewrite/bakeoff.md` 是 models 版本 `2026-09-13.2`，记录 qwen 100%、deepseek 88%、glm 38%。更晚的总报告 models `2026-09-13.5` 已变为 **75%、75%、62%**，三者 Schema 都 100%，但字段准确率均低于 90% 门槛。当前 `config/models.yaml` 的 domestic rewrite 行也引用这组结果，实际 `max_tokens:128`；不能引用旧阶段记录的 `512` 或旧 100% 作为当前配置质量保证。[旧报告](/Users/xiaoke.zhou/Documents/workspace/anker-haike/reports/bakeoff/query_rewrite/bakeoff.md:5)、[较新报告](/Users/xiaoke.zhou/Documents/workspace/anker-haike/reports/bakeoff/bakeoff.md:23)、[当前路由](/Users/xiaoke.zhou/Documents/workspace/anker-haike/config/models.yaml:77)

旧 0/56 触发是依据当时检索状态推断，不代表评测执行过完整改写补救。即使召回永远有东西，也可能都是不相关内容；RRF 是按名次融合的分数，不能当作“有答案”的概率。应该先区分“没有候选”和“候选不能回答”，再决定是否需要受控补救；直接复制每问必改写没有现成收益证据。

## 4. 评测口径与复现陷阱

1. **人工标注不足。** 当前 58 条仅 `bin-01`、`chg-03` 为 true，2/58≈3.4%，其余 56 条仍是草稿。旧 switches 的“0/56”和 issue 78 的“56 条”都已过时。已有任务约束是未标注样例不作为开启依据，阶段 3 至少 50 条人工标注；issue 78 进一步要求扩到 ≥80 条真实口语、每项单独开、plan 不降且 P95 在预算内。[数据声明](/Users/xiaoke.zhou/Documents/workspace/anker-haike/data/eval/retrieval/cases.yaml:3)、[原门槛](/Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-09-13_bounded-agentic-rag/task_plan.md:28)、[issue 78](/Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-09-14_l3-p1-real-data-multicategory/issues/78-retrieval-switches-enable.md:3)

2. **预填症状绕过真实 intake。** 57/58 样例有 symptoms，`case_state` 直接复制它们，再 build_query；`typo-01` 原话“吸利”已预填为“吸力变小”，`sb-02`“侧面那个小刷子”已预填为“侧刷不动”。所以口语/错别字标签的高 hit 不能证明原话检索或完整系统同样有效。[评测入口](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/eval.py:34)、[错别字样例](/Users/xiaoke.zhou/Documents/workspace/anker-haike/data/eval/retrieval/cases.yaml:204)

3. **文档 hit 不等于相关片段 hit。** `is_gold` 只看 doc_id 或工单原因子串，同一份手册任意块都算正确；FAQ 整个容器也是同一个 doc_id，把 `faq_rv` 加入 expected 后，错误 FAQ 条目也可能被计为正确。`precision@5` 分母实际是返回的 hit 数量，不固定为 5，再按样例宏平均；未列出的正确来源会被误判。[打分实现](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/eval.py:92)

4. **chunk 指标是文本标记匹配。** c12、A–E、1–5、表头被转换成子串；任意 hit 的 snippet/full_text 含其中一个就算命中，不要求该 hit 同时属于对应 gold 文档，也不要求多个期望片段全部覆盖。父块变长可能机械提高 chunk_rank，而不是改善排序。应增加“文档 ID + 稳定片段 ID + 相关性等级”金标。[marker 与匹配](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/eval.py:67)

5. **未覆盖完整诊断环。** `evaluate` 只执行 `round_no=1`；即使 with_synthesize，也只是后接 grade/synthesize，没有 rewrite 和第二轮检索、历史省略句恢复、真实 intake、前置安全规则、整图预算。安全样例的 outcome 明确跳过比较。不能用本报告验收 A1–A9 或二轮补救。[一轮调用](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/eval.py:245)、[安全排除](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/eval.py:192)

6. **latency 不包含后续模型步骤。** `latency_ms` 在 `_model_side` 前截断，包含本次 search/父块扩展，却不含 grade/synth、intake、全图控制和回复。索引 refresh 在逐案例计时之前，父块缓存首次加载则在首个样例内；冷热运行不能不加区分地比较。[计时边界](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/eval.py:244)

7. **报告头部与实际执行不一致。** renderer 固定写“只评检索层（不跑模型）”，但 A_synth/C_* 的 `with_synthesize=True` 且 JSON 有真实模型记录。以 flags/rows 为准，不能只读标题。grade 的 `false_negative=43` 也是文档级口径；旧分析认为其中真正目标块被删 4 次，不应把 43 全当独立关键证据误删。[报告模板](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/eval.py:403)、[grade 指标](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/eval.py:153)

8. **缺少严格的运行版本指纹。** JSON 只有 arm/summary/rows，flags 只保留部分布尔值和配置路径，没有代码 SHA、case 内容哈希、完整配置、语料/索引哈希，也没记录 rewrite 开关。9/13 与 9/16 都写相同 `kb_ver`，实际样例与数据范围不同；相同版本字符串不能证明实验同条件。[输出实现](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/eval.py:478)

9. **当前默认样例与当前 CLI 有静态复现风险。** 50 条 confirmed_sku 缺 `category`；`case_state` 和 `case_scope` 都直接访问 `case['category']`，`run_eval` 原样加载 cases 后调用 evaluate。据此存在第一条样例构造 state 时缺字段的风险；本次没有运行真实 eval 验证。应先使输入和入口一致，再重新产出实验，不能假定旧命令现在可复现。[字段访问](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/eval.py:46)、[直接读取](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/eval.py:463)、[首条样例](/Users/xiaoke.zhou/Documents/workspace/anker-haike/data/eval/retrieval/cases.yaml:30)

## 5. 最小可决策的下一轮评估

先把当前数据和 gold 对齐，再按单项对照决定开关。对于既有开关的一轮效果探索，可以先不改运行时编排；但补检索触发、证据充分性判断及两轮结果的验收必须接真实 graph，当前 `eval.py` 不足以验证这些方案。建议沿 issue 78 的方向补齐真实多品类样例，并显式包含：正确片段跨块、FAQ 独有答案、部件歧义、否定/已排除操作、跨轮省略、同 SKU 同因工单、只有反证、确实无知识、候选已召回但被挤出 top-k。

```text
固定代码 + 模型/参数 + 语料/索引快照 + 已标注样例
                         |
                 当前全部关闭基线
                         |
       +-----------------+------------------+
       |                 |                  |
    仅 FAQ           仅父块扩展         仅多查询
    来源覆盖          步骤完整性         漏召回恢复/漂移
       +-----------------+------------------+
                         |
                证明相关片段在候选池
                         |
                    仅 rerank
                 看片段名次/计划正确性
                         |
            仅在仍有可量化问题时评 grade / rewrite
                         |
         整图回放：答案依据、计划、拒答、P95、调用次数/成本
```

先记录 candidate recall、最终片段 Precision/Recall、关键上下文覆盖，再看 synth 的计划/结论与引用是否支持。多轮模型实验需要重复运行，报告每条得失；只改善 1 个样例不应掩盖其他样例退化。改写尤其需要记录触发率、拒绝理由、语义漂移、补救成功率；grade 需要关键证据误删率。达到门槛再启用，现有报告只能决定这些验证的优先级。
