# 最终架构（2026-09-12 确定）

决策：后端 Python + LangGraph；前端 Vite + React + TypeScript（Preact 为备选）；知识层 WeKnora；模型、Embedding、Rerank 全部远程 API；pi 不采用（见 findings.md）。

2026-09-12 按设计评审（../2026-09-12_smart-service-design-review/review.md）修订：新增 08 会话执行契约、09 计划 / 规则 / 知识 / 凭证设计，本图同步。

## 1. 前端方案复核（修订）

| 关注点 | 结论 |
| --- | --- |
| 框架 | Vite + React 19 + TS。范围可能扩展成完整 Agent 产品，React 生态复用价值高于 Preact 省下的体积 |
| 流式文本 | fetch + ReadableStream 手写 SSE 解析 |
| 卡片交互 | 预注册 5 种业务卡片（产品、步骤、证据、凭证、摘要），事件驱动，模型不生成 UI |
| 会话状态 | 前端 6 态状态机（idle / streaming / tool_running / awaiting_input / failed / recovering），reducer 纯函数 |
| 执行与恢复 | 由后端 LangGraph checkpoint 负责，前端只重建视图 |
| 类型一致 | 后端 Pydantic 导出 JSON Schema，前端生成 TS 类型 |
| 演进 | 聊天基础能力需求增多时接 assistant-ui 自定义 runtime；页面级协作需求出现时评估 CopilotKit |
| 体积 | 以 vite build 实际报告为准 |

## 2. 系统架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         浏览器  Vite + React + TypeScript                      │
│                                                                              │
│  ┌──────────┐ ┌───────────┐ ┌──────────────────────────────┐ ┌───────────┐ │
│  │HeaderBar │ │ProgressBar│ │           ChatPane            │ │  Toast    │ │
│  │健康灯    │ │五阶段     │ │ UserBubble / AssistantBubble  │ │  error    │ │
│  └──────────┘ └───────────┘ │ ProductCard  StepCard         │ └───────────┘ │
│  ┌──────────────────────┐   │ EvidenceDrawer  SummaryCard   │               │
│  │ purpose=fault/receipt│   └──────────────────────────────┘               │
│  └──────────────────────┘                                                   │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ state/reducer (6 态 ui 状态机, 快照权威) ◀── api/sse.ts (seq/card_id/message_id 幂等) │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└───────────────┬──────────────────────────────────────────▲──────────────────┘
                │ POST messages (multipart)                  │ SSE: run_started / ping / progress / tool_call /
                │ POST actions {action_id, expected_version} │ message_start / message / message_end /
                │ POST cancel   GET snapshot                 │ product_card / step_card / receipt_card / evidence /
                │ GET runs/{id}/events?after_seq  GET /health│ awaiting_input / escalation_summary / error / done
                ▼                                            │
┌─────────────────────────────────────────────────────────────────────────────┐
│                    编排服务  Python 3.11  FastAPI + LangGraph                  │
│                                                                              │
│  ┌── API 层 ────────────────────────────────────────────────────────────┐   │
│  │ SSE + ping  事件先落 session_events 再发  会话锁串行  action_id 去重/409   │   │
│  └───────────────────────────────┬──────────────────────────────────────┘   │
│                                  ▼                                           │
│  ┌── LangGraph 状态图 ──────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  intake ─▶ disambiguate ─▶ diagnose ─▶ guide ─▶ verify ─▶ done       │   │
│  │    │          │   ▲  [P→A→X]     ▲        [P→A→X] │  ▲    continue    │   │
│  │    │          │   └─ select ─────┼───────────────┘  └── next_on ─┘   │   │
│  │    │          │ out_of_scope     │ rediagnose(补充症状/图片)            │   │
│  │    │          ▼                  │                                   │   │
│  │    └─ CP-in ─▶ escalate ◀── CP-verify R1/R1b/R1c/R2 ◀───────────────┘   │
│  │       R3/R4     ├─ 安全/主动 ─▶ summarize                            │   │
│  │                 └─ 常规 ─▶ collect_receipt[P→A→X] ─▶ extract         │   │
│  │                            ─▶ confirm_fields[P→A→X] ─▶ lookup ─▶ summarize ─▶ done │
│  │                                                                      │   │
│  │  [P→A→X] = prepare_card → await_input(interrupt) → apply_action       │   │
│  │  检查点：CP-in(每输入) CP-pre-step(发卡前) CP-verify(反馈后)            │   │
│  │  流过滤：messages 只透传 tag=user_visible；internal 调用不进聊天        │   │
│  └──────┬──────────────┬──────────────────┬──────────────────┬──────────┘   │
│         │              │                  │                  │              │
│  ┌──────▼──────┐ ┌─────▼──────┐ ┌─────────▼────────┐ ┌───────▼────────┐    │
│  │KnowledgeAd. │ │ ModelRouter │ │  规则服务(自研)   │ │ Checkpointer   │    │
│  │ scope→ids   │ │ invoke/stream│ │ R1–R8 检查点     │ │ PostgresSaver  │    │
│  │ 4态结果     │ │ 唯一重试层  │ │ 计划游标 凭证L1-6 │ │ + 事件日志      │    │
│  │ Replay(显式)│ │ budget_ms   │ │ product_state    │ │ + 动作去重      │    │
│  └──────┬──────┘ └─────┬──────┘ └─────────┬────────┘ └───────┬────────┘    │
└─────────┼──────────────┼──────────────────┼──────────────────┼─────────────┘
          │ HTTP/MCP     │ 多厂商 SDK/HTTP   │ SQL              │ SQL
┌─────────▼──────┐ ┌─────▼──────────┐ ┌─────▼──────────────────▼─────────────┐
│    WeKnora     │ │ 远程模型 API    │ │            PostgreSQL + pgvector       │
│ kb_manual      │ │ Qwen/DeepSeek/GLM│ │ products plans dealers orders_mock     │
│ kb_tickets     │ │ Claude/Gemini   │ │ langgraph_checkpoints(权威)            │
│ scope 元数据   │ │ Embedding/Rerank│ │ session_events/actions/images          │
│ BM25+向量+Rerank│ │ 远程 API        │ │ sessions(投影) WeKnora 自身表          │
│                │ └────────────────┘ │                                        │
└────────────────┘                    └───────────────────────────────────────┘
          │                                          │
┌─────────▼──────────────────────────────────────────▼─────────────────────┐
│  Redis(仅 WeKnora 依赖)   Langfuse(可选 profile)   结构化日志(JSONL)   回放录制包  │
└──────────────────────────────────────────────────────────────────────────┘

部署：单机 Docker Compose = orchestrator(含静态前端) + weknora + postgres + redis [+ langfuse profile]；模型 / Embedding / Rerank 全部远程 API，无本地模型容器。资源预算见 04 §5。
```

## 3. 一次对话的数据流（A1 排障成功）

```
用户           前端                  编排服务/LangGraph                     WeKnora     模型API
 │ 文本+图片     │                         │                                   │          │
 ├─────────────▶│ POST messages           │                                   │          │
 │              ├────────────────────────▶│ 落图→run_started(deadline 40s)     │          │
 │              │◀─ progress(intake) ─────┤ CP-in 规则(安全词) 未命中           │          │
 │              │                         │ intake 抽取(internal) ──────────────────────▶│
 │              │◀─ message_start/delta ──┤ reply.stream 安抚(user_visible) ────────────▶│
 │              │◀─ message_end ──────────┤                                   │          │
 │              │◀─ progress(diagnose) ───┤ disambiguate 单命中 → confirmed_sku│          │
 │              │◀─ tool_call(search) ────┤ 文本query 检索(scope=sku) ─────────▶│          │
 │              │◀─ tool_call(vision) ────┤ 读图(internal) 并行 ────────────────────────▶│
 │              │                         │◀─ hits(ok) ────────────────────────┤          │
 │              │                         │ 观察过 CP-in；有新信息→补检索(可选)  │          │
 │              │◀─ evidence(ids) ────────┤ synthesize → plans_ranked(internal) ────────▶│
 │              │◀─ progress(guide) ──────┤ prepare_card: 改写 s1(internal) ─────────────▶│
 │              │                         │   持久化 pending_card(card_id 稳定) │          │
 │              │                         │ CP-pre-step 通过                    │          │
 │              │◀─ step_card(card_id) ───┤ await_input                        │          │
 │              │◀─ awaiting_input ───────┤ interrupt                          │          │
 │              │◀─ done(awaiting, v=5) ──┤                                   │          │
 │ 点「已解决」  │                         │                                   │          │
 ├─────────────▶│ POST actions            │                                   │          │
 │              │ {action_id, card_id,    │                                   │          │
 │              │  expected_version=5}    │                                   │          │
 │              ├────────────────────────▶│ 会话锁 → 去重 → 版本/卡片校验        │          │
 │              │◀─ run_started(resumed) ─┤ Command(resume) → await_input 重跑  │          │
 │              │   (step_card 重发, 前端按 card_id 幂等)                       │          │
 │              │                         │ apply_action → verify: solved      │          │
 │              │◀─ progress(done) ───────┤                                   │          │
 │              │◀─ message(结束语) ──────┤ reply.stream(user_visible) ─────────────────▶│
 │              │◀─ done(completed, v=6) ─┤ 回填 session_actions 结果          │          │
```

A3 升级分支在 verify 触发 R1/R2 后：escalate → collect_receipt[awaiting upload_receipt] → 用户传凭证(purpose=receipt) → extract(receipt_ocr) → confirm_fields[receipt_card, awaiting confirm_receipt] → 用户改字段确认 → lookup(L1–L6 核对 SKU 与渠道) → summarize → escalation_summary → done。

## 4. 边界与替换点

| 边界 | 接口 | 可替换为 |
| --- | --- | --- |
| 前端 ↔ 编排 | 08 会话执行契约（事件 / 动作 / 快照 Schema，make contracts 生成） | 任何能消费 SSE 的前端 |
| 编排 ↔ 知识层 | KnowledgeAdapter.hybrid_search(scope) → 四态 ToolResult | RAGFlow；Replay 仅显式回放 |
| 编排 ↔ 模型 | ModelRouter（LangChain init_chat_model；Claude/Gemini 官方集成，国内厂商 OpenAI 兼容 + base_url） | 按 task 路由，主备链跨厂商、跨通道降级，见 model-selection.md |
| 编排 ↔ 规则 | 三个检查点 + plans / rules 配置表（09） | 外部规则引擎 |
| 编排 ↔ 持久化 | Checkpointer（权威）+ session_events / actions（08 §2） | 内存(测试)、PostgreSQL |
