# 向量库选型决策：现在不切，切也不是 FAISS / Chroma

日期：2026-09-14。分支 `feat/memory-optimization`。触发问题：赛题解析文档提到「技术路线自选（FAISS、Chroma 等）」，是否需要把向量检索从当前方案切走。

本文只做决策记录与迁移契约，**不改动任何代码或配置**，未重跑评测、未访问数据库；引用的评测数字全部来自既有报告。

## 结论

1. **现在不切。** 在当前语料规模（手册库 13 个子块、全库 203 条知识 + 50 条 FAQ）上，ANN 索引结构对召回和延迟都无可测影响；既有 A/B/C/P/G 五组评测也证明检索层指标已饱和。
2. **赛题没有要求换库。** 「FAISS、Chroma 等」是举例，真正的约束是「不要直接套 Bedrock KB，因为切片 / 向量化 / 检索 / 重排是黑盒，无法做精准召回策略」。评的是召回策略可控可讲，我们的适配器层已经满足。
3. **将来真要动，目标是现有 Postgres 的 pgvector 自建索引，不是新增 FAISS / Chroma。** 触发条件与迁移契约见 §4、§5。
4. **需要诚实承认的一点**：WeKnora 对我们也是半个黑盒，我们已经绕开了它四项能力。对外表述应落在「自研召回策略层」，不能落在「用了 WeKnora」。

## 1. 现状事实

### 1.1 检索不是一个可替换的独立组件

向量检索在 WeKnora v0.8.0 内部，`RETRIEVE_DRIVER: postgres`，用的是 WeKnora 官方镜像自带的 **pgvector + pg_search（BM25）**（[docker-compose.yml:48](../../docker-compose.yml)、`weknora-app` 环境变量段）。编排服务与 WeKnora **共用同一个 Postgres 实例、各自独立数据库**。

因此「换 FAISS / Chroma」不是换一个库，而是把整个知识服务替掉，连带：

| 一并失去 | 现有实现 |
| --- | --- |
| 文档解析 | `weknora-docreader` 容器 |
| 父子分块（800 / 200） | WeKnora chunking_config |
| 入库幂等、doc_version 比对、删旧建新 | [ingest.py](../../orchestrator/app/knowledge/ingest.py) 419 行 |
| BM25 混合检索 | pg_search，WeKnora 侧 RRF 融合 |
| manifest / snapshot / replay 可复现链路 | `data/knowledge/manifest.json`、`snapshots/`、票 43 ReplayKnowledgeAdapter |

### 1.2 语料规模

- `data/` 全部知识源 **396 KB**；`tickets.csv` 200 条；手册 / 排障手册 3 份；FAQ 50 条。
- manifest 记录：入库 203 条知识 + 50 条 FAQ entries，embedding `text-embedding-v4` / 1024 维。
- 关键数字：**手册库只有 13 个子块**（[bounded-agentic-rag/findings.md:67](../planning/2026-09-13_bounded-agentic-rag/findings.md)）。

### 1.3 已经绕开的 WeKnora 四项能力

| 能力 | WeKnora v0.8.0 实际表现 | 我们的绕法 |
| --- | --- | --- |
| FAQ 检索 | 导入成功、KB 状态 available，但 `faq/search` / `hybrid-search` / `knowledge-search` 对 FAQ 库全部返回空 | 本地 `LocalFaqIndex`（[faq.py](../../orchestrator/app/knowledge/faq.py)，字符二元组 Dice + 子串加分，阈值 0.3） |
| rerank | KB 对象没有 `rerank_model_id` 字段，创建 / 更新静默忽略 | 适配器自己调百炼 `gte-rerank-v2`（[rerank.py](../../orchestrator/app/knowledge/rerank.py)） |
| 分值 | `hybrid-search` 只回 RRF 名次分 0.0154–0.0164，无区分度 | 跨库按库内名次再做一次 RRF（`search.interleave_kbs`），绝对阈值判「无知识」改由 grade 承担 |
| `knowledge_ids` 范围过滤 | `/knowledge-search` 完全忽略；`hybrid-search` 遵守但空列表等于不过滤 | `match_count = max(top_k*3, top_k)` 过取 + 本地按 `knowledge_id` 后过滤（[adapter.py:330](../../orchestrator/app/knowledge/adapter.py)、[adapter.py:341](../../orchestrator/app/knowledge/adapter.py)） |

四项里只有最后一项与「向量库选型」相关，且只在扩容后才致命（§4.1）。

## 2. 为什么现在不切

### 2.1 检索层指标已饱和，换索引看不出差别

A 组基线（56 条，`reports/retrieval/20260913T033959Z_A.md`）：hit@5 **96%**、chunk_hit@5 **98%**、precision@5 65%、leak 5/5、p50 **549 ms** / p95 821 ms。

findings 的原话：语料太小导致检索指标饱和，手册库 13 个子块、top-5 就覆盖单份手册的大半，**任何检索层改动在 hit / chunk_hit 上都看不出差别**。

- 召回：几十到几千向量的规模，FAISS Flat、HNSW、pgvector 顺序扫描的 recall 都是 100%。
- 延迟：549 ms 里绝大部分是远程 embedding 的网络往返（评测脚本两库串行，单库约 270 ms 含 embedding），换本地索引省不掉这一段。

### 2.2 已记录的失败项，逐条对照换库能否解决

| 现象 | 真因 | 换 FAISS / Chroma |
| --- | --- | --- |
| 5/5 无知识样例泄漏 | RRF 名次分无区分度，无法做绝对阈值 | 部分解决（能拿原始余弦分），但阈值仍需在标注集上校准；当前由 grade 承担 |
| `query_rewrite` 0/56 触发、实为死代码 | 同上：任何 query 都返回 ≈0.016 的命中，真 no_match 只在允许集合为空时出现 | 同上 |
| FAQ 库检索恒空 | WeKnora 缺陷 | 无关，已本地绕过 |
| rerank 配了不生效 | WeKnora 缺陷 | 无关，已自己调 |
| 范围过滤靠 ×3 过取 + 本地后过滤 | WeKnora 接口缺陷 | **可解决**，但见 §4.1 的时机判断 |
| 六个开关默认全关、评测集 56 条标注 0 条 | 评测没闭环 | 无关；且换库会让 A / B / C / P / G 五组报告全部作废、需重跑重标 |

### 2.3 机会成本

预赛材料 2026-09-27 截止。[gap-analysis](../planning/2026-09-14_hackathon-brief-gap-analysis/gap-analysis.md) 的 P0 是 **L3 业务办理零覆盖**（动作注册表、政策引擎、授权门、回执、case 对象）。检索侧在 P2，且 P2 写的是「**启用并评测**六个检索开关」——那件事不需要换库。

换库的代价：重写 ingest（419 行）、重建 manifest / snapshot / replay（现场演示可复现性的资产）、五组评测基线作废、`Hit` / `ToolResult` 上游全部回归。收益：不可测。

## 3. 赛题口径的正确理解

赛题原文（[hackathon-brief-gap-analysis/findings.md §4](../planning/2026-09-14_hackathon-brief-gap-analysis/findings.md)）：

> 可拿到 …… AWS 的多模态理解、LLM、Embedding、向量检索、Step Functions。技术路线自选（FAISS、Chroma 等）。
> 提示：建议不要直接套 AWS Bedrock Knowledge Bases，它把切片、向量化、检索、重排封成黑盒，无法做精准召回策略。

「FAISS、Chroma 等」是**举例**，约束在下一句：**召回策略必须可控、可讲**。

我们已有的自研召回策略层（约 960 行）：

- [adapter.py](../../orchestrator/app/knowledge/adapter.py)（417）：四态结果、KnowledgeScope 范围过滤、token 预算截断、hint 面向模型可读
- [search.py](../../orchestrator/app/knowledge/search.py)（234）：多变体 RRF、跨库交错（手册 > FAQ > 工单破平、反证最后）、开关化
- [rerank.py](../../orchestrator/app/knowledge/rerank.py)（121）：适配器侧 rerank
- [faq.py](../../orchestrator/app/knowledge/faq.py)（190）：确定性本地 FAQ 索引
- 之上：父块扩展、grade、一次有界补检索（[bounded-agentic-rag/design.md](../planning/2026-09-13_bounded-agentic-rag/design.md)）

**这正是赛题想看的白盒。** 换成 FAISS 不会让它更白盒，只会把这 960 行推倒重来。

对外表述口径：强调「自研召回策略层（跨库 RRF / 范围过滤 / 父块扩展 / rerank / grade / 有界补检索），不用黑盒 KB」，**不要**强调用了哪个向量库或哪个知识服务。

## 4. 重新评估的触发条件

任一成立时重开本决策：

### 4.1 真实脱敏工单入库后规模跨量级（最可能先到）

票 [71 工单清洗管线](../planning/2026-09-14_l3-p1-real-data-multicategory/issues/71-ticket-cleaning-pipeline.md) 把 200 条合成工单换成真实批次，票 [67 多品类目录](../planning/2026-09-14_l3-p1-real-data-multicategory/issues/67-multicategory-catalog.md) 把品类从 1 扩到 ≥2。

风险：现在是 `match_count = top_k*3` 过取后本地按 `knowledge_id` 过滤。窄 SKU 范围 + 大工单库时，过取的 3×top_k 条里可能一条都不属于允许集合，**召回直接塌方**，且这种失败是静默的（表现为 no_match，不是报错）。

这是当前**唯一有硬截止的技术债**。量化阈值建议：当 kb_tickets 条数 × 允许集合占比使得「过取命中落在允许集合内的期望条数 < top_k」时必须处理。到时先测量，不要凭感觉切。

### 4.2 需要多维硬过滤

票 [70 知识按品类 / 区域入库与发布状态过滤](../planning/2026-09-14_l3-p1-real-data-multicategory/issues/70-knowledge-region-publish-state.md) 要求 `publish_state == published` 必选、区域专属文档按 `scope.region` 匹配。这类过滤条件叠加后，「过取 + 后过滤」的失效概率随过滤维度指数上升。

注意：票 70 当前设计是在 adapter 侧过滤，短期可行；它本身不构成换库理由，但与 §4.1 叠加时会。

### 4.3 需要原始相似度做绝对阈值

若要用相似度阈值判「无知识」以省掉每轮 grade 的 LLM 调用（延迟 + 成本），需要原始分而非 RRF 名次分。前置条件是评测集标注完成、阈值在标注集上校准过——**先有标注，再谈阈值**。

## 5. 迁移目标与契约（触发后才执行）

### 5.1 目标：现有 Postgres 的 pgvector 自建索引

不新增任何组件：

| 前置条件 | 现状 |
| --- | --- |
| pgvector 扩展 | [deploy/postgres/init/01-haike-db.sh](../../deploy/postgres/init/01-haike-db.sh) 末行已在 haike 库执行 `CREATE EXTENSION IF NOT EXISTS vector` |
| embedding 客户端 | [config/models.yaml:52](../../config/models.yaml) 已声明 `embed-primary: text-embedding-v4, dim 1024` |
| rerank 客户端 | [rerank.py](../../orchestrator/app/knowledge/rerank.py) DashScopeReranker 已在用 |
| BM25 | 同实例自带 pg_search |
| 事务 / 备份 / 迁移 | 与业务库同一套 SQLAlchemy + alembic |

收益：元数据过滤变成 SQL `WHERE`（sku / category / region / publish_state / doc_version 精确可组合、可测），原始余弦分可得，过取 + 后过滤的隐性失效消失。

### 5.2 不可破坏的契约

替换只允许发生在 `KnowledgeAdapter` 内部。以下保持不变，否则回归面失控：

- `Hit`（含 `evidence_id`、`score`、`rrf_score`、`full_text`、`source_queries`、`counter_evidence`）、`ToolResult`（四态 ok / no_match / unavailable / replay，含 `hint`、`truncated`、`allowed_count`、`latency_ms`）
- `KnowledgeScope`（product_state / category / sku，票 70 后加 region）
- [search.py](../../orchestrator/app/knowledge/search.py) 之上全部不改：图节点 retrieve、`haike-kb eval`、ReplayKnowledgeAdapter、retrieval_trace 事件
- manifest 的 `kb_ver` 语义（知识版本 + embedding 模型 + 维度）与 snapshot 导入导出

### 5.3 验收口径

- 同一评测集、同一知识版本、同一模型配置下与 WeKnora 基线对照：hit@5、chunk_hit@5、precision@5、leak、p50 / p95 逐项不退化。
- 范围过滤专项：窄 SKU、跨区域、draft / withdrawn 文档零召回，构造扩容规模的合成库验证（不能只在 203 条上测）。
- 回滚：适配器实现以配置切换，WeKnora 路径保留一个发布周期。

## 6. 为什么不是 FAISS / Chroma

| | FAISS | Chroma | pgvector（本方案） |
| --- | --- | --- | --- |
| 元数据过滤 | 无，需自建映射与后过滤 | 有 | SQL WHERE，任意维度组合 |
| BM25 / 混合检索 | 无，需自写 | 弱 | pg_search，同实例 |
| 持久化 / 并发 | 无服务模型，需自管文件与锁 | 有（单节点） | 与业务库同一套 |
| 增删改 | 删改需重建索引 | 支持 | SQL |
| 备份 / 快照 / 回放 | 另起一套 | 另起一套 | 复用现有 |
| 新增组件 | 是（进程内库 + 自管文件） | 是（进程 / 数据目录） | **否** |

FAISS 只解决「向量最近邻」这一件我们**当前不缺**的事；我们缺的范围过滤和混合检索它全不提供。Chroma 补上了元数据过滤和持久化，但混合检索弱，且它能给的 pgvector 全都有，代价是多一个数据存储要纳入备份、快照、回放。

补一句尺度感：13 个子块的规模上，numpy 暴力点积都够用。这本身就说明选型不是瓶颈所在。

## 7. 本次不做

- 不切换向量库、不新增 FAISS / Chroma / Milvus / Qdrant 依赖。
- 不改 WeKnora 版本、不改 ingest / manifest / snapshot。
- 不改任何检索开关的默认值（六个开关仍默认全关，启用与否归票 78 按评测决定）。

## 8. 下一步（检索侧的正事）

1. 票 [72 评测集替换](../planning/2026-09-14_l3-p1-real-data-multicategory/issues/72-evalsets-real-samples.md) / 现有 56 条标注补齐——没有标注，任何检索结论都不成立。
2. 票 [78 检索开关启用](../planning/2026-09-14_l3-p1-real-data-multicategory/issues/78-retrieval-switches-enable.md)——在 synthesize 输出上量收益（expected_plan 一致率），不只看 hit@5。
3. 真实工单到手后按 §4.1 先测量过取失效率，再决定是否执行 §5 的迁移。
