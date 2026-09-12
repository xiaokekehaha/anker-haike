# WeKnora v0.8.0 官方核查

核查日期：2026-09-12。版本固定为 `v0.8.0`，commit `1edcd54b43606d9079bb36650efe3f68707a79ea`，与本项目运行镜像 revision 一致。通过 web 读取固定版本 README，并在 `/tmp/weknora-official-v080-research` 只读核对该 tag 源码。本次未连接数据库、未创建空间、未调用任何写入 API。

## 1. 有完整 Web UI，tenant 在界面叫「工作空间」

- 官方 UI 支持知识库管理、文件/网页/在线文本入库、文档解析状态、切片查看和编辑、切片修订历史，以及带引用的知识问答。
- 默认部署前端地址是 `http://localhost`，后端是 `http://localhost:8080`；本项目端口和 UI 是否启动由本地 compose 决定，不能直接照搬。
- 常规使用顺序：注册/登录 → 进入或创建工作空间 → 建文档库/FAQ 库 → 选择模型和切片参数 → 上传并等待 completed → 检索或问答。
- 自助注册默认会创建个人工作空间，用户成为 Owner；部署若为 invite-only 或 tenantless，则改为邀请/空间引导流程。
- 服务端集成密钥从「空间设置 → API Key」创建，按需选择 retrieve / ingest / manage_kbs 等能力并可限制知识库范围。新建 tenant **默认不自动返回 API Key**，可通过 `POST /api/v1/tenants/:id/api-keys` 创建。tenant 是数据及权限隔离边界，不等于要再部署一套容器。

来源：[固定版快速上手](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/website-docs/01-getting-started/03-quickstart.md)、[空间与认证](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/website-docs/03-features/01-tenant-auth.md)、[空间 API](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/docs/api/tenant.md)、[README 界面展示](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/README.md#-interface-showcase)。

## 2. 如何导入

| 内容 | 官方方式 | 本项目解释时的边界 |
|---|---|---|
| PDF/Word 等文档 | 文档库上传区上传；API `POST /knowledge-bases/:id/knowledge/file` | 解析成正文后自动分块和向量化；扫描 PDF 还依赖 OCR/图像解析配置 |
| 现成 Markdown/普通文本 | 在线编辑；API `POST /knowledge-bases/:id/knowledge/manual`，title/content/status | 草稿不触发解析，发布后才进入入库流程；适合业务侧预整理的语义文档 |
| FAQ | 单独的 `faq` 类型知识库；标准问、相似问、答案等结构化条目，支持单条及批量 API | 不应把 FAQ 说成所有文档的统一切片模式；可按问题或问题+答案建索引 |
| CSV 普通文档上传 | Go SimpleFormatReader 读取，首行当表头，将整份 CSV 转成 Markdown 表格再送通用分块 | **不是每行自动生成独立 knowledge_id + 任意业务 metadata**；有逐记录追溯/精确过滤需求时应由业务入库脚本明确映射 |

FAQ 的单条/批量能力已核实；本次未进一步逐控件验证 FAQ CSV/Excel 上传模板界面，不将其作为已完成集成承诺。

来源：[知识 API](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/docs/api/knowledge.md)、[FAQ API](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/docs/api/faq.md)、[CSV 转换源码](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/infrastructure/docparser/builtin_converter.go#L180)、[文档解析说明](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/website-docs/03-features/03-document-parsing.md)。

## 3. 切片：800/200 是本项目选值，单位是字符

父子模式字段：`chunking_config.enable_parent_child=true`、`parent_chunk_size=800`、`child_chunk_size=200`。实际长度和位置使用 Unicode rune，可解释为字符数；**不是 800/200 token，也不是字节**。标点、空格、英文字符都计入字符长度。

实际流程：正文先按父块配置切一次，再在每个父块内按子块配置切一次。父块写入 chunks 表用于上下文；只有子块/普通平铺块进入检索索引并调用 embedding，父块不单独向量化。很短的父块若只产生相同的一个子块，会省去冗余父记录。

- 上游默认父块 4096 字符、子块 384 字符，因此 800/200 需显式配置。
- 父块 overlap 来自 `chunk_overlap`；入库归一化函数对 `<=0` 回填 80，因此不要保证设置 0 就完全不重叠。
- 子块 overlap 由实现固定取 `child_size / 5`，200 对应 40 字符，并非独立的子 overlap 字段。
- 有 auto / heading / heuristic / legacy 策略：可优先遵循标题、段落、页/章节等边界，超长内容再递归分割；因此“800 字符父块”是尺寸配置，不代表每块精确等长。Markdown 链接、代码、公式和表格行等存在结构保护。
- `token_limit` 是另一个可选的近似 token 限制；父子模式下只作用于子块，不能混同字符大小。
- UI 切片栏支持样本文本预览，显示分块字符数、估算 token、边界和策略。调整配置不会自动重切既有文档，需要重解析/重建索引。

检索以小子块匹配，默认结果处理会补充父块等上下文；`skip_enrichment=true` 可关闭底层补充。问答链的 Merge 阶段还会把命中子块扩为父块上下文。故“子块负责找得准、父块负责给足背景”可作为用户解释，但不能承诺每个底层 API 只返回父块。

来源：[分块说明](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/docs/CHUNKING.md)、[字符计量源码](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/infrastructure/chunker/splitter.go#L14)、[父子参数及 overlap 实现](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/infrastructure/chunker/strategy.go#L125)、[父块落库/子块向量化](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledge_process.go#L388)、[检索结果补充](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledgebase_search_results.go#L15)、[问答 Merge](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/merge.go#L214)。

## 4. Embedding、LLM、Rerank 是不同角色

Embedding 将子块文字转换成固定维度向量，查询也转换成向量以便相似度检索；LLM 用检索到的上下文生成答案；Rerank 对已召回候选重新打相关性分数。普通文本解析/切片本身不等于调用聊天 LLM，完整 UI 问答闭环则需对话模型。上游支持远程 OpenAI 兼容 embedding，模型通过知识库的 embedding_model_id 绑定，维度通过模型参数指定。百炼模型当前维度及生命周期由主任务另行核验。

**只传环境变量不等于模型已注册。** `EMBEDDING_MODEL_NAME` / `EMBEDDING_BASE_URL` / `EMBEDDING_API_KEY` / `EMBEDDING_PROVIDER` 和 `RERANK_*` 在上游只是 YAML 样板变量名，没有对应直接读取并创建模型的代码。必须通过 UI/API 创建模型，或挂载 `config/builtin_models.yaml`（可用 `BUILTIN_MODELS_CONFIG` 指定），由 YAML 引用变量、启动时同步 models。内置模型默认对所有空间可见；如需模型配置也仅属于本项目空间，可走空间内 UI/API 模型配置。

来源：[内置模型机制](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/docs/BUILTIN_MODELS.md)、[YAML loader](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/types/builtin_models_config.go)、[OpenAI embedding 实现](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/models/embedding/openai.go)、[模型 API](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/docs/api/model.md)。

## 5. 百炼 Rerank 接口兼容边界

固定版本有两条关键实现：

- `provider=aliyun`：请求直接发往配置的完整 URL，默认 `/api/v1/services/rerank/text-rerank/text-rerank`；请求使用 `{model,input:{query,documents},parameters:...}`，响应读取 `output.results`。
- `provider=generic`：请求使用顶层 `{model,query,documents}`，响应读取顶层 `results`，但 URL 固定拼接 **`/rerank` 单数**。因此若当前百炼 qwen3-rerank 使用 `/compatible-api/v1/reranks` 复数，不能只换模型名或给完整 URL 就宣称直连成功，需要路径适配/代理/修改实现或经核实的新版。

主任务已查到旧 gte-rerank 下线信息，生命周期由主任务引用百炼官方源。WeKnora aliyun 实现与仍使用旧嵌套协议的模型在协议结构上相容，但本次未实际发送计费模型请求，不能称“已验通”。

问答 pipeline 的 rerank API 失败会回退已有召回候选继续执行；这只验证了该特定路径，不代表所有检索入口或 embedding 故障都自动降级。Embedding 入库失败会记录 embedding 阶段失败，不能当成成功入库。

来源：[provider 路由](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/models/rerank/reranker.go)、[generic 协议及 URL](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/models/rerank/remote_api.go)、[aliyun 协议](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/models/rerank/aliyun_reranker.go)、[rerank 失败回退](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/chat_pipeline/rerank.go#L120)。

## 6. Metadata / 文档范围 / 业务快照的简短边界

- 原生 `knowledge-search` 支持 `knowledge_ids` 限制到指定文档；普通知识修改支持 `custom_metadata`。这些是原生能力。
- 本次核对的公开检索请求字段没有任意 metadata 条件表达式；不能把存有 metadata 等同于已完成 source_type / entity_id / snapshot_id 的条件检索集成。
- 官方切片版本历史是内容编辑/回滚历史，不等于本项目的业务数据 snapshot 版本管理。业务快照映射和过滤是否实现须查看本地入库/查询适配代码，本次未做额外上游穷尽调查。

来源：[知识搜索 API](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/docs/api/knowledge-search.md)、[知识更新 API](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/docs/api/knowledge.md)、[知识库与切片历史](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/website-docs/03-features/02-knowledge-base.md)。
