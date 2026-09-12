# 主流技术调研与选型

整理日期：2026-09-12。目标是找出可以直接复用、减少自研工作量的开源组件，并说明为何选或不选。

## 1. 候选清单

| 层次 | 候选 | 定位 | 对本项目的价值 | 结论 |
| --- | --- | --- | --- | --- |
| 知识库 / RAG | **WeKnora**（腾讯，Go） | 文档解析 + 三路混合检索 + ReAct Agent + MCP 服务 | 直接承担说明书、FAQ、历史工单的入库与检索；多模态解析可处理图片类工单；MCP 暴露检索工具给我们的编排层 | **采用**，作为知识层 |
| 知识库 / RAG | RAGFlow | 深度文档理解，表格与版面抽取强 | 说明书 PDF 解析质量高 | 备选，与 WeKnora 定位重叠，不并用 |
| 知识库 / RAG | Dify 内置 RAG | 平台自带 | 检索策略可控性弱 | 不采用 |
| Agent 编排 | **LangGraph**（Python） | 有状态图、checkpoint、中断与人机交接 | 五阶段状态机、排障反馈回路、升级中断天然对应 | **采用**，作为编排层 |
| Agent 编排 | Dify | 低代码平台 | 原型快，业务同学可调 Prompt | 不采用，反馈回路与规则判定难表达，前端卡片难定制 |
| Agent 编排 | WeKnora 内置 ReAct Agent | 自主检索推理 | 通用问答可用 | 不采用作主编排，流程不可控、进度不可展示 |
| 模型 | Claude / Gemini / OpenAI 与国内 OpenAI 兼容 API（百炼 Qwen、DeepSeek、智谱、火山、Moonshot） | 文本 + 视觉 | 按环节路由不同模型，主备降级链 | 全部远程；自建 ModelRouter 适配层，底层用 LangChain init_chat_model，详见 model-selection.md |
| 模型网关 | LiteLLM Proxy | 多厂商统一 OpenAI 接口、fallback、配额 | 多服务共用时省事 | 备选，当前不引入，ModelRouter 接口与之兼容 |
| 前端 | **Vite + React 19 + TypeScript** | 静态单页，生态最全 | 业务卡片自写，后续可接 assistant-ui | **采用**，详见 05_frontend-design.md |
| 前端 | Vite + Preact | 运行时约 3 KB | compat 兼容性需验证 | 备选 |
| 前端 | assistant-ui | 聊天组件与 runtime | LangGraph runtime 要求 LangGraph Server API，对自定义 SSE 需写 runtime | 演进路径 |
| 前端 | CopilotKit | 页面级协作、共享状态，有 Python LangGraph 接入 | 需接受 AG-UI 协议 | 后续评估 |
| 前端 | Next.js | SSR 全栈 | 本项目不需要 SSR | 不采用 |
| 可观测 | **Langfuse** | LLM 调用追踪 | 记录每轮延迟、token、工具调用；WeKnora 已原生集成 | **采用** |
| 评测 | RAGAS | 检索与生成质量评估 | 验证知识库命中率，支撑「已验证效果」 | 采用，离线使用 |
| 存储 | PostgreSQL + pgvector、Redis | WeKnora 默认依赖 | 会话状态与 LangGraph checkpoint 复用同一 PostgreSQL | 采用 |

## 2. WeKnora 重点说明

- 检索：BM25 + 向量 + 知识图谱三路混合，RRF 融合后 Rerank，支持父子分块。适合「用户描述含糊」时靠关键词兜住、靠向量泛化、靠图谱关联同型号故障。
- 解析：PDF、Word、图片（OCR）、Excel 等 11 类格式，支持按批次覆盖解析器与 VLM 描述配置。历史工单可用 CSV/XLSX 导入，说明书用 PDF。
- 对外接口：提供 HTTP API、Python MCP Server（stdio / SSE / HTTP）和 CLI。我们的 LangGraph 节点通过 MCP 或 HTTP 调用「hybrid search」「ask」工具。
- 部署：Docker Compose 一键，依赖 PostgreSQL(pgvector)、Redis；本项目 Embedding / Rerank 配置为远程 API（D17），不启用 Ollama。
- 需要注意：项目迭代快（2026 年已到 v0.4.x），API 以部署版本文档为准；知识库按用户归属，需为演示建独立 tenant 与 API key。

## 3. 组合方式

```
Vite + React 前端 ──SSE──▶ FastAPI + LangGraph 编排 ──MCP/HTTP──▶ WeKnora（知识库、工单库、产品目录检索）
                              │
                              ├──▶ ModelRouter ──▶ Claude / Gemini / Qwen / DeepSeek / GLM（按环节路由 + 降级）
                              ├──▶ 业务规则服务（升级判定、质保路径，自研）
                              └──▶ PostgreSQL（会话状态、checkpoint）  Langfuse（追踪）
```

- WeKnora 只负责「找资料」，不负责「走流程」。流程由 LangGraph 状态机控制，保证进度可展示、升级可解释。
- 产品目录与经销商名录数据量小、需要精确匹配，放 PostgreSQL 表由业务规则服务查询，不走向量检索。
- 历史工单同时入 WeKnora（语义检索相似案例）与 PostgreSQL（结构化统计）。

## 4. 风险

- WeKnora 版本变动导致 MCP 工具签名变化：锁定镜像版本，检索调用封装在适配器接口后。
- 三路检索在小数据集上图谱收益有限：演示阶段可关闭图谱路径，只用 BM25 + 向量。
- 多组件部署增加演示环境故障点：提供单机 Docker Compose 与「离线回放模式」。

## 来源
- https://github.com/Tencent/WeKnora
- https://github.com/Tencent/WeKnora/blob/main/docs/api/mcp-service.md
- https://jimmysong.io/blog/open-source-ai-agent-workflow-comparison/
- https://www.firecrawl.dev/blog/best-open-source-rag-frameworks
- https://www.firecrawl.dev/blog/best-open-source-agent-frameworks
