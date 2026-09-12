# 调研发现

## 赛道要求（来自 docs/smart-service-track.md）
- 五项能力：情绪识别与安抚、产品消歧、故障定位（多模态）、排障引导、升级与后续处理。
- 建议流程六步：描述问题 → 确认产品 → 判断故障 → 分步排障 → 确认结果 → 升级处理。
- 三个演示案例：排障成功、产品歧义、排障失败升级。
- 知识库、历史工单、经销商名录官方未给开放清单，需自建模拟数据。
- 预赛只要方案文档，截止 2026-09-27 23:59；技术设计服务于复赛/决赛实现与预赛「自由展示区」。

## 技术调研
- WeKnora（腾讯，Go）：BM25 + 向量 + 图谱三路混合检索、RRF 融合、Rerank；PDF/Word/图片多格式解析含 OCR 与 VLM；内置 MCP 服务和 CLI，可被外部 Agent 以工具方式调用；支持 Ollama 与 OpenAI 兼容 API；Docker Compose 部署。
- LangGraph：有状态图编排，支持 checkpoint、中断与人机交接，适合显式状态机式客服流程。
- Dify：低代码平台，适合快速原型与非开发者调 Prompt，但流程控制粒度粗，卡片式前端难定制。
- RAGFlow：文档解析与表格抽取强，适合复杂 PDF 说明书；与 WeKnora 定位重叠，二选一。
- 评测：RAGAS 做检索质量评估；Langfuse 做 LLM 调用追踪（WeKnora 已集成）。
- 前端（改）：轻量方案对比 Preact 约 4 KB、Svelte 约 3 KB、Lit 约 5 KB；assistant-ui / CopilotKit / Vercel AI SDK UI 均绑定 React 与自有协议，对 Python 后端不友好。选 Vite + Preact + TS。
- 后端流式：FastAPI StreamingResponse + LangGraph astream 三流模式（updates / custom / messages），get_stream_writer 发结构化事件，必发终止事件；Python ≥ 3.11 避免 ContextVar 问题。

## 决策依据
- 选 WeKnora 而不是 RAGFlow：一体化提供检索 + MCP 工具 + 多模态，Go 单二进制资源占用低，赛事演示部署简单。
- 选 LangGraph 而不是 Dify：赛题五阶段是显式状态，需要代码控制迁移和升级判定，Dify 的画布难表达反馈回路与规则。

## pi（Mario Zechner / Earendil）作为 Agent 运行时的评估（2026-09-12）
- pi 是 TypeScript 工具包：pi-ai（多厂商统一 LLM API）、pi-agent-core（工具调用循环 + 事件流）、pi-coding-agent（编码 agent 与 SDK，内置 bash/read/write/edit）、pi-web-ui（Lit 聊天组件）。2026-05 包名从 @mariozechner 迁到 @earendil-works。
- 优点：LLM 接入与工具循环、流式事件开箱即用；一种语言贯通前后端；极简、可控。
- 缺点：无内置 RAG、无状态机、无 checkpoint / interrupt / resume；无 MCP 客户端于 agent-core 层；编码工具对客服场景无用且有安全风险；与「后端 Python」决策冲突。
- 若采用：后端改 Node/TS；用 pi-agent-core 而非 coding-agent SDK；自研阶段控制器与状态持久化；WeKnora 走 HTTP；卡片用「工具调用 → 前端卡片」模式；Langfuse 用 TS SDK 手动埋点。
- 结论：待用户决定。团队若更熟 TS 可选 pi，否则维持 Python + LangGraph。

## 模型接入（2026-09-12 追加）
- 用户不考虑本机部署，全部远程调用；不同环节用不同模型，需要适配层。
- LangChain init_chat_model 支持 provider:model 字符串统一建实例，国内厂商走 openai provider + base_url；with_structured_output 的 json_schema 方法在 OpenAI / Anthropic / Gemini 原生支持，其他模型退化为 json_object 或工具调用；with_fallbacks 可做链式降级。
- LiteLLM Proxy 可作网关方案，但 alias 与 fallback 组合有已知边角问题，当前不引入。
- 视觉模型独立测评：不同任务领先者不同（Claude 文档 / 图表，GPT 通用 VQA，Gemini 多图），按任务路由比单模型高 5–15%；单图成本相差 13 倍（Qwen VL 约 $0.0003，Claude Sonnet 约 $0.004）。
- 国内 API：DeepSeek 价格最低且有缓存命中价；Qwen 系列矩阵最全含 VL；GLM 工具调用口碑好；均提供 OpenAI 兼容接口。价格变动频繁，以厂商控制台为准。

## 设计评审采纳记录（2026-09-12）
| 评审项 | 落点 |
| --- | --- |
| R1 规则检查点 | 09 §1：CP-in / CP-pre-step / CP-verify；rediagnose 动作；R4 优先 |
| R2 产品适用性 | 09 §2：product_state 三分；scope 元数据；KnowledgeScope → knowledge_ids；空集合直接 no_match；IV-1 待核对 |
| R3 有限计划 | 09 §3：plans 表、plan_cursor、counters、R1/R1b/R1c/R2 |
| R4 中断恢复 | 08 §2–§7：三段式节点、action_id / expected_version / card_id、事件日志、快照、取消 |
| R5 流过滤 | 08 §5：user_visible / internal tag；message_start / end / replaces |
| R6 事件一致 | 08 §5 唯一定义；05 类型摘录；step / summary 对象层级；evidence_id；PendingKind 含 upload_receipt / confirm_receipt |
| R7 订单核对 | 09 §5.2：L1–L6；core.sku 核对；低置信降级；不输出资格结论（D16） |
| R8 知识四态 | 09 §4：ok / no_match / unavailable / replay；删除常识假设与 Mock 兜底 |
| R9 deadline | 08 §8：run deadline、task 预算、唯一重试层 |
| R10 全远程与路由 | model-selection §2 远程 Embedding / Rerank；§3.7 唯一 YAML（冒号修正）；§4 生成表；06 图同步 |
| R11 回放分离 | 09 §6：回放 / fixture / bake-off 三分；缓存键 |
| 简化建议 | D15 规则管计划；ModelRouter invoke / stream 分离；08 单独契约；04 §5 依赖与资源预算 |
