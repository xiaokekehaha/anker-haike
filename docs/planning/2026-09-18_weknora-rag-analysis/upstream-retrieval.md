# WeKnora v0.8.0 入库与检索源码分析

核对日期：2026-09-18。源码固定在提交 `1edcd54b43606d9079bb36650efe3f68707a79ea`。本文依据该提交的实现；本地会话与数据库证据由主代理只读核对并汇入本文，完整案例见主分析文档。已完整阅读本文分析的主要实现文件；没有执行导入、模型调用或数据库修改。

## 1. 核心边界

RAG（Retrieval-Augmented Generation，检索增强生成）把问题相关的资料取回，再作为上下文交给生成模型。WeKnora 在代码上分成两条独立链路：入库时解析、切片、建索引；提问时召回、融合、重排、组装上下文。`HybridSearch` 本身结束在召回结果补全，不调用答案生成模型，也不调用重排模型。[HybridSearch](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledgebase_search.go#L93-L269)、[重排插件](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/rerank.go#L38-L93)

```text
                      写入链路
文件 / URL ---> 异步解析 ---> Markdown ---> Go 切片器
手工 Markdown -------> 异步任务 ------------+
                                           |
                          +----------------+----------------+
                          |                                 |
                    chunks 表                         索引内容
                 原文、父子关系                标题 + 小节标题 + 子段
                          |                                 |
                          |                          Embedding 模型
                          |                                 |
                          |                       embeddings 表
                          |                       /             \
                          |                  pgvector          pg_search
                          |                  语义向量          BM25关键词
                          |                       \             /
                          |                        \           /
问题 ---> 查询向量 + 查询文本 ---> 双路候选 ---> RRF 融合、去重
                          |                           |
                          +---- 按 chunk_id 读正文 <--+
                                                      |
                         上层：Rerank -> Merge -> 生成答案
                                     父段扩展
```

图中的 `pgvector` 是 PostgreSQL 的向量检索扩展；`pg_search` 是 ParadeDB 的全文检索扩展。两者作用于同一张 `embeddings` 表，分别建立 HNSW（近似最近邻图索引）和 BM25（关键词相关度排序）索引，并不是把全部文档直接交给聊天模型。[索引迁移](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/migrations/versioned/000002_embeddings.up.sql#L15-L77)

## 2. 入库实际怎么走

### 文件与手工内容不同

文件上传先检查文件、去重、保存原文件，再创建 `knowledge` 记录，初始为 `pending/disabled`，最后提交 Asynq 文档处理任务。HTTP 上传完成与可检索不是同一个时刻。[文件创建](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledge_create.go#L146-L283)

手工 Markdown 保存为 `manual` 类型；`draft` 只保存内容，`publish` 才提交 `manual:process` 任务。worker 调用 `triggerManualProcessing`，直接使用 Go 切片器；这条链路不需要把 Markdown 再送到 Python DocReader。[手工发布](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledge_create.go#L726-L851)、[直接切片](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledge_create.go#L1256-L1321)、[worker 入口](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledge_process.go#L3075-L3175)

文件或 URL 的 `convert` 根据 parser engine 选择 `DocReader` 实现；远端 Python 路径通过 gRPC，返回 Markdown、图片和元数据。当前 Go gRPC 适配器优先调用 `ReadStream`，先接收文字/元数据，再接收图片。Python DocReader 的职责是解析；文件解析后的切片仍发生在 Go 服务中。不能把所有文件格式都写成“必须经过 Python”：源码允许其他 reader 实现，由解析引擎配置决定。[reader 选择与调用](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledge_process.go#L3668-L3736)、[gRPC 适配](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/infrastructure/docparser/grpc_parser.go#L110-L197)、[Python 响应](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/docreader/main.py#L226-L273)、[Go 切片](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledge_process.go#L3536-L3592)

### 父子切片为什么存在

父子切片解决“短片段便于精确匹配，长片段便于理解上下文”的冲突。先切较大的 parent，再把每个 parent 切成 child；child 保存 `ParentChunkID`。实际只有一个 child 且与 parent 完全相同时，不额外存相同 parent。父段 `parent_text` 存在 `chunks` 表中，但不进入向量索引；`text` 子段负责被搜索命中。[二级切片](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/infrastructure/chunker/strategy.go#L148-L185)、[父子持久化](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledge_process.go#L388-L478)、[只索引子段](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledge_process.go#L517-L548)

```text
一篇说明书
  |
  +-- P1：完整章节，parent_text -----------> chunks，仅作上下文
       |
       +-- C1：段落 A，text ---------------> chunks + embedding + BM25
       +-- C2：段落 B，text ---------------> chunks + embedding + BM25
       +-- C3：段落 C，text ---------------> chunks + embedding + BM25

查询命中 C2 -> 对 C2 重排 -> Merge 读取 P1 -> 给生成模型较完整上下文
```

切片器的代码默认值为普通段 512 字符、重叠 80 字符；启用父子切片且没有显式大小时，父段 4096 字符，子段 384 字符，子段重叠取子段大小的五分之一。这些是回退值，不能替代本地知识库的实存配置。切片策略可选择标题、启发式、递归或 auto；空策略实际走 legacy，源码入口注释中“empty or auto”的说法与分支不同，应以分支为准。[大小与重叠](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/infrastructure/chunker/splitter.go#L98-L111)、[父子配置](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/infrastructure/chunker/strategy.go#L220-L244)、[策略分支](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/infrastructure/chunker/strategy.go#L273-L294)

### 原文和检索索引是两份有联系的数据

`chunks.Content` 保留段落内容；索引输入会把文档标题、小节标题上下文加到子段前面，提高问题与陈述型资料的匹配能力。索引表通过 `chunk_id` 回连正文。`SourceID` 表示具体索引条目：普通子段的 `SourceID == ChunkID`；启用问题生成时，一个子段可以有多个问题索引，共同指向同一个 `ChunkID`，因此“向量条数”不一定等于“正文段数”。[索引内容构造](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledge_process.go#L528-L548)、[标题拼接](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledge_index_content.go#L9-L21)、[问题索引](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledge_process.go#L2046-L2089)

`BatchIndex` 对这些输入批量计算 embedding，再批量写存储；Postgres 使用 `halfvec` 存向量，并另存 `dimension`。当前迁移同时为 1024 维添加 HNSW 部分索引；是否真正命中索引仍需要实际执行计划判断，不能单靠存在索引下结论。[批量 embedding](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/retriever/keywords_vector_hybrid_indexer.go#L85-L125)、[Postgres 结构](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/repository/retriever/postgres/structs.go#L15-L28)、[1024 维索引](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/migrations/versioned/000059_embeddings_hnsw_1024.up.sql#L30-L44)

索引完成后可以启用文档检索，摘要、问题生成、图片 OCR/描述等后处理仍可能继续；`parse_status` 因而可能保持 `processing`。这些后处理是扩展能力，不是每次基础 RAG 召回都要重新执行。[状态更新](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledge_process.go#L169-L203)、[后处理入队](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledge_process.go#L639-L689)

## 3. 查询链路与分数

`HybridSearch` 加载并授权检索范围内的知识库，验证共享 embedding 空间；查询向量在同模型组中计算一次并复用，然后按存储绑定组织检索。文档库可以走向量和关键词两路；FAQ 库按该服务的参数构造只走 FAQ 向量检索，不加关键词路。[范围与向量复用](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledgebase_search.go#L117-L194)、[文档/FAQ 路由](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledgebase_search.go#L353-L433)

对单次 `HybridSearch`，内部候选深度为：

```text
pool = min(500, max(MatchCount * 5, 50) * 知识库数量)

示例：MatchCount=10，三个知识库
pool = min(500, max(50,50) * 3) = 150
```

这个 150 是候选深度，不是最后拼进提示词的段数。融合后先截取 `MatchCount` 个主要命中，再从正文表补充关联段、相邻段等，所以默认补全开启时最终返回长度也可能超过 `MatchCount`。[候选深度与截断](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledgebase_search.go#L158-L166)、[补全入口](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledgebase_search.go#L263-L269)、[补全关系](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledgebase_search_results.go#L133-L176)

| 阶段 | 实际计算 | 解决的问题 |
| --- | --- | --- |
| 向量召回 | `1 - cosine_distance(query_vector, chunk_vector)`，按阈值和 TopK 筛选 | 不同措辞表达相近含义 |
| 关键词召回 | `content ||| query`，按 `paradedb.score(id)` 排序 | 型号、错误码、专有名称等精确词 |
| RRF 融合 | 用两条候选列表中的名次计算融合分 | 两路原始分数量纲不同 |
| Rerank 重排 | 将问题与候选文本交给重排模型 | 判断具体片段是否真正回答问题 |

向量和关键词 SQL 的实际实现分别见 [VectorRetrieve](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/repository/retriever/postgres/repository.go#L265-L401) 与 [KeywordsRetrieve](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/repository/retriever/postgres/repository.go#L164-L232)。这里的关键词检索使用 ParadeDB BM25；初始迁移对内容指定 `chinese_lindera` 分词器。[BM25 分词配置](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/migrations/versioned/000002_embeddings.up.sql#L40-L51)

RRF（Reciprocal Rank Fusion，倒数名次融合）公式是：

```text
score(chunk) = w_vector / (k + rank_vector)
             + w_keyword / (k + rank_keyword)

某一路没命中：该路贡献 0
rank 从 1 开始
默认：k=60，w_vector=0.7，w_keyword=0.3
```

只有两路都有结果时才用 RRF；单一路则按 `ChunkID` 去重并保留最高原始分。默认两个榜单都排第一的上限约为 `1/61 = 0.016393`。因此 RRF 出现约 `0.016` 不能解释为“只有 1.6% 相关”；它不是相关概率。权重来自租户 `retrieval_config`，可自定义且代码不要求和为 1，本地须以实存配置为准。[RRF 实现](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledgebase_search_fusion.go#L31-L48)、[公式与名次](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledgebase_search_fusion.go#L80-L127)、[默认参数](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/types/retrieval_config.go#L86-L109)

主代理的本地只读检查确认：镜像 `org.opencontainers.image.revision` 与本文提交一致；租户 `10001.retrieval_config` 为 SQL `NULL`，本地这条检索因此采用 `k=60、0.7/0.3`。数据库扩展为 `vector 0.8.1` 和 `pg_search 0.22.2`；存在 `chinese_lindera` BM25 索引与 1024 维 `halfvec_cosine_ops` HNSW 部分索引，参数为 `m=16、ef_construction=64`。使用的 embedding 为 `text-embedding-v4`、1024 维。这些是运行实例的实测信息；未执行 `EXPLAIN`，不推断每次查询都使用 HNSW。

同一轮日志显示三个知识库共享模型并复用一次查询 embedding，候选深度 150；向量返回 128 条，关键词返回 150 条，按 `ChunkID` 合并后共 215 条，再保留前 10 条主要结果。`128 + 150` 与 `215` 的差额反映同一段落被多个候选索引或两路同时命中后的去重，不能未经逐条关联直接等同于两路交集大小。日志最高融合分约 `0.01609` 与上述 RRF 数值尺度一致。

## 4. Rerank 和父段扩展的准确边界

原生聊天管线的 `PluginRerank` 调用独立重排模型，以改写后的问题和候选正文评分，再做阈值筛选。之后的结果分数还会融合模型分、原召回分、来源权重，并用 MMR（Maximal Marginal Relevance，最大边际相关性）减少重复内容；所以界面最终分数也不一定等于向量余弦相似度。[模型调用与过滤](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/rerank.go#L334-L425)、[组合评分及 MMR](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/rerank.go#L461-L540)

父段扩展在 `PluginMerge`：它优先取重排结果，再读取父段，把父段内容与匹配 child 的当前正文合并。这样既保留小段精确召回，也给生成模型较长上下文。`HybridSearch` 虽会查找父 ID，但 `isSearchableChunk` 不把 `parent_text` 当作独立搜索结果返回；不能画成“数据库先返回所有父段，再对父段重排”。[合并顺序](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/merge.go#L33-L105)、[实际父段扩展](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/merge.go#L318-L343)、[搜索结果类型过滤](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledgebase_search_results.go#L337-L352)

## 5. 限制与设计含义

- `HybridSearch` 与完整原生聊天流程边界不同。只调用检索 API 的外部应用不会自动得到 `PluginRerank`、`PluginMerge` 和答案生成；应逐个核对调用方行为。上述类的职责分离由其入口与返回路径直接体现。
- `KeywordThreshold` 虽传入检索参数，当前 Postgres `KeywordsRetrieve` 的 SQL 实际未使用它；向量阈值则明确进入 SQL。不能把 UI 上两个阈值都说成在该驱动中同样生效。[参数传递](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledgebase_search.go#L417-L433)、[关键词实现](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/repository/retriever/postgres/repository.go#L164-L261)
- `content` 在索引表与正文表各有一份，承担不同职责；后续用 `chunk_id` 读取正文而不是直接返回命中的索引文本，因此命中辅助问题时，仍可向上层返回它所指向的原始段落。[正文补全](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledgebase_search_results.go#L24-L42)、[结果构造](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledgebase_search_results.go#L301-L332)
- 父子切片、混合召回、模型重排分别处理不同损失：上下文被切断、语义与精确词召回互补、候选不够相关。异步解析和可替换 retrieval engine 是工程扩展，是否需要图谱、联网搜索、图片理解要看知识类型和实际配置。
- 本文未做性能压测、召回率标注评估或 SQL 执行计划检查；源码能力不能自动等同于本地配置启用了该能力。
