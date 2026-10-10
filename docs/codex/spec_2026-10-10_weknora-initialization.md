# WeKnora 知识库初始化提示排查

日期：2026-10-10。

用户反馈：本机 `http://localhost:8081/platform/knowledge-bases` 显示「部分知识库尚未初始化，需要先在设置中配置模型信息才能添加知识文档」。

范围：读取本机 WeKnora 服务状态、项目空间的知识库与模型配置，核对运行版本的初始化判定。定位具体未初始化知识库及缺失字段，记录修复方式。复用 `.env` 中已有凭据，凭据不写入文档或输出。

验收：用只读检查复现提示对应的初始化状态，并给出具体知识库、缺失字段和原因。若需要修改配置，先明确修改对象；不删除知识库、重建索引、重导入资料或修改其他会话的文件。

## 排查结果

- 项目空间 `tenant_id=10001` 只有 `haike_kb_qa`，ID 为 `bed1f9a4-770b-4a91-a9b2-ba46d125a452`。
- `embedding_model_id=cb1b0cb6-92f6-4b73-a4b0-942e2cb9bec4`，对应 active 的 `text-embedding-v4`；`summary_model_id` 为空。
- 当前网页资源 `KnowledgeBaseList-BpPm7osN.js` 的初始化判定先检查 `summary_model_id`，为空即未初始化；全局提示由「存在任一未初始化知识库」触发。用当前网页真实判定函数处理只读 API 返回值，检查退出码为 1，输出 `missing_summary=true, missing_embedding=false`。
- 初始化配置 API 返回 `hasFiles=true`，有 embedding 配置，没有 llm 配置；872 条知识全部 `parse_status=completed`。业务聚合健康为 ok，WeKnora 健康为 ok。
- `orchestrator/app/knowledge/ingest.py:114` 的 `ensure_qa_kb` 创建时只传 embedding 模型 ID，没有传 summary 模型 ID；已有知识库直接复用，因此后续 ingest 也不会补齐。运行状态与这一创建逻辑一致。
- 可复用已有 active/default 的 `builtin-llm-default`（`deepseek-flash`），为该知识库补齐摘要/对话模型绑定。无需重新登记模型或重导入已有知识。
- [WeKnora v0.8.0 初始化处理代码](https://github.com/Tencent/WeKnora/blob/v0.8.0/internal/handler/initialization.go) 将 `llmModelId` 写入 `SummaryModelID`，与网页所需字段一致。

本次只排查并记录原因，未修改服务、知识库配置或入库实现。临时检查脚本用后删除；未调用真实模型。

## 配置与重建评估

用户追加授权：配置已有摘要/对话模型，并判断是否需要重新创建知识库或重建索引。

执行范围：为 `haike_kb_qa` 绑定 `builtin-llm-default`（`deepseek-flash`）；保留现有 embedding、分块及其他配置。回读确认模型绑定，运行网页当前初始化判定，并检查 872 条知识的解析状态、实际分块/向量覆盖和检索结果，再判断重建是否必要。不会仅为消除提示而重建知识库。

### 执行结果

- 已通过 `PUT /api/v1/initialization/config/{kb_id}` 保存 `llmModelId=builtin-llm-default`。回读 `summary_model_id` 与 llm 模型名称均正确。
- 使用当前网页资源的真实初始化判定函数：保存前 `initialized=false`，保存后及最终复核均为 `initialized=true`，检查退出码从 1 变为 0。
- 前后核对知识库 ID、embedding ID、分块、索引策略、图像/语音模型、存储实例及知识数量，均保持一致。API 将原先为空的知识图谱和问题生成配置规范化为 disabled，功能仍关闭。
- 数据库只读检查：872 条知识全部 completed/enabled；909 个文本块均 enabled/ready；909 条 1024 维向量均 enabled，覆盖全部 909 个块和 872 条知识。无知识缺块，无文本块缺向量。
- 与本地官方 Q&A 源核对：872 条可见条目完全对应，无缺失或多余条目，全部 `doc_version=0cc02e6531d6`。分布为扫地机 593、吸奶器 127、摄像头 152。
- 使用业务知识适配器按品类和 SKU 进行三次真实 hybrid-search：`T2352/rv-0001`、`T8D04/bp-0001`、`T8170/bp-0128` 均返回 ok，预期条目均排第一，耗时分别为 315/274/363 ms。
- 历史摘要状态原为 872 条 failed。为验证模型实际可用，仅对 `rv-0001` 调用 `POST /api/v1/knowledge/{id}/regenerate-summary`；摘要变为 completed，生成 296 字符，解析状态、标题和元数据保持一致。最终数据库复核保留 909 个文本块，新增 1 个 ready 的摘要块及对应向量，向量总数为 910，无缺失向量。没有对全部资料重新解析。
- 业务聚合健康为 ok；WeKnora、数据库、Redis 正常。

结论：无需重新创建知识库、重建索引或重新导入资料。剩余 871 条历史摘要失败记录不会因绑定模型自动补生成；如需补齐摘要，应单独重生成摘要，现有正文/向量检索不依赖这些摘要。本次只修改知识库模型绑定并补生成一条验收摘要，未修改入库实现、重启服务或提交代码。
