# 发现

## 2026-09-13 评估与设计阶段

代码事实（已核对源码）：

- `sessions/graph.py:815` `_search_round` 对 kb_manual / kb_tickets 串行 await。
- `config/retrieval.yaml: retrieval.second_round_budget_ms` 只被 `diagnose/config.py` 定义，graph 内只用 `min_remaining_for_second_round_ms` 做开始前检查，第二轮 `_search_round` 没有 `wait_for`。
- 第二轮有命中时 `hits, results = hits2, results2`（graph.py:971、1038），首轮命中被丢弃。
- `Hit.counter_evidence` 未进入 `as_evidence_item()`；`synthesize.py:154` 的证据行只有 id / source / snippet 前 300 字，模型无法区分 solved 与 unsolved 工单。适配器排序把 counter_evidence 放后，但 top_k 截断后仍可能进入。
- `data/knowledge/manifest.json` 与 `replay/kb_manifest.json` 的 kb_ver 均为 `2026-09-12.1+stub-embedding-1024`，真实 embedding / rerank 未在本机验证。
- FAQ 入库到独立 `haike_kb_faq`，运行时 `_search_round` 只查两库，FAQ 不参与检索；FAQ 内容只通过 plans.yaml evidence 占位与故障卡间接出现。评测集中 4 条金标只在 FAQ 里，打 `faq_only` 标签；另有若干条在 irrelevant_hint 里注明相关 FAQ 条目不在范围。
- plans.yaml 只有 5 个吸力相关计划；充电、拖布、水箱、路线、指示灯类问题有语料无计划，synthesize 在这些样例上的行为（默认计划 / 无计划）需要在阶段 2 基线里观察后决定 expected_outcome。
- EUFY-S1-PRO 扫地机不在任何手册 sku_list 中，confirmed_sku 下只有排障手册与该 SKU 工单可见。A2 演示进入检索后依赖排障手册 A 节。
- 语料无数字错误码；「精确词」在本期指语音提示（请检查尘盒 / 请检查滚刷）、灯态与部件名。
- 国产链只有 json_object；智谱静默忽略 json_schema。grade 的 Schema 校验必须在代码侧做（evidence_id 白名单、枚举回退）。
- bake-off 中 query.rewrite 准确率 0% 是 `validate_rewrite` 全拒所致（词表问题），不是模型不会改写。

与另一份评估（`2026-09-13_agentic-rag-evaluation`）的对照见 `docs/claude/spec_agentic_rag_evaluation.md §6`。

## 2026-09-13 阶段 1 实施

- `asyncio.wait_for` 超时会取消在途的 `hybrid_search` 协程；WeKnora httpx 请求随之取消，不会残留。测试里用 `started` 计数而非完成计数验证「发出 4 次、完成 2 次」。
- 两轮合并后 `per_kb_status` 取两轮中较好者（ok > no_match > unavailable），`truncated` 取两轮任一。首轮已有的 evidence_id 不被第二轮同 id 命中覆盖（首轮 snippet 保留）。
- `evidence` 状态字段与 SSE `evidence` 事件仍用 `as_evidence_item()`（契约不变）；只有 synthesize 的输入用 `as_internal_item()`。回放包录制的 Hit dict 缺新字段时按默认值补齐，兼容。
- 改写路径第二轮预算取 `min(second_round_budget_ms, remaining − min_remaining_for_second_round_ms)`，下限 500 ms，与 rewrite 自身预算口径一致。
- 全量测试首次跑有 10 个 `test_admin_api` 失败（psycopg 连接），第二次全部通过，与本次改动无关，属环境波动。

## 2026-09-13 阶段 2 实施

- DashScope key 直连实测：`text-embedding-v4` 1024 维正常；`gte-rerank-v2` 正常打分。WeKnora 容器启动时 EMBEDDING_API_KEY / RERANK_API_KEY 为空，重建 weknora-app 与 orchestrator 容器后加载；/health 三家 provider 全 ready。
- WeKnora 知识库的 embedding 模型在创建时绑定、不可改；三库原绑 stub-embedding-1024。新增 `haike-kb ingest --recreate-kb`（embedding 不一致时删库重建），重建后 203 条全部 completed，manifest kb_ver `2026-09-12.1+text-embedding-v4`。重建前已 `snapshot export` 到 `data/knowledge/snapshots/20260913T033245Z`。知识库 id 全部变化，orchestrator 容器需重建以重新读 manifest（单文件 bind mount + 适配器缓存 kb_ids）。
- **rerank 在 v0.8.0 的 `hybrid-search` 接口不生效**：知识库对象没有 `rerank_model_id` 字段（创建 / 更新静默忽略），返回分值全部落在 0.0154–0.0164（即 RRF 的 1/(60+rank)），重排属于 WeKnora chat 会话管线。已在 WeKnora 登记 gte-rerank-v2 模型（manifest 记录），但要用它必须由适配器自己调百炼 rerank 接口 → 归阶段 3 评估（设计 S1 的「RRF 融合」实际由 WeKnora 已做，我们的 RRF 只需处理多变体合并）。
- 分值没有区分度 → 无法靠阈值过滤「无知识」样例，5/5 无知识样例全部返回命中（leak）。这正是阶段 5 grade 要解决的问题。
- A 组基线（56 条，未标注，`reports/retrieval/20260913T033959Z_A.md`）：hit@5 96%、precision@5 65%、leak 5/5、检索 p50 549 ms / p95 821 ms（评测脚本两库串行，即单库约 270 ms 含远程 embedding；重建库后首次跑 p50 1463 ms，是冷启动，已删除该份报告）。两条 miss：chg-03「找不到基站」（工单 T0178/T0168 命中但金标未列，标注时补）、ctr-03「清扫路线混乱」（命中 T0130 而非金标 T0030，同因工单，金标应放宽为 root_cause 匹配）。低精确率：multi-03、ctr-02（工单噪声）。
- 单库约 270 ms（热）/ 700 ms（冷），图内两库并发（P0-1）每轮省下同量级时间。
- 重建库后立即 `refresh_index` 有 1/200 条工单 custom_metadata 读到空（列表视图滞后，稍后 get / list 均已存在），导致 live 测试 199≠200 一次性失败；ingest 已加写后回读校验 + 重试一次（`_set_metadata`）。重跑 ingest 203 条全部 skipped，幂等成立。

## 2026-09-13 阶段 3 实施

- **WeKnora v0.8.0 FAQ 库不可检索**：50 条 FAQ 导入成功（entries 接口可列、KB `vector_store_status=available`），但 `faq/search`、`hybrid-search`、`knowledge-search` 对 FAQ 库全部返回空，关阈值也一样；日志无报错。改为适配器侧本地索引（`knowledge/faq.py`：源文件 faq_rv.yaml，字符二元组 Dice + 子串加分，阈值 0.3，匹配前剥掉 SKU / eufy 词）。零延迟、确定性、回放友好。
- `WeKnoraClient.list_faq_entries` 分页解析错误（响应是 `data.data`，原代码把 dict 当列表迭代 key，导致翻到第 8 页才停），已修。
- **各库分值量纲不同**：WeKnora hybrid-search ≈ 0.016（RRF）、本地 FAQ 0.3–1、百炼 rerank relevance 0–1。跨库按原始分混排会让 FAQ / rerank 后的工单挤掉手册（B_rerank 第一次跑 hit@5 掉到 45% 就是这个原因）。新增 `search.interleave_kbs`：按库内名次做 RRF、手册 > FAQ > 工单破平、反证最后，图内 synthesize 输入顺序与评测 top-k 共用。
- 同义词表用于扩展时的副作用：单字同义词（清扫: [扫, 跑]）会把「扫地机器人」改成「清扫地机器人」→ 扩展只用 ≥ 2 字的同义词；子串替换仍会出现「小刷子」→「小滚刷」，靠 RRF 融合吸收。词表本身是 rewrite 校验用的，扩展复用它属于借用，后续可分表。
- 三组对照（56 条、未标注、跨库交错口径，`reports/retrieval/20260913T035314Z_A / 035339Z_B / 035426Z_B_rerank`）：

  | 组 | 开关 | hit@5 | precision@5 | leak | p50 / p95 ms |
  | --- | --- | --- | --- | --- | --- |
  | A | 全关 | 96% | 61% | 5/5 | 281 / 615 |
  | B | multi_query + faq | 96% | 47% | 5/5 | 334 / 827 |
  | B_rerank | 再加 rerank | 96% | 46% | 5/5 | 750 / 1116 |

  - 手册 / 排障手册在 50 条有手册金标的样例里三组都排第一，文档级 hit@5 对这三项改动不敏感；分块级差异当前指标看不见。
  - B 的 precision 下降全部来自 FAQ 命中不在金标：逐条核对 45 条 FAQ 命中，如「提示请检查尘盒」→ q5、「电池鼓包」→ q22、「拖布异味」→ q17、「App 无法连接」→ q35（这条原被算作「无知识泄漏」，其实是正确命中）；弱相关的有「不充电」带出「找不到基站」、「墙边角落扫不干净」带出「吸力变小」。
  - rerank 106 次调用全部成功，中位 265 ms；文档级无增益；bin-03 把第 3 章指示灯表格块顶到 c18 前面。
  - 工单在 top5 的占比 100/268 → 93/276，FAQ 挤掉的是工单不是手册。
- 按硬约束（未标注样例不作开关依据），三个开关默认仍关闭；建议见 task_plan「待用户决策」。
- 运行中的 orchestrator 容器仍是旧镜像代码（本阶段未 rebuild），开关全关时行为等价，正式验证走 RELEASE 流程。

## 2026-09-13 阶段 4 实施

- WeKnora v0.8.0 分块接口：`GET /chunks/{knowledge_id}?page&page_size` 可列子块（带 `parent_chunk_id`、`chunk_index`、`pre/next_chunk_id`、`content`），**父块本身没有读取接口**（`/chunks/{parent_id}` → Knowledge not found；`/knowledge/{id}/chunks` 404）。X10 手册 7 个子块共一个父块 id，越过父块边界的尾块（指示灯表格）`parent_chunk_id` 为空。
- 因此父块用「同 `parent_chunk_id` 的子块按 `chunk_index` 拼接、去重叠」还原（`adapter.merge_overlapping`，重叠取前块后缀 = 后块前缀的最长公共串，上限 120 字，对应 chunk_overlap=80）。实测 X10 手册 6 块 → 783 字、L60 手册 3 块 → 425 字、排障手册 3 块 → 447 字（整篇），内容完整无重复。无父的尾块用 pre/next 邻块。
- 手册库一共 13 个子块（3 份文档），子块缓存一次性拉取，零运行时开销；工单每条单块不缓存。
- 同一父块下的多条命中只让第一条带 full_text，其余 `expanded_from` 指向它，避免 synthesize 收到三份相同正文。SSE evidence 与快照仍是子块 snippet（契约不变），full_text 只经 `as_internal_item()` 进 synthesize（`_evidence_text`：父块 ≤ 800 字，否则子块 ≤ 300 字）。
- 评测新增 chunk_hit@5（expected_chunk_hint 的 c12 / A–E / 1–5 / 第3章表 / faq qN 映射为正文标记，命中 snippet 或 full_text 含标记即算）。A 与 P 组都是 98%（49/50），唯一 miss 是 chg-03（金标问题，见阶段 2）。
- 但看「目标段落出现在第一条证据里」（chunk_rank==1）：A 组 36/49，P 组 48/49。也就是说父块扩展后，synthesize 拿到的第一条证据在 98% 的样例里已经包含金标段落全文，而只看子块时只有 73%。这是父块扩展的直接收益，71 次扩展、中位父块 447 字、延迟无差异。**语料太小导致检索指标饱和**：手册库 13 个子块，top-5 就覆盖单份手册的大半，任何检索层改动在 hit / chunk_hit 上都看不出差别。三个开关（faq / multi_query / parent_expand）的真实收益只能在 synthesize 输出上量（expected_plan 一致率），需要模型侧评测 → 阶段 5。
- 运行中的 orchestrator 容器仍是旧镜像；`parent_expand` 默认关闭，行为等价。

## 2026-09-13 阶段 5 实施

- **百炼 Qwen 默认开思考模式**：qwen3.7-flash / qwen3.8-max 在 OpenAI 兼容接口下结构化调用返回空 content（probe reply=''），synthesize 在 qwen-max 上 8 s 预算全部超时 → 之前没有 DASHSCOPE key 时链直接跳到 deepseek 所以没暴露；阶段 2 配上 key 后 domestic 主模型实际上一直在超时降级。models.yaml 给 qwen-flash / qwen-plus / qwen-max 加 `params: {enable_thinking: false}` 后 probe 1.2 s 正常。**这是生产问题，与本任务无关但由本任务发现**；orchestrator 容器读的是挂载的 config/，重启即生效。
- retrieve.grade bake-off（8 样本 × 2 次，`reports/bakeoff/retrieve_grade/bakeoff.md`）：qwen-flash schema 100% / 准确率 98% / 1169 ms → 主；deepseek 100% / 100% / 1038 ms → 备；glm-flash 0%（智谱账户 429 限流 + 预算耗尽，非模型能力问题）。主备两家厂商满足 model-selection §3.8。首轮 max_tokens 256 不够（items 列表 + coverage 约 300 token），提到 512。
- grade 设计落地：评分不进 SSE evidence（被剔除的命中仍作为「检索到的来源」发出），只改 synthesize 输入；`evidence_quality` 进 state；graded 全不相关时把 ok 库视作 no_match 参与 09 §4.1 改写决策，`knowledge_status` 不变；第二轮新增命中默认标 unsure（`grade.second_round` 开才第二次调用）。
- `haike-kb eval --with-synthesize`：对每条样例用真实模型跑 grade（若开）+ synthesize，比较 expected_plan / expected_outcome；安全类样例的 escalate 来自 R4 规则不在此比较。模型侧对照（56 条、未标注、qwen-max 做 synthesize）：

  | 组 | 开关 | plan_match | outcome_match | synth 空列表→standard_flow | synth p50 |
  | --- | --- | --- | --- | --- | --- |
  | A_synth | 全关 | 40/43 | 49/51 | 13 | 3645 ms |
  | C_nograde_synth | multi_query + faq + parent_expand | 41/43 | 50/51 | 14 | 3291 ms |
  | C_synth | 再加 grade | **39/43** | 50/51 | 14 | 3206 ms（+ grade 1578 ms）|

  - A 的 3 个 plan 不匹配：cat-05（滤网清洗 → 判 filter_clog，金标 filter_clog 其实一致，是 expected_outcome 写成 standard_flow 的金标问题）、neg-03（尘盒已清理 → filter_clog，金标 hair_wrap，两者都说得通）、typo-01、exact-02（红灯常亮 → motor_fault，金标 null）。C_nograde 把 neg-03 修正了。
  - synth 空列表 13/14 条全是「无计划」「无知识」样例（充电、拖布、路线、App…），模型正确地没有硬选计划 → standard_flow，与 expected_outcome 一致，这正是 09 §3.2 想要的行为。
  - **grade 让 plan_match 变差（41 → 39）**，两条回归都是金标段落被判 irrelevant：a2-01（S1 Pro 不吸 → filter_clog，滚刷段被剔）、sb-03（墙边扫不到 → hair_wrap，边刷 c21 段被剔）。按 chunk 级统计，99 次剔除里真正剔掉金标段落的有 4 次；`grade_false_negative: 43` 是我这个指标的口径问题（金标是文档级，一份手册的多数子块本来就与该问题无关），看报告时以 chunk 级为准。
  - 单独探针里 grade 表现正确：文档标题块、边刷段、指示灯表格判 irrelevant，滚刷段与同症状工单判 relevant，三次重复稳定，1.5–1.8 s。**它在「命中里混了无关块」时确实有用，只是本期语料上这种噪声本来就少，收益抵不过自身误剔。**
  - 56 条里 7 条 grade 调用失败（百炼偶发限流 / 预算内重试用尽），全部落到 ungraded 不过滤、主流程无影响，符合设计。
  - 结论：**grade 默认保持关闭**，不建议在当前语料开启。语料扩大、或首轮召回噪声上升（多品类、更大 top_k）后重新用同一套 `--with-synthesize` 对照评估。

## 2026-09-13 阶段 6 实施

- **改写在本语料上根本不会触发**：`should_rewrite` 要求「实际请求的库全部 no_match」，而 56 条样例里 kb_manual 全部 ok（kb_tickets 6 条 no_match），两库同时 no_match 的样例 **0/56**。WeKnora 混合检索对任何 query 都会返回分数 ≈ 0.016 的命中，真 no_match 只在允许集合为空时出现，而那条路径按 09 §4.1 本来就不改写。因此 `query_rewrite.enabled` 在当前语料下是死代码，除非 grade 开启（graded 全不相关会被计为 no_match 参与决策，阶段 5 的 C 组里有 5 条 coverage=none）。
- `validate_rewrite` 的过严来自实现超出了设计意图。03 §1.4.2 写的是「拒绝新增未经输入支持的**部件、原因或操作**」，实现却用 `_segmentable` 要求整句都能由原文片段切出来，任何自然连接词（完成后 / 无法 / 不佳）都会被拒。改为按文档意图判定：
  - 新增**部件**检查（PARTS 列表：滚刷 / 边刷 / 滤网 / 尘盒 / 水箱 / 拖布 / 基站 / 传感器 / 触点…），原文没有且非已审核同义 → 拒 `new_part:X`；原因与操作沿用 FORBIDDEN_NEW；型号 / 数字 / 错误码检查不变。
  - **否定分方向**：凭空加否定必拒（语义翻转）；丢否定只在被否定的是真事实时拒。「不是吸力小，是有异响」这类纠正句式里的否定属于被纠正掉的旧事实，比较前剥掉（`strip_corrected_clause`，逗号可省）。「滚刷没缠头发」→「滚刷缠头发」仍然拒。
  - 新增**漂移锚点**检查：改写必须保留原症状的一个 2 字词，或一个已审核同义词（规范词或其口语说法）。改写的本职就是把口语换成说明书用语，字面重叠可能为零，所以同义映射必须算锚点；单字同义（扫 / 跑）区分度不够，不作锚点。「吸力下降」的同义表补了「吸力不足」「吸不起来」。
  - 早期严格模式保留在 `query_rewrite.strict_terms`（默认 false），需要时可一键回到旧行为。
- query.rewrite bake-off（8 样本 × 3 次，`reports/bakeoff/query_rewrite/`）：qwen-flash 0% → **100%**（706 ms，主），deepseek 0% → 88%（842 ms，差 2 pp 未达备用位门槛，失败项是模型原样返回原 query 与保留纠正从句），glm 38%。**修正过程中没有出现过「错误放行」，两轮失败全是保守拒绝**，这与设计的保守立场一致。
- **Qwen 思考模式修复端到端验证通过**：重建镜像后真实会话里 intake / synthesize / reply.stream / guide.step 四个 task 全部首次命中 domestic 主模型（qwen-flash 2068 ms、qwen-max 4662 ms、qwen-plus 2289 ms、qwen-max 2578 ms），不再降级到 deepseek。
- **验证时踩到 config 与镜像不成对的故障**：config/ 是热挂载而代码在镜像里，新版 retrieval.yaml（多了 grade / parent_expand / strict_terms）挂到旧镜像 → `RetrievalConfig` 的 `extra="forbid"` 在**首次使用时**才校验，于是 `/health` 200、容器 healthy，只有走到诊断节点的请求以 `error/node_failed` 失败。`docs/runbook/release.md` 原文写的是「直接启动失败并进入重启循环」，与实际不符且更危险（静默），已改正并补上「换 config 后必须发一条真实会话验活」。

## 待核对
- 三家模型在 grade 枚举输出上的稳定性（阶段 5 bake-off）。
- 真实 embedding 下 hybrid-search 的 latency_ms 分布（阶段 2 基线）。
