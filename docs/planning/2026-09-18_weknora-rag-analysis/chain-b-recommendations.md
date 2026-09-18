# 链路 B：改写、召回、排序的修改必要性

分析日期：2026-09-18。链路 A 指 WeKnora 原生聊天，链路 B 指海客自己的对话编排调用 WeKnora `hybrid-search`。本轮仅分析源码和既有评测，未修改业务实现、启用开关或发起真实模型评测。

结论：有必要改链路 B，优先改「候选过早裁剪」和「证据不足时的补查决策」，同时修正两轮证据进入模型的选择方式。LLM 改写和模型重排是可以复用的现有能力，但收益需要重新验证，不能用全部开关开启代替流程修改。

术语：召回是从知识库取出候选片段；RRF 是按各检索列表的名次融合候选；重排是用模型重新评价问题与候选的相关性；充分性判断是检查这些证据能否支撑当前问题的排障方向。四者解决不同问题。

## 1. 当前实现与限制

```text
用户原话 / 历史有效事实
          |
          v
intake：确认产品、提取有效症状、处理纠正
          |
          v
build_query：产品 + 故障类别 + 有效症状
          |
          +--> KnowledgeScope：先限定适用文档
          |
          v
说明书库 / 工单库并发 hybrid-search
  WeKnora：关键词 + 向量 -> RRF -> 每次请求最多返回 15 条
          |
          v
adapter：正文截为 400 字 -> 每库只留 5 条 -> 字符预算
          |
          v
可选多查询融合：每库又裁到 5 条
          |
          v
可选 rerank：只能给已经留下的片段排序
          |
          v
跨库按名次交错
          |
          +--> 可选 grade：最多 8 条，每条 200 字
          |      当前会过滤 irrelevant；并非按 insufficient 补查
          |
          +--> 有界补查：图片或文本，共用一次名额
          |      文本通常被「已有命中」挡住
          |      新结果追加，第二轮不重排
          v
可选父块扩展 -> 加入本地故障卡 -> 诊断输入选前 12 条
  普通片段每条最多 300 字；扩展正文每条最多 800 字
          |
          v
统一 context 层加入产品、事实、原话、选中的历史
          |
          v
synthesize：选择允许的预写计划 -> 步骤指导
```

说明：图中 15 来自当前 `top_k=5` 对应的 `match_count=top_k*3`，是 API 返回预算，不是 WeKnora 内部最初的向量/关键词候选总数。所有可选检索增强当前均关闭。故障卡与检索证据在运行时分支汇合，并不经过完全相同的评分路径。

依据：[配置](/Users/xiaoke.zhou/Documents/workspace/anker-haike/config/retrieval.yaml:1)、[API 请求与裁剪](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/adapter.py:313)、[一轮检索](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/search.py:112)、[真实编排追踪](/Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-09-18_weknora-rag-analysis/chain-b-runtime.md)。

## 2. 具体改哪里，为什么

| 优先级 | 修改点 | 必要性与建议 |
| --- | --- | --- |
| P0 | 候选数量与最终上下文数量分开 | 已确认的流程限制。重排前只剩每库 5 条，无法挽回被提前丢弃的候选。先保留更大的候选集合，最终再裁剪。 |
| P0 | 按证据充分性决定补查 | 已确认的控制流缺口。有结果不等于足够；`insufficient` 尚未真正驱动补查。 |
| P0 | 两轮联合选择最终证据 | 补查改造的必要配套。第二轮追加到末尾可能进不了诊断的前 12 条。 |
| P1 | 改写输入与同义词按品类约束 | 适合在补查中启用；现有全局词表存在已记录的部件替换错误，不能直接全开多查询。 |
| P1 | 模型重排 | 候选保留修正后独立试验；现有历史数据没有证明应默认启用。 |
| P1 | 父块/邻块扩展与完整证据包装 | 对截断导致的证据缺失有针对性；按命中位置扩展，避免只扩大无关内容。 |
| P2 | FAQ、多查询等其他增强 | 独立验证，避免和主要改造捆绑后无法归因。 |

### 2.1 候选保留：先召回，再排序，最后给模型分配上下文

问题：当前适配器请求最多 15 条后自己先裁为 5 条；多查询融合再次裁为 5 条；重排发生在这些裁剪之后。`max_chars=2000` 又把展示/上下文限制施加到了候选集合上。

机制示例（不是已测案例）：正确片段在 WeKnora 返回列表中排第 8。即使重排模型本来能将它排第 1，它也已在适配器被删除。仅设置 `rerank.enabled=true` 解决不了。

建议：

- 区分 `candidate_k`、`final_k` 与 `context_budget`。可先用每库保留当前请求的 15 条作为实验起点；15 或 20 都只是待测参数，不是已证实最优值。
- 候选保留完整的命中片段、文档标题、来源、版本、轮次与反证属性；展示摘要单独截断。对单条候选仍设合理长度上限，避免无限扩张。
- 多查询及两轮结果先按稳定证据 ID 去重，再排序、选择、扩展和分配上下文。不使用跨产品/跨工单结果的正文相似度去重。
- trace 分别记录 API 返回数、范围过滤后数量、融合数量、最终选中数及排除原因。当前 `total_hits` 在裁剪后计数，不足以观察召回损失。

落点：[adapter.py](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/adapter.py:313)、[search.py](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/search.py:35)、[检索配置](/Users/xiaoke.zhou/Documents/workspace/anker-haike/config/retrieval.yaml:48)、对应配置模型及追踪字段。

### 2.2 补查：从「有没有」改为「够不够」

问题：文本改写的主要触发条件是没有命中。开启 grade 后，只要还有一个 relevant 或故障卡命中，仍可能阻止补查；`coverage=insufficient` 并不等价于启动第二轮。grade 同时会硬过滤片段，历史评测出现过误删。

例子：用户说「不是不充电，是充得慢」。首轮找到一段“检查充电连接”的内容，属于部分相关，但没有慢充条件、功率或状态的证据。正确行为应是保留这段内容，再围绕“充电慢”补查；不能因为已有一条命中就结束，也不能改写成未经确认的“充电器损坏”。

建议：

- 保持服务状态 `ok/no_match/unavailable` 原样，另设充分性 `sufficient/insufficient/none/unknown`。
- 首轮真实空结果，或已有证据但不足以支撑排障方向，可以消费一次补查名额。充分性评估应包含故障卡和实际会交给诊断的证据。
- 评分提供缺口和质量标记，不单凭 `irrelevant` 删除首轮候选；最终上下文仍需要受预算约束地选择。
- 复用现有改写校验、产品范围、一次补查上限、失败回退与取消机制。图片与文本继续共享名额，第二轮不递归。
- 服务不可用、适用文档集合为空与语义不相关分开处理。整体服务故障不能靠换一句话恢复。
- 将评估、改写、第二轮检索与整轮 deadline 一起核对；不能只打开功能开关却让旧的剩余时间门槛持续跳过它。

落点：[graph.py 的 retrieve 编排](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/sessions/graph.py:1793)、[should_rewrite](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/diagnose/rewrite.py:93)、[grade.py](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/diagnose/grade.py:106)。项目已有[效果优先的有界检索补救规格](/Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-09-13_quality-first-retrieval-rescue/spec.md)，方向与本次源码分析一致，可在该设计上继续，候选保留和最终选择是重要补充。

### 2.3 改写：保留已有理解层，在缺口处使用模型

当前 `build_query` 已使用已确认产品和有效症状，症状代码还会补充故障类别。线上 ModelRouter 的统一 context 层也提供产品、有效事实、原话和选中的历史。因此无需为了借鉴链路 A 再加一套通用意图识别或无条件 LLM 改写。

建议优先采用：基础 query 保留；补查 query 接收当前有效症状、明确否定/纠正、产品范围以及缺口提示。缺口提示只是检索方向，不能升级成故障事实。不得新造型号、部件、错误码或原因。原 query 与改写 query 的来源均保留。

多查询是另一个决策：当前简单子串替换已在测试中记录「侧面那个小刷子不动了」变成「侧面那个小滚刷不动了」。融合能保留原查询，但不能保证错误变体不会增加噪声。启用前应将词表按品类管理，并处理“刷子”这类部件歧义；改写允许的同义词和自动扩展规则不必共用同一宽松词表。

落点：[query.py](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/diagnose/query.py:61)、[rewrite.py](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/diagnose/rewrite.py:165)、[expand.py](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/diagnose/expand.py:41)、[已记录的替换问题](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/tests/test_diagnose_expand.py:50)。

### 2.4 排序与上下文：让新找出的有效证据真正进入诊断

现状：模型重排只读 `snippet`，不读标题；跨库按库内名次交错，避免直接比较 RRF、FAQ 相似度和模型相关分。第二轮固定关闭重排，去重后将新增证据追加；诊断只取前 12 条，所以“补查成功”不保证“模型看到”。

建议分两步：

1. 必要修改：两轮合并后进行一次明确的最终选择，保留来源、轮次和正反证区分。选中理由应可追踪，尤其是第二轮解决缺口的片段。选择依据包含相关性与问题覆盖，不能简单按轮次追加。
2. 可选试验：对更完整的候选调用现有重排模型，输入标题加命中正文。先比较现有分库重排/名次合并，再考虑统一重排；跨源共用同一个模型评分并不自动证明顺序更好。重排失败保留原排序。

在最终选中后，再按命中位置扩展父块/邻块并按语义边界截取。传给模型的证据块显式带标题、来源和工单结果；适用范围由代码继续强制执行。父块只提供上下文，引用仍能定位到具体命中。grade 当前最多看 8 条、每条 200 字，不应在扩大候选池后直接宣称它评估了全部候选的充分性。

落点：[重排输入](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/rerank.py:85)、[跨库合并](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/search.py:221)、[两轮合并](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/sessions/graph.py:1648)、[父块扩展](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/adapter.py:271)、[诊断证据包装](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/diagnose/synthesize.py:121)。

## 3. 建议目标流程

```text
有效事实 + 已确认产品
          |
          v
基础 query + 强制文档范围
          |
          v
关键词/向量混合召回 -> 保留候选池 -> 融合去重
          |                            |
          |                 故障卡等适用证据
          +----------------------------+
          |
          v
候选排序 / 代表性证据选择（模型重排可选）
          |
          v
证据是否足以支撑排障方向？
          |
          +-- 足够 ----------------------------+
          |                                    |
          +-- 不足且有补查名额                  |
                 |                             |
                 v                             |
        原意约束的改写或图片补查                |
                 |                             |
                 v                             |
        第二轮召回 -> 与首轮联合选择 -----------+
                                               |
                                               v
                         按需扩展 + 上下文预算 + 来源/结果标签
                                               |
                                               v
                             诊断选择允许的计划 / 明确兜底
```

第一轮候选保留与第二轮联合选择应先完成；充分性与受控改写作为一个完整补救单元落地；随后独立测重排、父块扩展与同义多查询。底层继续复用现有 WeKnora 混合检索，当前证据没有指出需要更换向量库或搬入原生聊天 Agent。

## 4. 如何判断修改确实有必要且有效

已有报告只支持定位问题，不能直接承诺效果提升：

- 9 月 16 日基线共 58 条、54 条可评分、只有 2 条已人工标注，主要仍为早期扫地机样例与旧知识版本。报告显示文档 hit@5 约 98%，但 precision 约 48%；4 条预期无知识样例全部返回了命中。这说明“搜到了”指标区分力有限。这里的无知识命中不是跨 SKU 泄漏。
- 9 月 13 日对照中 LLM 改写触发 0 次，无法证明改写有益或有害。grade 有误删；重排没有稳定改善文档命中。多查询、FAQ 和父块捆绑结果无法拆分归因。
- 当前 `eval.py` 主要共享一轮 `search_round`，并未覆盖真实补查编排。它直接使用预填症状，不能代表口语输入经 intake 的全过程；延迟也不包括后续 grade/synthesize。
- 某些步骤证据来自本地已审核计划的兜底注入，不能把“最后显示了带引用的步骤卡”当作 RAG 已召回正确片段。

详细证据与报告口径见[评测复核](/Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-09-18_weknora-rag-analysis/chain-b-evaluation.md)。

建议先冻结当前知识、模型与配置版本，补齐真实多品类标注，再比较以下独立方案：基线；只修候选/最终选择；加入充分性驱动补查；再加入模型重排；父块与多查询各自试验。

验收分三层：

| 层次 | 观察内容 |
| --- | --- |
| 召回与排序 | 候选池是否包含正确片段、最终前 K 条的相关性、关键症状覆盖、否定与型号约束是否保留 |
| 补查 | 是否在空结果/不相关/部分相关时正确触发，改写是否采用、是否带来新增有效证据、这些证据是否进入模型 |
| 最终效果 | 适用计划是否正确、引用是否真正支持结论、无依据时是否正确兜底，另列耗时、失败率与调用量 |

工程验证复用现有会话 HTTP 测试边界，以 FakeChatModel 和 fake WeKnora 覆盖真实编排；真实模型实验单独运行并记录版本。优先覆盖“正确片段位于原始列表第 8”“已有一条相关但关键证据不足”“第二轮有效证据排在旧前 12 条之后”“错误同义替换”“评分误判首轮有效证据”等回归场景。

此次结论是：流程限制值得修；改写、重排等模型能力的默认启用仍需这些实验来决定。没有现成数据可以承诺具体的准确率提升幅度。
