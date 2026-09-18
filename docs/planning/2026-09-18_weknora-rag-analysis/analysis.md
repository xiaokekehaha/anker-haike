# WeKnora RAG：本地会话、数据流与架构分析

分析日期：2026-09-18。RAG（Retrieval-Augmented Generation，检索增强生成）是在回答前检索资料，把相关片段交给大语言模型生成答案；这条链路不会把知识库训练进模型权重。

本文核对了[指定本地会话](http://localhost:8081/platform/chat/eb046d88-6364-4459-b47a-c28d7d00398b)、运行容器、数据库和对应源码。镜像为 v0.8.0，OCI revision 与 GitHub tag 均为 `1edcd54b43606d9079bb36650efe3f68707a79ea`。下面区分“实际发生”“源码支持”和“设计推论”，不使用不断变化的 main 解释本地版本。

**核心结论：本次使用 Quick Answer 固定问答管线；三个库做混合召回，跳过模型重排，经过父段扩展和去重后，用4条证据生成答案。海客业务服务只复用其检索层，另外施加产品范围与排障计划约束，两者不是同一条问答流程。**

## 1. 先看本地实际部署

```text
[Browser: WeKnora UI :8081]
                 |
                 | HTTP /api/v1/knowledge-chat/:session_id
                 | <--- SSE: references / answer / complete
                 v
+-----------------------------------------------------------+
| WeKnora Go app :8080                                       |
|                                                           |
| HTTP Handler -> Application Service -> Pipeline Plugins    |
|                       |                   |               |
|                ingestion workers    retrieval + generation |
+-----------------------+-------------------+---------------+
                        |                   |
          +-------------+-------------------+--------------+
          |             |                   |              |
          v             v                   v              v
     PostgreSQL       Redis           Model APIs      DocReader
     + pgvector       task queue      embedding       Python/gRPC
     + pg_search      stream state    chat / rerank    :50051
     + metadata       cancellation    (as configured) file parsing
          |
          +-- WeKnora database: KB / chunks / indexes / messages
          +-- haike database: business state, separate database

[Haike API :8000]
      |
      +-- KnowledgeAdapter -> WeKnora hybrid-search
      +-- product scope / evidence / allowed plans -> own LLM flow
```

SSE（Server-Sent Events，服务器推送事件）用于逐步返回引用和答案。Redis在此承担任务队列、流式状态与取消信号；向量和关键词索引在PostgreSQL中。本地配置 `RETRIEVE_DRIVER=postgres`、`STREAM_MANAGER_TYPE=redis`，Neo4j关闭。原文件另有本地文件卷，不能把Postgres理解成所有文件的存储位置。[部署定义](/Users/xiaoke.zhou/Documents/workspace/anker-haike/docker-compose.yml:48)

这套设计是**Go应用内的分层模块加插件管线**，不是把每个RAG阶段拆成独立微服务。插件实现统一的 `OnEvent(..., ChatManage, next)` 接口；Service决定执行哪些阶段，插件读写本轮共享状态。EventManager在进程内组织调用，不能与Redis队列混为一谈。[Plugin / EventManager](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/chat_pipeline.go#L11-L90)

## 2. 资料如何变成可检索的数据

本地导入有三种输入：

- 手册：Markdown正文作为manual knowledge发布，front matter中的品类、SKU、版本等单独写入 `custom_metadata`。
- 工单：CSV每行转换成一份独立manual knowledge，保留每条工单自己的型号和结果。
- FAQ：问答条目批量写入FAQ类型知识库。

因此这批手册与工单实际走 **manual文本处理**，不经过Python DocReader。上传PDF等文件则按解析器配置先抽取Markdown，Python/gRPC是可用路径之一。[本地导入](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/ingest.py:289)、[manual处理](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledge_create.go#L1256-L1321)、[文件解析器](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledge_process.go#L3668-L3736)

```text
Local Markdown / one CSV row
          |
          v
POST /knowledge-bases/:id/knowledge/manual
          |
          +--> knowledges: title, raw content, status, metadata
          |
          v
Redis / Asynq async task -> Go chunker
          |
          +--> parent_text, target size 800
          |       |
          |       +--> chunks table; context only
          |
          +--> text child, target size 200
                  |
                  +--> chunks table: body / parent ID / position
                  |
                  +--> title + section context + child body
                              |
                         Embedding API
                       text-embedding-v4
                           1024 dims
                              |
                              v
                        embeddings table
                       /                \
              pgvector cosine       pg_search BM25
              HNSW index            keyword index
```

Embedding是把文本转换为数值向量；它用于找语义接近的片段。BM25是关键词相关度排序，用来补充型号、错误码等精确词匹配。两个索引关联到同一个 `chunk_id`，命中后再取正文，而不是把向量本身交给回答模型。[索引构造](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledge_process.go#L517-L548)、[批量向量化](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/retriever/keywords_vector_hybrid_indexer.go#L85-L125)

父子块解决一个实际冲突：小块更容易准确命中，大块提供更完整的上下文。父块保存在 `chunks`，子块参与索引。800/200是目标大小，按分隔符切分后不一定等长；知识库保存overlap=80，但父子策略的子块重叠还会按child size派生，不能认为任意两块必重叠80字符。[父子策略](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/infrastructure/chunker/strategy.go#L148-L185)、[大小与重叠](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/infrastructure/chunker/strategy.go#L220-L244)

例如本地Q45资料：

```text
official_q45_battery.md
          |
          +-- parent: 277 characters
                 |
                 +-- child 0: [0, 148)   charging / power
                 +-- child 1: [123,277) battery life
                                     ^
                                     |
                     query matches this child
```

本地有效数据快照为：

| 知识库 | 文档/容器数 | 子块或条目数 | 父块数 |
|---|---:|---:|---:|
| haike_kb_manual | 35 | 104 | 35 |
| haike_kb_tickets | 380 | 380 | 0 |
| haike_kb_faq | 1个FAQ容器 | 116条FAQ | 0 |

工单较短，一个子块就覆盖全文时无需额外存相同父块。数据库现有BM25中文分词索引和1024维HNSW向量索引；本次未跑执行计划，索引存在不等于每次查询必走该索引。[本地证据](/Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-09-18_weknora-rag-analysis/case-evidence.md)

## 3. 这条聊天实际怎样运行

会话时间为北京时间2026-09-18 08:24:55，用户原话“电池掉电很快”。请求使用 `builtin-quick-answer`，`agent_enabled=false`、联网搜索关闭，没有指定文档或知识库。Quick Answer配置为检索全部可用知识库，因而解析出三个完整库。

实际执行的九个阶段：

```text
"电池掉电很快"
      |
      v
LOAD_HISTORY          0 previous rounds
      |
MEMORY_RECALL         skipped: workspace disabled
      |
QUERY_UNDERSTAND       deepseek-flash
      |               intent = kb_search
      |               rewrite = "电池掉电很快是什么原因"
      v
CHUNK_SEARCH_PARALLEL
      |
      +-- one embedding model shared by all 3 KBs
      |       -> one 1024-dimensional query vector
      |
      +----------------------+
      |                      |
      v                      v
Vector retrieval        Keyword retrieval
limit 150               limit 150
128 candidates          150 candidates
      |                      |
      +----------+-----------+
                 v
            weighted RRF
          215 fused candidates
                 |
              Top 10
                 v
CHUNK_RERANK           skipped: empty_model_id
                 |
CHUNK_MERGE            parent expansion + dedup
                 |
           4 remaining references
                 |
FILTER_TOP_K           limit 10; all 4 remain
                 |
INTO_CHAT_MESSAGE      format evidence + citations
                 |
CHAT_COMPLETION_STREAM -> deepseek-flash
                 |
                 +--> answer chunks via SSE -> browser
                 +--> content / references persisted
```

九阶段来自当前配置的动态组装。这里“固定管线”指步骤由程序控制，不是由模型逐轮决定调用哪个工具；某些阶段仍能按意图或配置跳过。[管线构造](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/session_knowledge_qa.go#L165-L211)

检索上限150的计算为 `min(500, max(10*5,50)*3)`。内部需要较大的候选池供融合，再把较少证据交给回答模型。因此“界面显示4条引用”不等于“数据库只找到了4条”。[候选深度](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledgebase_search.go#L158-L166)

RRF（Reciprocal Rank Fusion，倒数名次融合）不直接相加BM25分和余弦相似度，而是按名次加权：

```text
score = 0.7 / (60 + vector_rank)
      + 0.3 / (60 + keyword_rank)

未被某一路召回 -> 该路贡献0
名次从1开始
```

本地租户没有覆盖默认参数。约0.016的分数属于排名分，不是1.6%的正确率。128+150合成215还涉及按chunk归并，不能据此简单断言两个原始列表恰好重叠63项。[RRF实现](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledgebase_search_fusion.go#L80-L127)

原生聊天源码有模型重排插件，但本轮明确记录 `skip reason=empty_model_id`。模型管理里登记了gte-rerank-v2，也没有自动使本请求调用它。[空模型跳过](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/rerank.go#L38-L93)

## 4. 最终进入回答的证据与Prompt

| 证据 | 实际品类 | 结果/来源 | 本轮融合分 |
|---|---|---|---:|
| T0223，ANKER-A1289 | 充电宝 | 未解决工单 | 0.01609 |
| Space Q45 A3040电池资料 | 耳机 | 官方支持资料的中文整理 | 0.01493 |
| 家庭安防摄像头通用手册 | 摄像头 | 人工演示样本 | 0.01339 |
| T0343，EUFY-T8210 | 摄像头/门铃 | 已解决工单 | 0.01293 |

这几类内容与“电池”语义相关，但用户没有提供产品范围，所以都可能被召回。原生通用问答不会自动知道海客的SKU业务规则。

最终请求的结构是：

```text
messages
  |
  +-- system
  |     answer from retrieved materials
  |     citation protocol
  |
  +-- history                absent in this first turn
  |
  +-- user
        original question
        <retrieval>
          <document id="d1" kb="b1" title="T0223">
            <chunk id="c1">
              retrieved passage
            </chunk>
          </document>
          ... other 3 documents
        </retrieval>
        runtime time
             |
             v
          Chat LLM
             |
      short citation handles
             |
      decode to real document/chunk IDs
             |
      UI citation links + persisted references
```

短句柄是本轮的引用代号，用来减少长UUID在模型输入输出中的负担；服务保留它与真实知识、块ID的映射。[引用准备](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/references.go#L14-L97)

本轮最终模型请求有system和user两条消息，user正文1743个Unicode字符。主回答统计为1637输入token、742输出token；日志首回答片段约4.24秒，助手消息约6秒完成。token是模型计费和上下文的文本单位，不等于字符数；这些统计不包含查询改写和并行标题生成。[时间线与请求抽查](/Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-09-18_weknora-rag-analysis/case-evidence.md)

## 5. 本地案例暴露的三个具体问题

### 产品范围与元数据传递

问题：T0223的数据库品类是 `power_bank`，最终回答却把它归入“耳机类产品”。

追踪：

```text
DB custom_metadata
  category=power_bank
  sku_list=ANKER-A1289
  result=unsolved
          |
          v
IntoChatMessage
  <documents><metadata>...</metadata></documents>
          |
          v
prepareMessagesWithModelContext
  rebuild rows: IDs + title + content
  omit knowledge_metadata
          |
          v
replace original RenderedContexts
          |
          v
actual LLM request
  NO category=power_bank / NO scope metadata
  still has SKU and "unsolved" inside body text
```

这不是“模型收到了category却忽略它”。源码调用方构建新引用行时遗漏metadata，然后用新上下文替换原上下文；实际发送JSON也确认 `power_bank` 和 `<metadata>` 不存在。不能只查数据库或 `rendered_content` 就断定字段已进入模型。[遗漏字段与替换](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/references.go#L48-L97)

方案：先以已确认品类/SKU约束允许文档，再把元数据完整传入最终模型上下文。缺少型号时先澄清，避免把多个产品的方案混成一个建议。元数据保留能改善解释，服务端范围限制才提供硬约束。这里只分析，未实施修改。

### 内容去重跨越型号与工单结果

问题：去重减少重复文字，同时可能丢掉业务上不同的证据。

本轮保留T0223（ANKER-A1289 / unsolved），去掉了T0203和T0228（同型号 / solved），以及不同型号的T0208、T0213、T0218。另一组保留EUFY-T8210的已解决工单，去掉EUFY-T8213的未解决工单。

源码对全局候选比较包含关系或高比例token重叠，没有先按SKU、文档或结果分组。这个案例证明不同结果确实被折叠；不能因此证明删掉的任意一条就是正确答案。[重叠去重](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/search.go#L214-L311)

方案：业务检索先按产品约束范围；需要保留多结果证据时，在品类/SKU/结果组内去重，或者保留合并后的来源与冲突状态。是否采用属于业务层选择，通用知识问答未必需要同样规则。

### 父段扩展被后续短块处理覆盖

问题：Q45子块154字符先扩为277字符的父块，随后又退回154；摄像头97字符则保留632字符父块。

追踪：Merge先取父段，再执行短上下文扩展。Q45父段小于350字符阈值，进入后续分支；该分支重新按子块ID读取原始正文作为基底，最后覆盖已扩展的内容。本地子块没有相邻ID，因此得到原来的154字符。摄像头父段632字符超过阈值，不进入该分支。[Merge顺序](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/merge.go#L74-L99)、[短块处理](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/merge_expand.go#L131-L217)

方案：短块补全应从已有扩展内容继续，或对已完成父段扩展的结果跳过重置。属于上游实现问题；本次未改源码，也未新跑模型验证修复。

## 6. 与海客接入有什么不同

```text
WeKnora native Quick Answer          Haike business flow
--------------------------          -------------------
free-form question                  confirmed product + symptoms
          |                                     |
default all accessible KBs          allowed document IDs
          |                         (category / SKU / scope)
query understanding                             |
          |                         manual + tickets hybrid-search
hybrid retrieval                                |
          |                         local post-filter + evidence IDs
optional rerank                                  |
          |                         own synthesize model
merge / prompt / answer                          |
                                    allowed plan_id + evidence checks
                                                 |
                                    business response / workflow
```

| 维度 | 本轮WeKnora原生聊天 | 海客当前代码/配置 |
|---|---|---|
| 范围 | 3个完整库，无SKU限制 | confirmed_sku允许该SKU及同品类通用文档；category_only仅通用文档；unknown为空 |
| 查询 | 模型理解与改写 | 按已确认产品和症状确定性拼接 |
| 检索入口 | KnowledgeQA内部完整管线 | `POST /knowledge-bases/:id/hybrid-search` |
| 结果过滤 | 通用检索/内容合并 | knowledge_ids前过滤，返回后再次验证；允许集合为空不请求 |
| 重排 | 本轮因空模型ID跳过 | 适配器重排已实现，当前enabled=false |
| 父段上下文 | 原生Merge | 本地扩展已实现，当前enabled=false |
| FAQ | 本轮搜索范围包含FAQ，但最后0条FAQ证据 | 本地FAQ路径已实现，当前enabled=false |
| 回答用途 | 生成自由文本和引用 | 从允许排障计划中选择，校验plan_id和evidence_id |

本地运行容器的retrieval配置与仓库文件哈希一致；多查询、FAQ、适配器重排、父块扩展、相关性评分和查询改写目前都关闭。不能把已有代码能力当成已启用功能。[配置](/Users/xiaoke.zhou/Documents/workspace/anker-haike/config/retrieval.yaml:1)

允许集合为空直接返回no_match很关键：该检索接口的空 `knowledge_ids` 表示不限制文档，直接传空集合会意外变成整库搜索。[范围与后过滤](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/adapter.py:201)、[请求路径](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/adapter.py:313)

海客还把未解决工单排后，并在synthesize提示里要求它只能作为反证；plan_id和evidence_id做程序验证。工单是否真正支持某个方案，仍不能只靠提示词保证。[检索合并](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/search.py:112)、[计划与证据校验](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/diagnose/synthesize.py:74)

## 7. 架构设计的取舍

- **入库与问答分离**：解析、切块、向量化主要发生在导入时；提问时只向量化问题并检索索引。这控制在线延迟，代价是要维护异步状态和索引一致性。
- **存储与业务解耦**：知识、正文、索引、会话分别建模；retriever通过接口支持不同后端。本地用同一个Postgres实例降低部署复杂度，不代表代码只支持这一种存储。
- **小块检索、大块回答**：降低无关文字对检索的干扰，同时补回上下文；必须检查各处理阶段是否保留已扩展内容。
- **混合检索先扩召回，重排再提精度**：两者解决的问题不同。本轮没有模型重排，实际是RRF排名加内容合并。
- **引用可追踪，正确性仍要评估**：引用说明回答引用了哪份资料，不保证资料适用于当前SKU，也不保证工单方案曾解决问题。
- **Quick Answer与Agent分开**：前者由程序控制管线；Agent模式允许模型循环选择检索等工具、根据工具结果继续推理。本轮虽在UI记录中看到“query_understand / knowledge_search”步骤，也不代表发生了Agent工具循环；这些是快速问答阶段的展示记录。[执行分支](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/handler/session/qa.go#L937-L1030)

对当前售后场景，产品范围、结果语义、元数据与最终上下文一致性是必要约束。图谱、联网、长期记忆、多轮Agent和多模态是可选扩展，不能替代这些约束。本轮未使用图谱、联网、图片处理或长期记忆召回。

## 证据索引与边界

- [本地运行证据、数据和时间线](/Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-09-18_weknora-rag-analysis/case-evidence.md)
- [上游入库与检索源码详解](/Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-09-18_weknora-rag-analysis/upstream-retrieval.md)
- [上游聊天与上下文源码详解](/Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-09-18_weknora-rag-analysis/upstream-chat.md)
- [本地Q45入库源文件](/Users/xiaoke.zhou/Documents/workspace/anker-haike/data/knowledge/kb_manual/official_q45_battery.md:1)
- [本地T0223源工单](/Users/xiaoke.zhou/Documents/workspace/anker-haike/data/knowledge/kb_tickets/tickets.csv:224)

本次是单会话的源码和运行记录分析，没有发起新模型请求、写数据库、改业务代码、做召回率评测或性能压测。单例可证明实际执行过程和上述字段/去重行为，不能代表整体回答质量。浏览器会话未登录，因此案例证据来自同一session ID的本地数据库和容器日志。
