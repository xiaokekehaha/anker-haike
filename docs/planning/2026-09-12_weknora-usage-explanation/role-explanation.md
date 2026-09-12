# WeKnora 在本项目中的作用

核查日期：2026-09-12。基于当前工作区代码与 WeKnora v0.8.0 官方资料；本轮没有执行数据库查询、导入或其他服务写入，也没有重新验证线上运行状态。

## 平台主要做什么

WeKnora 是围绕私有知识构建的知识管理与 AI 问答平台。核心链路是：导入资料 → 解析、分块、向量化和建立索引 → 根据问题检索相关片段 → 交给模型生成有来源的回答。这类“先检索资料，再生成回答”的方式叫 RAG。

它另外提供 Agent、MCP 工具、Wiki、知识图谱、数据源同步、聊天界面和权限管理等能力。这些是平台能力，并非本项目全部采用的功能。

来源：[官方 v0.8.0 README](https://github.com/Tencent/WeKnora/blob/v0.8.0/README.md)。

## 本项目为什么采用

项目是扫地机售后助手，需要结合说明书、排障手册和历史工单回答产品问题。WeKnora 承担知识入库与检索，可复用分块、索引、搜索 API 和管理界面，减少自研工作量。关键词检索适合型号、部件等词语，向量检索用于匹配表述不同但语义相关的问题；实际效果仍取决于数据和模型。

业务分工：WeKnora 管理和检索资料，LangGraph 控制产品确认与售后会话流程，ModelRouter 调用模型组织回复，PostgreSQL 保存结构化业务数据与会话状态。

项目自己的流程要控制产品确认、用户反馈、安全升级和界面事件，因此保留自有编排层。采用 WeKnora 的依据是复用知识服务，并没有证据说明它是唯一可行或经对照评测最优的选项。

来源：[选型记录](../2026-09-12_smart-service-tech-design/tech-stack-survey.md)、[会话图](../../../orchestrator/app/sessions/graph.py)。早期调研中 MCP、ask、图谱和重排的设想应与下述当前实现区分。

## 当前实际使用

| 能力 | 当前实现与边界 |
| --- | --- |
| 知识库及条目管理 | 导入代码创建说明书、FAQ、历史工单三个库；本地 manifest 记录了三个库的 ID |
| 文本入库 | Markdown 说明书和排障手册通过在线文本接口导入；CSV 工单按行转为独立知识条目 |
| FAQ 批量导入 | 原生 FAQ 接口以 replace 模式导入；当前对话 retrieve 节点尚未检索 FAQ 库 |
| 父子分块与索引 | 配置父块 800、子块 200 字符，Embedding 约定 1024 维；多模态和图谱关闭 |
| 混合检索 | 通过 HTTP 调用 `/knowledge-bases/{id}/hybrid-search`，查询说明书与工单，每库最多保留 5 条 |
| 元数据与来源 | 保存 scope、SKU、品类和文档版本，返回片段及 chunk ID，供项目构建证据事件 |
| 服务接入和维护 | API Key 鉴权、模型登记、幂等导入及导出/回滚辅助代码、健康检查和可选管理 UI |

来源：[导入代码](../../../orchestrator/app/knowledge/ingest.py)、[HTTP 客户端](../../../orchestrator/app/knowledge/weknora_client.py)、[检索适配器](../../../orchestrator/app/knowledge/adapter.py)、[会话 retrieve/reply](../../../orchestrator/app/sessions/graph.py)、[官方混合检索 API](https://github.com/Tencent/WeKnora/blob/v0.8.0/docs/api/knowledge-base.md)。

产品范围控制由项目的适配器实现：先按 SKU/品类筛选允许的 knowledge_ids，再请求 WeKnora，并对结果做二次过滤；空范围直接返回无匹配。失败工单的反证标记、证据展示与检索异常处理也属于项目自己的逻辑。

当前主流程未采用 WeKnora 内置聊天/问答生成、ReAct Agent、MCP 接入、Wiki、GraphRAG 或多模态文档解析。项目使用自己的模型调用生成回复。Rerank 虽有登记配置，但当前直接 hybrid-search 调用链没有执行独立 Rerank 模型；该版本上游 HybridSearch 返回召回结果，聊天管线可在后续另行重排。

来源：[当前 retrieve → reply 图连接](../../../orchestrator/app/sessions/graph.py)、[上游 HybridSearch](https://github.com/Tencent/WeKnora/blob/v0.8.0/internal/application/service/knowledgebase_search.go)、[模型登记配置](../../../deploy/weknora/builtin_models.yaml)。

## 一个使用例子

用户描述“这台扫地机吸力变小”：项目先确认产品型号、整理症状，再在允许的说明书和历史工单范围内检索。WeKnora 返回相关原文片段及来源；项目将证据交给模型生成回复，并由自己的会话流程控制后续交互。这个例子说明组件分工，不代表本轮执行了该问题的检索测试。

## 当前状态的限制

本地 `manifest.json` 记录 203 条文档/工单跳过、50 条 FAQ，以及 `stub-embedding-1024`。桩实现使用确定性词元哈希向量，其文件明确用途是验证入库/检索链路，不用于演示和评测。因此已实现接入不能被表述为真实语义检索效果已经验证；运行服务此刻使用什么模型也不能仅由 manifest 判断。

来源：[导入记录](../../../data/knowledge/manifest.json)、[Embedding 桩](../../../deploy/dev/embedding_stub.py)。
