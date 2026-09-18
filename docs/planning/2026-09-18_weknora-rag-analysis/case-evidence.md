# 本地会话只读证据

观察时间：2026-09-18。证据来自 Docker 镜像标签、容器日志和 PostgreSQL `BEGIN READ ONLY` 查询；未重新运行问答或检索。省略账户信息、密钥、完整提示词与模型推理文本。

## 版本和定位

- 会话：`eb046d88-6364-4459-b47a-c28d7d00398b`，标题「电池掉电很快问题」。
- 用户消息：`f00ccd3d-ac02-4186-8b02-666bc3b1e9b2`；助手消息：`58bfe512-9ce3-4194-8ab2-2441b332be83`。
- request_id：`1mrR9LDxgQ0Z`；时间：2026-09-18 08:24:55—08:25:01（Asia/Shanghai）。
- 镜像：`wechatopenai/weknora-app:v0.8.0`。
- image ID：`sha256:14953fcb990c59b2546f00e94673d2a4c88689e3319bfcf2b06f82feaccec9b4`。
- OCI revision：`1edcd54b43606d9079bb36650efe3f68707a79ea`；与 GitHub v0.8.0 tag 相同。

## 实际请求和配置

```json
{
  "query": "电池掉电很快",
  "agent_enabled": false,
  "agent_id": "builtin-quick-answer",
  "web_search_enabled": false,
  "summary_model_id": "builtin-llm-default",
  "knowledge_base_ids": null,
  "knowledge_ids": null
}
```

- 内置快速问答配置：`kb_selection_mode=all`，`retrieve_kb_only_when_mentioned=false`。
- 解析出 3 个完整知识库检索目标，无文件、品类或 SKU 限制。
- 运行日志有效参数：`embedding_top_k=10`、`vector_threshold=0.5`、`keyword_threshold=0.3`、`rerank_top_k=10`、`rerank_threshold=0.3`。
- `rerank_model_id=""`；已登记 `gte-rerank-v2` 不代表该请求已绑定它。
- tenant 10001 的 `retrieval_config` 为 NULL，因此 RRF 使用源码默认值 k=60、向量权重0.7、关键词权重0.3。
- `sessions` 中保留的旧列值（例如 rerank_threshold=0.65）不是本次执行配置的真源，应以 Agent 配置与日志为准。

## 时间线

| 本地时间 | 运行事实 |
|---|---|
| 08:24:55.087 | 请求为 Quick Answer，web_search=false |
| 08:24:55.155 | 3 full KB targets，0 partial/tag KB |
| 08:24:55.158 | 9阶段：load_history / memory_recall / query_understand / chunk_search_parallel / chunk_rerank / chunk_merge / filter_top_k / into_chat_message / chat_completion_stream |
| 08:24:55.167 | history_rounds=0 |
| 08:24:55.170 | memory recall skipped：workspace_disabled |
| 08:24:56.329 | 改写「电池掉电很快是什么原因」，intent=kb_search |
| 08:24:56.344 | 3个目标只有1组embedding模型 |
| 08:24:56.937 | text-embedding-v4，vector_len=1024，combined_kb_count=3 |
| 08:24:56.941 | vector/keywords两路topK均150，向量阈值0.5 |
| 08:24:57.012 | 向量返回128条 |
| 08:24:57.189 | 关键词返回150条 |
| 08:24:57.191 | RRF合并215条 |
| 08:24:57.202 | 取回10条搜索结果 |
| 08:24:57.206 | Rerank skip：empty_model_id |
| 08:24:57.207 | Q45子块154字符 -> 父块277字符 |
| 08:24:57.208 | 摄像头子块97字符 -> 父块632字符 |
| 08:24:57.211 | 短块扩展又把Q45内容277字符覆盖为154字符 |
| 08:24:57.302—57.481 | 内容重叠去重丢6条，保留4条 |
| 08:24:57.481 | FilterTopK：merge_cnt=4 / top_k=10 / rerank_cnt=0 |
| 08:24:57.483 | IntoChatMessage：4 document / 0 FAQ，保存rendered_content |
| 08:24:57.505 | 调用deepseek-flash流式生成 |
| 08:24:59.209 | 首回答片段，日志ttfb_ms=4241 |
| 08:25:01.090 | 生成结束；主回答prompt_tokens=1637 / completion_tokens=742 |
| 08:25:01.095 | 助手消息持久化完成 |
| 08:25:04.176 | HTTP SSE连接结束，POST /api/v1/knowledge-chat/:session_id，access log总延迟9.2407秒 |

9阶段同步启动耗时日志为2441ms，但流式生成随后继续，不能把2441ms解释为完整回答耗时。助手消息约6秒完成后，SSE仍等待标题事件，总连接时间约9.24秒。主回答token不包含改写和并行标题生成。

## 最终4条证据

| 文档 | chunk ID | 融合分 | 数据库元数据 | 最终上下文字符数 |
|---|---|---:|---|---:|
| T0223 | a278d5cd-1b12-4a27-9458-c93c473b241c | 0.01609079445 | power_bank / ANKER-A1289 / unsolved | 87 |
| Q45电池官方摘要 | 870c9ca5-0af1-4f53-88bf-82703c2efcc4 | 0.01492537313 | headphones / SOUNDCORE-A3040 | 154 |
| 家庭安防摄像头通用演示手册 | 4b4e4f0e-7986-4d68-91b4-b4c55819bccf | 0.01338612368 | security_cam / category_generic | 632 |
| T0343 | 8f58275f-d6f4-4ad9-a649-ba48f65442ed | 0.01292569659 | security_cam / EUFY-T8210 / solved | 75 |

这些分数是加权RRF排名分，不是回答正确率或置信度。最终回答把T0223写入「耳机类产品」小节；数据库category实际为power_bank。

## 被去重的记录

| 保留 | 丢弃 | 丢弃记录的SKU/结果 |
|---|---|---|
| T0223：ANKER-A1289 / unsolved | T0203 | ANKER-A1289 / solved |
| T0223 | T0228 | ANKER-A1289 / solved |
| T0223 | T0208 | ANKER-A1611 / unsolved |
| T0223 | T0213 | ANKER-A1695 / solved |
| T0223 | T0218 | ANKER-A1611 / escalated |
| T0343：EUFY-T8210 / solved | T0349 | EUFY-T8213 / unsolved |

日志动作均为 `Merge action=partial_overlap_drop`。可确认本轮去重跨型号且抹平结果差异；不据此宣称被删记录一定是更正确答案。

## 最终模型请求抽查

解析上述request_id的 `[LLM Stream Request]` JSON，只保留结构性检查：

```json
{
  "model": "deepseek-flash",
  "message_roles": ["system", "user"],
  "user_content_chars": 1743,
  "has_metadata_tag": false,
  "has_power_bank_category": false,
  "has_scope_field": false,
  "has_unsolved_in_body": true,
  "has_sku_in_body": true
}
```

最终模型看到的是短引用句柄 `<document id="d1" kb="b1" title="T0223"><chunk id="c1" ...>` 与正文。`unsolved`、`ANKER-A1289` 因为也写在工单正文中仍在；结构化 `category`、`scope` 等没有保留。中间 `rendered_content` 和最终模型输入并非同一份文本。

## 知识库与存储

| 知识库 | 类型 | 知识记录 | 子/普通块 | 父块 |
|---|---|---:|---:|---:|
| haike_kb_manual | document | 35 | 104 text | 35 parent_text |
| haike_kb_tickets | document | 380 | 380 text | 0 |
| haike_kb_faq | faq | 1 FAQ容器 | 116 FAQ | 0 |

全部有效知识记录的parse_status均为completed。手册和工单来源类型为manual。配置父块800、子块200、overlap80，实际边界受分隔符影响，并非定长。

- PostgreSQL扩展：vector 0.8.1、pg_search 0.22.2。
- `embeddings_search_idx`：BM25，content tokenizer=`chinese_lindera`。
- `embeddings_embedding_idx_1024`：HNSW，`halfvec(1024)` cosine，m=16 / ef_construction=64，部分索引条件dimension=1024。
- 本次没有跑EXPLAIN，不能断言每条向量SQL最终采用HNSW计划。
- 本地 `config/retrieval.yaml` 与运行orchestrator容器 `/srv/config/retrieval.yaml` SHA256一致：`9390dda136f9aa0825cf40b655c2df8b4178b1ad53ec28188ee3c38a76940ced`。
