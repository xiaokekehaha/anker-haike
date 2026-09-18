# WeKnora 原生问答：源码与本地请求追踪

源码固定为 [1edcd54b43606d9079bb36650efe3f68707a79ea](https://github.com/Tencent/WeKnora/tree/1edcd54b43606d9079bb36650efe3f68707a79ea)，本地源码目录 `/tmp/haike-weknora-v080-20260918`。本地请求、日志及数据库事实由主研究提供：会话 `eb046d88-6364-4459-b47a-c28d7d00398b`，请求 `1mrR9LDxgQ0Z`。本次只读源码，未发起模型请求。

RAG（检索增强生成）是先检索资料、再把资料放进模型上下文生成回答。本地这轮使用 Quick Answer：后端预先组装一条顺序处理链。Agent 模式则让模型循环选择工具、读工具结果、继续推理；两者共用模型、知识检索服务和输出事件机制，但不是同一条执行链。

## 1. HTTP 入口与执行边界

路由分别注册 `/knowledge-chat/:session_id`、`/agent-chat/:session_id` 和无会话的 `/knowledge-search`。[routes_chat.go:101-121](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/router/routes_chat.go#L101-L121)

```text
HTTP request
   |
   v
parseQARequest
   |-- 校验会话所有权、解析 agent、合并 @知识库/@文档
   v
executeQA
   |-- 保存 user message + 空 assistant message
   |-- 创建本请求 EventBus、StreamHandler
   |-- 后台执行服务；HTTP 前台读取 StreamManager 并输出 SSE
   |
   +-- qaModeNormal --> sessionService.KnowledgeQA --> 动态 pipeline
   |
   +-- qaModeAgent  --> sessionService.AgentQA --> AgentEngine.Execute
```

`KnowledgeQA` handler 始终走普通模式；`AgentQA` handler 优先使用已解析 agent 的 `IsAgentMode()`，其次才看请求 `agent_enabled`。因此不能单凭 URL 出现 `agent-chat` 判断用了 Agent 推理循环。本地 `agent_enabled=false`、Quick Answer 配置与日志对应普通 RAG 链。[qa.go:811-895](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/handler/session/qa.go#L811-L895)

普通模式生成与持久化逻辑由 handler 的 `executeQA` 管理，包括创建消息、订阅完成事件、选择服务方法。[qa.go:897-1049](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/handler/session/qa.go#L897-L1049)

## 2. 动态 pipeline 与本轮数据流

实际入口是 `sessionService.KnowledgeQA` 的 `NewPipelineBuilder`，不是 `types.Pipeline["rag_stream"]` 的静态数组。是否有知识检索范围或 Web 搜索决定 RAG/纯聊天；历史、Web Fetch、数据分析按条件加入。阶段进入后还会再次看 query intent 决定跳过检索。[session_knowledge_qa.go:162-207](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/session_knowledge_qa.go#L162-L207)、[chat_manage.go:97-108](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/types/chat_manage.go#L97-L108)、[chat_manage.go:155-164](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/types/chat_manage.go#L155-L164)

本地日志记录的九阶段如下。箭头表示阶段顺序；标记“跳过”的阶段仍在执行列表中。

```text
用户: 电池掉电很快
   |
   v
LOAD_HISTORY                  -> 实际历史轮数 = 0
   |
MEMORY_RECALL                 -> workspace_disabled，未提供长期记忆
   |
QUERY_UNDERSTAND              -> rewrite = 电池掉电很快是什么原因
   |                            intent  = kb_search
   v
CHUNK_SEARCH_PARALLEL
   |-- 普通知识检索
   |     3 个 full-KB targets，共用同一个 embedding 模型
   |     查询向量计算一次，合并调用 HybridSearch
   |     vector 128 + keyword 150 -> RRF 215 -> 返回 10 条
   |-- 图检索                  -> no_entities，跳过
   `-- Web 搜索                -> 未开启
   |
CHUNK_RERANK                   -> empty_model_id，跳过模型重排
   |
CHUNK_MERGE
   |-- 取 SearchResult 分数排序作为输入
   |-- 父块恢复 / 同文档合并 / 短上下文邻块扩展
   `-- partial overlap 去重，删除 6 条
   |
FILTER_TOP_K                  -> 最终 4 条 references
   |
INTO_CHAT_MESSAGE             -> 资料 + 用户问题 -> 模板渲染快照
   |
CHAT_COMPLETION_STREAM
   |-- 转换成模型使用的 <retrieval> 上下文与 cN 引用句柄
   |-- LLM ChatStream
   `-- 解码引用 -> 事件 -> SSE + 消息持久化
```

RRF（倒数排名融合）把不同召回通道的排名合并，属于检索服务内部的结果融合；它不等于单独调用 rerank 模型。上图具体数量来自该请求日志，不能当作所有请求的固定参数。

`QUERY_UNDERSTAND` 在启用改写时调用聊天模型，输入包括原问题、可用历史等，解析结构化 `rewrite_query` 与 `intent`；失败时保留原问题继续。文本改写可选专用模型，否则用本轮聊天模型。[query_understand.go:63-155](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/query_understand.go#L63-L155)、[query_understand.go:267-295](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/query_understand.go#L267-L295)

检索的并行有多层：chunk 与 entity 可并行；chunk 内知识库与 Web 可并行；知识库按实际 embedding 模型名称和 endpoint 分组，每组只计算一次查询向量，同组完整知识库合并为一次 `HybridSearch`。显式文档/标签范围单独检索。[search_parallel.go:94-160](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/search_parallel.go#L94-L160)、[search.go:352-562](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/search.go#L352-L562)

## 3. 空 rerank_model_id 的确切含义

`PluginRerank.OnEvent` 在 `RerankModelID == ""` 时直接 `return next()`，不会调用重排模型，也不会进入该插件后续的阈值过滤、组合分数、FAQ 加分或 MMR（兼顾相关性和多样性的选择算法）。`PluginMerge.selectInputResults` 因 `RerankResult` 为空，回退到按 `Score` 降序排列的 `SearchResult`。[rerank.go:38-62](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/rerank.go#L38-L62)、[merge.go:104-117](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/merge.go#L104-L117)

后续 `FILTER_TOP_K` 仍会按分数排序、使用 `RerankTopK` 限制最终条数；参数名包含 rerank 不表示已执行模型重排。本轮 10→4 主要由 merge 的六次去重产生，不能表述为“重排筛成四条”。[filter_top_k.go:29-64](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/filter_top_k.go#L29-L64)

配置来源也需要区分：`KnowledgeQA` 从 `cfg.Conversation` 初始化参数，再由 `CustomAgent.Config` 覆盖。旧 `Session` 的 embedding/rerank/rewrite 等字段已经在结构体中注释掉；数据库仍存在旧列不代表执行读取这些列。`LastRequestState` 明确只是恢复输入栏的 UI 记录。[session_knowledge_qa.go:59-154](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/session_knowledge_qa.go#L59-L154)、[session_qa_helpers.go:170-283](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/session_qa_helpers.go#L170-L283)、[session.go:110-125](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/types/session.go#L110-L125)、[session.go:274-291](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/types/session.go#L274-L291)

与此不同，无会话 `/knowledge-search` 从租户 `RetrievalConfig` 取参数，rerank 未指定时还会尝试选择已有 rerank 模型。因此 `/knowledge-search` 的行为不能直接套到原生 Quick Answer；海客当前检索适配器使用的是 `/knowledge-bases/:id/hybrid-search`。[session_knowledge_qa.go:838-892](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/session_knowledge_qa.go#L838-L892)

## 4. 父块恢复为什么对 Q45 又缩回去了

父子块的目标是“小块负责定位，大块负责回答上下文”。实现上，`resolveParentChunks` 找到 text 子块的 `parent_text` 父块，将父块正文与子块正文合并写回检索结果；ID 仍然保留子块 ID。随后再做短上下文扩展。[merge.go:78-96](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/merge.go#L78-L96)、[merge.go:326-346](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/merge.go#L326-L346)

本轮可复原的实际追踪：

```text
Q45 text child       154 字
  -> parent_resolve  277 字父上下文
  -> 277 < 350，进入 expandShortContextWithNeighbors
  -> 根据原子块 ID 重新从数据库读取 baseChunk.Content = 154 字
  -> 从 baseChunk + 前后邻块重新拼接；没有可补内容
  -> res.Content = merged，无条件覆盖
  -> 最终             154 字

camera text child     97 字
  -> parent_resolve  632 字父上下文
  -> 632 >= 350，不进入短上下文扩展
  -> 最终             632 字
```

关键代码：短块门槛 350、上限 850；判断依据是父块恢复后的 `res.Content`，重新构建依据却是数据库原子块 `baseChunk.Content`，且无“扩展后必须更长”的保护。这解释了日志中的 `before_len=277 after_len=154`，属于两个上下文处理步骤交互造成的信息回退。[merge_expand.go:16-50](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/merge_expand.go#L16-L50)、[merge_expand.go:124-173](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/merge_expand.go#L124-L173)、[merge_expand.go:212-218](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/merge_expand.go#L212-L218)

改进方向：以已经恢复的上下文为扩展基底，或在父块恢复成功后跳过会覆盖父块的邻块扩展；应以“父上下文不丢失”的回归用例验证。此研究未改实现。

## 5. 两处会影响售后案例质量的边界

### 5.1 去重跨 SKU 和处理结果

初次去重按块 ID 与正文签名；最终 `removePartialOverlaps` 跨整个结果集比较，没有知识库、文档、SKU 或工单结果条件。正文包含，或 token 重叠系数达到 0.85，即删除低分项，等分时长内容优先。[search.go:183-209](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/search.go#L183-L209)、[search.go:214-314](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/search.go#L214-L314)

本轮日志的六次删除与本地工单元数据关联如下（主研究数据库核对）：

| 保留工单 | 删除工单 | 差异 |
|---|---|---|
| T0223 / ANKER-A1289 / unsolved | T0203、T0228 / ANKER-A1289 / solved | 同型号但处理结果不同 |
| T0223 / ANKER-A1289 / unsolved | T0208 / ANKER-A1611 / unsolved | 不同型号 |
| T0223 / ANKER-A1289 / unsolved | T0213 / ANKER-A1695 / solved | 不同型号、不同结果 |
| T0223 / ANKER-A1289 / unsolved | T0218 / ANKER-A1611 / escalated | 不同型号、不同结果 |
| T0343 / EUFY-T8210 / solved | T0349 / EUFY-T8213 / unsolved | 不同型号、不同结果 |

观察事实是跨型号、跨结果案例被折叠；推论是这可能降低诊断证据多样性。“文本相似”并不保证“售后经验等价”。若回答要区分成功/失败处理，去重应保留这些业务维度，或至少记录合并来源与结果差异。

### 5.2 模板快照有 metadata，真正发送给模型的上下文却没有

问题发生在 Quick Answer 的上下文转换调用方，不能归因为 `Registry.EncodeMessages` 把 metadata 编码丢了。

最小源码链：

1. `IntoChatMessage` 先把文档 title、description、`KnowledgeCustomMetadata` 输出成 `<documents>`，与 `<context>` 一起组成 `RenderedContexts`；数据库 `rendered_content` 保存这层快照。[into_chat_message.go:124-193](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/into_chat_message.go#L124-L193)、[into_chat_message.go:267-290](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/into_chat_message.go#L267-L290)
2. 流式调用前 `prepareMessagesWithModelContext` 重建 `knowledgeRows`，只传 `chunk_id / knowledge_id / knowledge_base_id / knowledge_title / chunk_index / chunk_type / content`，没有传 `knowledge_metadata` 或 description。[references.go:47-57](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/references.go#L47-L57)
3. 它把原 `RenderedContexts` 整体替换成新生成的 `<retrieval>`，连旧 `<documents><metadata>` 一起替换掉。[references.go:59-95](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/references.go#L59-L95)
4. 下层 renderer 本身支持从 `knowledge_metadata` 读取和输出 `<metadata>`；调用方未传，因此本轮最终上下文没有这批 category/result/sku 字段。[model_output.go:200-205](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/modelcontext/model_output.go#L200-L205)、[model_output.go:304-307](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/modelcontext/model_output.go#L304-L307)

```text
检索结果 KnowledgeCustomMetadata
          |
          v
IntoChatMessage: <documents><metadata>category, result, sku ...</metadata>
          |                         |
          |                         `-> rendered_content 持久化快照有字段
          v
prepareMessagesWithModelContext
          |-- 构造 knowledgeRows 时遗漏 knowledge_metadata
          `-- 整体替换旧 RenderedContexts
          v
真正 LLM input: <retrieval><document title="T0223"><chunk>正文</chunk>...
               无 category/result/sku 元数据字段
```

因此不能仅检查 `messages.rendered_content` 就认定模型看到全部业务元数据；需要对照最终 `Stream user_message` 或模型请求追踪。本轮不能写成“模型忽略了 power_bank 标签”，更准确的是“转换层没有把该标签交给最终回答模型”。若正文仍含某个型号，模型当然仍可能从正文识别；这里确认丢失的是独立元数据字段。

改进方向：Quick Answer 建立 `knowledgeRows` 时补传 `knowledge_metadata`，并验证最终模型上下文保留 category、sku、result；描述字段如需保留，应建立明确的渲染契约。

## 6. Prompt、引用与输出架构

两个 event 概念职责不同：`chatpipeline.EventManager` 按有序 event 列表调用插件，是流程编排；每请求 `EventBus` 向输出订阅者广播进度、references、answer、complete，是运行结果传递。`ChatManage` 由请求配置、中间状态与运行上下文组成。[chat_pipeline.go:24-77](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/chat_pipeline.go#L24-L77)、[chat_manage.go:111-152](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/types/chat_manage.go#L111-L152)

Prompt 基本顺序是 system prompt + 历史问答 + 本轮 user prompt。检索使用改写问题，本轮 RAG 生成模板里的 query 仍用经过校验的原问题。模型上下文使用临时句柄 cN/dN/bN；模型输出 `<ref id="cN"/>`，服务端映射回真实 chunk/KB 引用。未知句柄被丢弃。[common.go:89-127](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/common.go#L89-L127)、[into_chat_message.go:166-177](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/into_chat_message.go#L166-L177)、[citations.go:14-25](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/modelcontext/citations.go#L14-L25)、[citations.go:169-202](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/modelcontext/citations.go#L169-L202)

```text
MergeResult ----------> references event --------> assistant.KnowledgeReferences
     |                       |                                |
     v                       v                                v
Prompt -> LLM stream -> 请求 EventBus -> StreamManager       message DB
            |                    |             |
            `-> 引用解码         |             `-> HTTP 每100ms按offset读取 -> SSE
                                 `-> Done -> 保存完整answer -> complete
```

references 在开始回答前发出，供检索结果面板显示；与正文内实际使用的 citation 是不同层。四条 references 表示给模型的四条合并资料，不等于四条都支持最终答案。引用协议只保证引用 ID 来自已登记资料，不做论断真实性或产品类别一致性验证。[session_knowledge_qa.go:724-733](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/session_knowledge_qa.go#L724-L733)、[session_knowledge_qa.go:1196-1216](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/session_knowledge_qa.go#L1196-L1216)、[agent_stream_handler.go:388-429](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/handler/session/agent_stream_handler.go#L388-L429)

流式插件调用 `ChatStream`，将返回文本解码成 answer 事件；handler 累积正文，Done 时更新消息并发 complete。HTTP 消费端独立轮询 StreamManager，支持重新接收流，而不是直接把模型 channel 绑定到浏览器连接。[chat_completion_stream.go:53-86](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/chat_completion_stream.go#L53-L86)、[chat_completion_stream.go:215-242](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/chat_completion_stream.go#L215-L242)、[qa.go:972-998](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/handler/session/qa.go#L972-L998)、[stream.go:326-361](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/handler/session/stream.go#L326-L361)

Agent 模式把流程控制交给受迭代预算约束的循环：模型选择工具 → 执行 → 把结果追加到 messages → 再次调用模型，直到自然回答或停止条件。它可以多次检索和补读，不适用上面的固定九阶段追踪；其 `knowledge_search` 可用时还要求 agent 显式配置 rerank 模型，空 ID 行为与 Quick Answer 不同。[engine.go:428-509](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/agent/engine.go#L428-L509)、[engine.go:712-758](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/agent/engine.go#L712-L758)、[session_agent_qa.go:112-137](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/session_agent_qa.go#L112-L137)
