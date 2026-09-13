# 智能体式 RAG（Agentic RAG）方案评估

日期：2026-09-13　状态：评估稿，未实施　范围：diagnose 阶段的知识召回链路

## 0. 结论先行

| 问题 | 结论 |
| --- | --- |
| 现在的检索链路是什么形态 | 固定管线 RAG：纯函数拼 query → 每库一次混合检索（WeKnora BM25 + 向量 + 重排）→ 可选一次受控改写（默认关）→ synthesize 从预写计划枚举里选 |
| 完整的智能体式 RAG（ReAct 循环 / 多智能体）现在可行吗 | **不建议**。与 D15、R5、09 §4.1「至多两轮、不开改写循环」正面冲突；国产链 json_object 下工具调用可靠性未验证；语料只有 4 份手册 + 200 条工单，多跳 / 多轮探索没有收益，却要付 5–10 s 延迟和可回放性 |
| 有没有值得做的「有界智能体化」 | **有，且可行**。在现有两轮上限内加：证据相关性评分（CRAG-lite）、确定性同义扩展多查询 + RRF 合并、parent chunk 扩展（small-to-big）、开启已实现的改写。预计额外 +1 次轻量模型调用（≈1 s），不破坏任何规则 |
| 前置条件 | 先有检索评测集（≥50 条口语样例 + 期望命中文档 / 分块），否则任何改动都无法证明收益。这正是票 32 遗留的人工标注缺口 |

## 1. 现状基线

代码入口：`orchestrator/app/knowledge/adapter.py`（KnowledgeAdapter）、`orchestrator/app/diagnose/query.py`（query 规范化）、`orchestrator/app/diagnose/rewrite.py`（受控改写）、`orchestrator/app/diagnose/synthesize.py`、`orchestrator/app/sessions/graph.py`（retrieve / vision 节点）。

| 维度 | 现状 |
| --- | --- |
| 检索引擎 | WeKnora v0.8.0，父子分块 800 / 200，混合检索 + 重排，图谱关闭；embedding / rerank 走百炼远程 API（D17） |
| 语料规模 | kb_manual 4 份 Markdown 约 9.5k 字 + FAQ；kb_tickets 200 行 CSV。全部约 192 KB |
| 查询构造 | `build_query`：产品词 + 有效症状固定拼接，纯函数，不调模型 |
| 范围控制 | KnowledgeScope 按 product_state 映射 knowledge_ids；允许集合为空直接 no_match，禁止整库搜索 |
| 轮次上限 | 每 run 首轮 + 至多一次补检索；图片观察补检索与改写补检索二选一（09 §4.1） |
| 改写 | 已实现，默认关闭；validate_rewrite 极严格，bake-off 中候选被全拒（rewrite 100 / 12），瓶颈在词表而非模型 |
| 降级 | ToolResult 四态 ok / no_match / unavailable / replay；无证据时走预写计划或 R5 升级，禁止常识假设 |
| 预算 | 文本轮 run deadline 25 s，含图轮 40 s；单次模型调用国产链 0.9–1.2 s（DeepSeek）、2.4–2.7 s（GLM） |
| 结构化输出 | 国产链只有 json_object 可用；智谱静默忽略 json_schema。Router 走 `with_structured_output`，没有生产路径依赖原生 tool calling |

现有失败模式判断：语料很小且单品类，召回失败几乎全是**词汇失配**（口语 vs 说明书用语），而不是覆盖不足、多跳推理或长文档定位。这决定了「智能体化」该往哪个方向投。

## 2. 候选方案与逐项评估

评分说明：收益 / 成本 / 治理冲突 / 可测性，各项 高 / 中 / 低。

### 2.1 ReAct 式检索智能体（模型自己决定搜什么、搜几次、何时停）

- 形态：把 hybrid_search 暴露为工具，模型循环 thought → search → observe，直到自认为证据足够。
- 收益：低。语料 4 份文档，模型多搜几次搜到的还是那几段。
- 成本：高。每轮 1 次模型调用 + 1 次检索，3–5 轮即 5–10 s；含图轮预算更紧。
- 治理冲突：**高**。D15「不让模型临时组织操作」、09 §4.1「不能另开改写循环」、03 §1.4.1 规则 4「不增加多查询扩展、第二套重排或额外重试层」全部冲突。改写文本不是证据的原则也难以在循环里守住。
- 可测性：低。回放 / fixture 体系（R11）依赖确定性轮次，循环步数不定难以录制。
- 模型层风险：国产链原生 tool calling 未做 bake-off；智谱忽略 json_schema 说明协议兼容层薄。
- 结论：**现阶段否决**。语料扩到多品类数百文档、且出现跨文档多跳问题（如质保政策 × 手册 × 工单交叉）时再评估。

### 2.2 多智能体（planner / retriever / critic）

- 同 2.1 的所有问题再乘以角色数；单机 Compose 演示环境下额外调用与编排复杂度不成比例。
- 结论：**否决**。

### 2.3 Self-RAG / CRAG：检索后评分与纠正（有界反思）

- 形态：首轮命中后加一个 `retrieve.grade` 节点，轻量模型对每条 hit 输出 `{evidence_id, relevant: yes|no|ambiguous}`（json_object 枚举，一次调用批量评）。全部 no → 视同 no_match，进入既有改写 / 预写计划 / R5 路径；部分 no → 过滤后再进 synthesize。
- 收益：**中高**。现有链路只处理「零命中」，不处理「命中了但不对」（假阳性直接喂给 synthesize）。评分补上精确率这一侧，也让 synthesize 输入更干净。
- 成本：低。+1 次 qwen-flash / deepseek 调用 ≈ 1 s，max_tokens 可控在 256 以内；不新增检索轮次。
- 治理冲突：低。不产生业务事实、不扩大范围、不改轮次；「评分不是证据」与「改写不是证据」同构。
- 可测性：高。输入输出都是结构化枚举，可录回放；可离线跑评测集算 precision@k 变化。
- 风险：模型假阴性把好证据滤掉。缓解：只在 relevant=no 且非 ambiguous 时过滤；至少保留分数最高一条；trace 记录被滤条目。
- 结论：**推荐，第一优先**。

### 2.4 确定性多查询扩展 + RRF 合并

- 形态：首轮不只发一个 query，而是用 `config/retrieval.yaml` 的已审核同义词表确定性生成 2–3 个变体（如「扫地机器人 不吸」→ 追加「扫地机器人 吸力下降」），并行打 WeKnora，按 Reciprocal Rank Fusion 合并去重后再 top_k。
- 收益：中高。直接针对词汇失配这个主要失败模式，且不依赖模型。
- 成本：低。零模型调用；检索请求并行，端到端延迟约等于单次检索。WeKnora 并发压力可控（语料小）。
- 治理冲突：中。03 §1.4.1 规则 4 明文「不增加多查询扩展」，需要一条设计修订（00_decisions 新增决策项）说明理由：扩展来自已审核词表而非模型，范围仍由 scope 控制。
- 可测性：高。纯函数 + 确定性合并。
- 结论：**推荐，第二优先**，与 2.3 组合。

### 2.5 Small-to-big：命中子块后取 parent chunk

- 形态：WeKnora 命中已返回 `parent_chunk_id`；对 top 命中拉父块（800 字）替换 200 字子块作为 synthesize 上下文。需确认 WeKnora v0.8.0 有单块读取接口，或在导入时本地保留父块映射（ingest 阶段能拿到）。
- 收益：中。synthesize 看到完整步骤段落而不是被切断的 200 字，减少「有证据但步骤缺一半」。
- 成本：低。若 WeKnora 无接口则 ingest 时本地存一份父块表，零运行时模型开销。注意 MAX_CHARS=2000 的上限要相应调整（父块 800 × top_k 5 会超）。
- 治理冲突：无。
- 结论：**推荐，第三优先**，可独立实施。

### 2.6 Adaptive RAG 路由（先判断要不要检索、检索几深）

- 形态：intake 之后判「是否需要知识」：明确错误码 / 部件名 → 先走 faultcards / FAQ 确定性查找；纯情绪 / 求助人工 → 不检索。
- 现状：graph 里 request_human / R3 / R4 / 凭证路径已经不检索，faultcards 模块已存在。剩余增量是「错误码优先精确匹配」这一小步。
- 结论：**小改即可**，归入 2.4 的首轮策略：有错误码时先精确检索 FAQ，命中则跳过向量检索。

### 2.7 GraphRAG / 知识图谱

- WeKnora 支持图谱但导入时关闭。4 份文档、单品类，实体关系（部件 → 症状 → 步骤）已由 faultcards 与预写计划显式编码，图谱是重复建设。
- 结论：**否决**，多品类、多代产品互相引用时再看。

### 2.8 会话级检索记忆（多轮 query 浓缩）

- 现状 rediagnose 已复用 intake 抽取并重建 query，symptoms 支持替换 / 补充。
- 结论：已覆盖，不需要额外的「对话历史压缩」节点。

## 3. 推荐方案：有界智能体化（Bounded Agentic Retrieval）

```text
build_query ─┬─ 确定性同义扩展 → 2–3 个 query 并行 hybrid_search（每库）→ RRF 合并 → top_k
             └─ 错误码 / 部件精确匹配 FAQ（有则优先）
       ↓
retrieve.grade（+1 轻量模型调用，枚举输出）→ 过滤假阳性；全部不相关 → 视同 no_match
       ↓
parent chunk 扩展（本地映射，无模型调用）
       ↓
no_match → 既有路径：一次受控改写（开启）→ 补检索一轮 → 预写计划 / R5
       ↓
synthesize（不变）
```

轮次上限不变（首轮 + 至多一次补检索），新增模型调用只有 grade 一次。

### 3.1 预算核算（文本轮，国产链）

| 环节 | 现状 | 方案后 |
| --- | --- | --- |
| intake | ≈ 0.9 s | 不变 |
| 首轮检索 | 1 次 / 库 | 2–3 次 / 库并行，墙钟时间 ≈ 单次 + 少量 |
| grade | 无 | ≈ 1 s |
| synthesize | ≈ 1.2 s | 不变，输入更干净 |
| 合计增量 | | **≈ +1 s**，远在 25 s deadline 内；含图轮 40 s 同样有余量 |

### 3.2 需要改动的面

| 项 | 内容 |
| --- | --- |
| 设计文档 | 00_decisions 新增决策：允许基于已审核词表的确定性多查询扩展与一次相关性评分；修订 03 §1.4.1 规则 4 与 09 §4.1 表述 |
| config/models.yaml | 新增 task `retrieve.grade`，链 `[qwen-flash, deepseek, glm-flash]`，effort low，max_tokens 256 |
| config/retrieval.yaml | 新增 `multi_query.enabled / max_variants`、`grade.enabled / keep_min`、`parent_expand.enabled`；`query_rewrite.enabled` 在评测通过后置 true |
| knowledge/adapter.py | 多 query 并行与 RRF 合并；parent 块映射；MAX_CHARS 调整 |
| diagnose/ 新模块 grade.py | 评分 prompt、Schema、过滤规则、trace 字段 |
| sessions/graph.py | retrieve 节点内串接，不新增图节点（保持回放契约） |
| retrieval_trace | 新增 variants、fused_rank、grade 结果、filtered_ids |
| 评测 | `data/eval/retrieval/` ≥ 50 条口语样例（含 A1–A3 演示案例变体），指标：hit@5、precision@5、错配数、端到端 p50 / p95 |

### 3.3 实施顺序与工期

1. 评测集与离线跑分脚本（复用 knowledge/cli.py 与 replay 体系）：1–2 天。没有这一步不动代码。
2. 确定性多查询 + RRF + 错误码优先：1 天。零模型风险，先看 hit@5 变化。
3. parent chunk 扩展：0.5–1 天。
4. retrieve.grade：1–2 天，含 bake-off 三家模型的枚举稳定性。
5. 用评测集对照后开启 query_rewrite，同时修 validate_rewrite 词表过严的问题：1 天。

合计约 1–1.5 周，每步可独立开关、独立回滚。

## 4. 主要风险

| 风险 | 缓解 |
| --- | --- |
| grade 假阴性丢掉正确证据 | 只过滤明确 no；保留最高分一条；trace 可审计；评测集上监控 hit@5 不下降 |
| 多查询让 WeKnora 混合检索返回更多噪声 | RRF 后仍 top_k 截断；grade 兜底；每变体 match_count 不放大 |
| WeKnora `knowledge_ids` 语义怪异（空列表 = 不过滤） | 沿用现有本地后过滤兜底，多查询每次都传非空允许集合 |
| 含图轮串行读图 + grade 叠加 | grade 与 vision 结果合并后只评一次；剩余 < 3 s 时跳过 grade（与第二轮检索同规则） |
| 设计文档与代码漂移 | 先改 00 / 03 / 09，再动代码；票内 findings 回填 |

## 5. 不做的事与再评估触发条件

- 不做 ReAct 循环、多智能体、GraphRAG、模型驱动的多查询生成。
- 再评估触发：语料扩到多品类 ≥ 100 份文档；出现需要跨库多跳组合才能回答的问题；模型链完成原生 tool calling bake-off 且通过率 ≥ 95%；产品接受 40 s 以上的诊断等待。

## 6. 与 docs/planning/2026-09-13_agentic-rag-evaluation 的对照（2026-09-13 复核）

该目录的评估由另一次任务产出。其列出的代码事实已逐条核对，全部成立，且有 4 条是本 spec 遗漏的实际缺口，应单独开票：

| 事实 | 位置 | 性质 |
| --- | --- | --- |
| 两库检索 for 循环串行 | `sessions/graph.py:815` `_search_round` | 性能缺口，改 gather 即可，零风险 |
| `second_round_budget_ms` 只在配置里定义，执行器未消费；补检索只检查开始前剩余时间 | `sessions/graph.py:958–1035` vs `diagnose/config.py` | 与 08 §8「补检索整轮 ≤ 3 s」不符 |
| 第二轮有命中时整体替换首轮 hits，不合并 | `sessions/graph.py:971、1038` | 设计取舍未明示；合并去重更合理 |
| `counter_evidence` 在 `Hit.as_evidence_item()` 丢失，synthesize 看不到工单是否 unsolved | `knowledge/adapter.py` / `diagnose/synthesize.py:154` | 正确性缺口：失败工单与成功工单在模型眼里无区别 |
| manifest 仍是 stub-embedding-1024，真实 embedding / rerank 未在本机验证 | `data/knowledge/manifest.json` | 任何检索评测前必须先跑通真实链路 |

两份评估的主结论一致：不上自主 ReAct / 多智能体，保持首轮 + 至多一次补检索，在 LangGraph 内做有界子图。分歧与我的意见：

1. **控制权给谁。** 对方首版让模型控制器在 answer / search / expand / clarify / fallback 里选动作，子图最多 4 次模型调用。本 spec 主张第一阶段动作确定性化：search 用已审核同义词扩展，expand 对 top 命中一律取父块，只保留一次 grade 调用。理由是当前失败模式是词汇失配而非缺乏规划，且 03 §1.4.1 规则 4、09 §4.1、D15 对模型自主决策有明文限制，对方评估没有正面处理这几条，落地前需先改设计文档。
2. **clarify 动作。** 从检索子图发起追问会新增一条状态路径，涉及 08 会话契约、澄清计数与卡片，不是子图内部改动。建议一期不做，沿用现有 disambiguate / clarify。
3. **规模口径。** 对方评估按生产系统写（租户权限、draft / approved / published / withdrawn 发布状态、100–200 条真实脱敏工单、灰度）。本项目是赛道演示，D3 规定全部模拟数据、D8 单机 Compose。§5 的四项数据层前置若当作门禁，一期什么都做不了；应降为「真实 embedding 链路跑通 + 50 条以上标注样例」这两项。
4. **WeKnora 内置 Agent 对照组。** 研究扎实（默认 50 轮、LLMCallTimeout 是流静默超时），但适配器已实测 `/knowledge-search` 忽略 knowledge_ids，内置 Agent 的隔离风险很高。同意对方「1–2 日 spike」的定位，不建议进正式对照。

对方的验收指标设计（C 对 B 的增量、困难子集 +5 pp、普通路径 p95 增量 ≤ 1 s、越界引用为 0）比本 spec 更完整，建议直接采用。
