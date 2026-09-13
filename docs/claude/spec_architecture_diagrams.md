# anker-haike 架构图与数据流程图（ASCII）

生成日期：2026-09-13。来源：docker-compose.yml、orchestrator/app/**、frontend/src/**、config/models.yaml。

## 1. 整体部署架构

```
                              ┌──────────────────────────────────────┐
                              │            浏览器 / 用户              │
                              │  Vite + React 19 SPA（同源托管）      │
                              └───────────────┬──────────────────────┘
                                              │ HTTP + SSE(text/event-stream)
                                              │ POST /sessions/{id}/messages
                                              │ GET  /sessions/{id}/runs/{rid}/events
                                              ▼
 ┌───────────────────────────────────────────────────────────────────────────────────┐
 │  orchestrator  :8000   FastAPI + LangGraph（Python 3.12 / uv）                     │
 │                                                                                   │
 │  ┌── HTTP 层 ─────────────┐ ┌── 编排层 ──────────┐ ┌── 能力层 ────────────────┐   │
 │  │ /sessions  会话/动作   │ │ RunManager 后台 run │ │ ModelRouter（降级链+并发门）│   │
 │  │ /models    通道自检    │ │ RunEmitter 事件落库 │ │ KnowledgeAdapter（四态）    │   │
 │  │ /health    聚合健康    │ │ StateGraph 状态机   │ │ RulesService  CP-in/CP-out  │   │
 │  │ /  静态前端 dist       │ │ SessionLock 串行    │ │ Catalog/Plans/FaultCards    │   │
 │  └────────────────────────┘ └────────────────────┘ └─────────────────────────────┘   │
 │            │                         │                     │            │           │
 └────────────┼─────────────────────────┼─────────────────────┼────────────┼───────────┘
              │ psycopg pool            │ checkpointer        │ HTTP       │ SDK(openai/anthropic/genai)
              ▼                         ▼                     ▼            ▼
 ┌────────────────────────┐  ┌────────────────────┐  ┌──────────────┐  ┌────────────────────┐
 │ PostgreSQL :5432       │  │ LangGraph          │  │ WeKnora :8080│  │ 模型厂商（外网）    │
 │ paradedb pg17+pgvector │  │ PostgresSaver      │  │ v0.8.0 RAG   │  │ deepseek / zhipu   │
 │  db haike:             │  │ checkpoints 表     │  │ hybrid-search│  │ dashscope          │
 │   sessions             │  │ （与业务同库）      │  └──────┬───────┘  │ anthropic / google │
 │   session_events       │  └────────────────────┘         │          └────────────────────┘
 │   session_actions      │                                 │ gRPC :50051
 │   session_images       │  ┌────────────────────┐  ┌──────▼────────┐
 │   products/plans/...   │  │ Redis :6379        │  │ docreader      │
 │  db WeKnora: 向量/分块 │  │ WeKnora 流管理     │  │ 文档解析/切块  │
 └───────────┬────────────┘  │ 编排侧仅 /health   │  └────────────────┘
             │               └────────────────────┘
             ▼
 ┌────────────────────────┐   ┌──────────────────────────────┐
 │ pg-backup（每日逻辑备份│   │ 可观测：JSONL 本地 + Langfuse │
 │ 两库，保留 7 天）       │   │ 告警：模型链/检索空/队列拒绝  │
 └────────────────────────┘   └──────────────────────────────┘
```

侧路（非在线链路）：`haike-*` CLI —— knowledge 灌库、bakeoff 厂商评测、inspection 故障巡检、replay 录制回放（`REPLAY_CASE_ID` 时 ReplayRouter/ReplayKnowledgeAdapter 顶替真实模型与检索）。

## 2. 编排服务内部分层

```
   HTTP  ─ sessions/router.py ── 会话锁(PG advisory) ── action_id 幂等 ── Command(resume)
                 │                                                          │
                 ├─ manager.py  RunManager：run 在后台任务跑，HTTP 只是订阅者 │
                 │     └─ runner.py  RunEmitter：事件先 append 拿 seq 再下发  │
                 ▼                                                          ▼
            sessions/graph.py  StateGraph(SessionState) + PostgresSaver checkpoint
                 │
   ┌─────────────┼───────────────┬───────────────┬──────────────┬─────────────┐
   ▼             ▼               ▼               ▼              ▼             ▼
 intake/      rules/          diagnose/        guide/       escalation/   warranty/
 extract      CP-in R3/R4/R6  query·rewrite    steps        summary       receipt
 rediagnose   CP-pre/verify   vision·synth     verify       polish        store
   │             │               │               │              │             │
   └─────────────┴───────────────┴───────┬───────┴──────────────┴─────────────┘
                                         ▼
                  models/router.py  ModelRouter.invoke / stream
                   ├ registry：别名→厂商 SDK（sdk_max_retries=0，唯一重试层在此）
                   ├ 结构化：native json_schema / json_object+提示 / tool-call，统一 Pydantic 校验
                   ├ 降级：超时·5xx 同模型重试1 → 换厂商；429 退避 1/2/4s；拒答不重试直接换
                   ├ 预算：单次 timeout = min(模型 timeout_s, 剩余预算)
                   └ queue.py BoundedGate：max_in_flight=50，满即 error(recoverable=true)
                                         │
                  knowledge/adapter.py   │   observability/runtime.py record()
                   ├ scope: confirmed_sku / category_only / unknown
                   ├ WeKnora POST /knowledge-bases/{id}/hybrid-search（遵守 knowledge_ids）
                   ├ 空允许集合 → 本地直接 no_match，不发请求
                   └ 四态 ok / no_match / unavailable / replay，单次 ≤ 2k token
```

## 3. LangGraph 状态机（会话内一次 run 的节点流转）

```
                          START
                            │ route_entry
        ┌───────────────────┼────────────────────┐
        ▼                   ▼                    ▼
   human_request         intake              rediagnose
        │              (CP-in R3/R4/R6)           │ route_after_rediagnose
        │                   │ route_after_intake  ├──► escalate
        │        ┌──────────┼──────────┐          ├──► clarify
        │        ▼          ▼          ▼          ├──► reassure
        │    escalate   reassure   disambiguate ◄─┘──► disambiguate
        │        ▲          │          │
        │        │          └──────────┤ route_after_disambiguate
        │        │       ┌────┬────────┼─────────┬──────────┬──────────┐
        │        │       ▼    ▼        ▼         ▼          ▼          ▼
        │        │  out_of_  clarify  prepare_  vision   retrieve    reply
        │        │   scope    │        card       │         │          │
        │        │     │      ▼         │         │ route_  │ route_   │ route_
        └────────┴─────┘    END         │         │ after_  │ after_   │ after_
                                        │         │ vision  │ retrieve │ reply
                                        ▼         ├──►retrieve         │
                                   await_input ◄──┤ └──►escalate       ├──► END
                                   (interrupt)    │      ▲             └──► guide
                                        │         │      │                   │
                                        ▼         │      │              route_after_guide
                                   apply_action ──┘      │              ├──► await_input
                                        │ route_after_apply             └──► escalate
        ┌──────┬──────┬────────┬────────┼────────┬───────┬────────┐
        ▼      ▼      ▼        ▼        ▼        ▼       ▼        ▼
      reply retrieve vision escalate out_of_  guide   close  rediagnose
                                      scope                    │
                                        │                      ▼
                                        ▼                     END
                                    escalate
                                        │ route_escalate
                    ┌───────────────────┼──────────────────────┐
                    ▼                   ▼                      ▼
                summarize         prepare_receipt        receipt_extract
                    │                   │                      │
                    ▼                   └────────► await_input ◄┘
                   END
```

要点：
- `await_input` 是唯一中断点（LangGraph `interrupt`），`awaiting_input` 事件由运行器在真正中断时发出，版本号取自 checkpoint。
- CP-in 命中 R3/R4 时从 intake 经条件边直达 escalate，**不经过任何调模型的节点**。
- `clarify` / `summarize` / `close` 三个终态节点直接到 END，一轮 run 结束。

## 4. 数据流程图 A：一条用户消息的完整链路

```
用户                前端 SPA            /sessions/{id}/messages         图节点            外部
 │                    │                          │                       │                │
 │ 输入文本(+图片)     │                          │                       │                │
 ├───────────────────►│                          │                       │                │
 │                    │ POST multipart           │                       │                │
 │                    ├─────────────────────────►│                       │                │
 │                    │                  ① 会话锁 + try_start_run         │                │
 │                    │                  ② 图片落 session_images(1h TTL) │                │
 │                    │                  ③ RunManager 起后台 run          │                │
 │                    │◄── SSE run_started ──────┤                       │                │
 │                    │                          ├──────────────────────►│ intake         │
 │                    │◄── progress(intake) ─────┤                       ├─ extract ─────►│ 模型 intake 链
 │                    │                          │                       ├─ CP-in 规则     │
 │                    │◄── message(安抚流式) ────┤                       │ reassure ─────►│ reply.stream
 │                    │                          │                       │ disambiguate   │
 │                    │◄── product_card ─────────┤                       │ prepare_card   │
 │                    │◄── awaiting_input ───────┤                       │ await_input ⏸  │
 │  选择 SKU           │                          │                       │  (interrupt)   │
 ├───────────────────►│ POST /actions            │                       │                │
 │                    ├─────────────────────────►│ 锁→幂等→Command(resume)│ apply_action  │
 │                    │◄── tool_call(started) ───┤                       │ vision ───────►│ 视觉模型
 │                    │◄── progress(retrieve) ───┤                       │ retrieve ─────►│ WeKnora hybrid
 │                    │◄── evidence ─────────────┤                       │  synthesize ──►│ 强推理模型
 │                    │◄── message(结论流式) ────┤                       │ reply          │
 │                    │◄── step_card ────────────┤                       │ guide ────────►│ guide.step
 │                    │◄── awaiting_input ───────┤                       │ await_input ⏸  │
 │ 反馈"没解决"        │                          │                       │                │
 ├───────────────────►│ POST /actions            │  step_feedback        │ apply_action   │
 │                    │◄── step_card / 换计划 ───┤                       │ guide 或        │
 │                    │◄── escalation_summary ───┤                       │ escalate→summarize
 │                    │◄── done(completed) ──────┤                       │                │
```

每条事件先 `append_event` 拿到 **seq** 再下发；SSE 以 `id: seq` 编码，断线后 `GET .../runs/{rid}/events?after_seq=N` 先重放再接实时，**断开连接 ≠ 取消**（取消要显式 `POST /cancel`）。

## 5. 数据流程图 B：检索与模型调用的数据加工

```
 用户文本 + 图片
     │
     ▼
 intake 抽取 ──► {emotion.strategy, product_hints, symptoms}
     │                    │
     │                    └──► 注入系统提示第二层（prompts/system.py）
     ▼
 disambiguate ──► product_state ∈ {confirmed_sku, category_only, unknown}
     │                    │
     │                    └──► KnowledgeScope(product_state, category, sku)
     ▼                                  │
 vision（可选）──► visible_parts / image_observations
     │                                  ▼
     ▼                        允许 knowledge_ids 集合
 build_query ──► query ─────────────────┤
     │                                  ▼
     │                    空集合? ──是──► no_match（不发请求）
     │                        │否
     │                        ▼
     │              WeKnora hybrid-search（match_count ×3 放大）
     │                        │
     │                        ▼
     │              本地按 knowledge_id 再过滤 + ≤2k token 截断
     │                        │
     ├── 无命中且允许改写 ──► query.rewrite 一次 ──► 第二轮检索（rewrite_used=true）
     │                        │
     ▼                        ▼
 evidence{evidence_id→片段}   knowledge_status ∈ ok|no_match|unavailable|replay
     │                        │
     └──────────┬─────────────┘
                ▼
        fault_card 预加载（≤800 token，fit_prompt_budget 裁剪）
                │
                ▼
        synthesize ──► plans_ranked[{plan_id, confidence, evidence_ids, source}]
                │        diagnose_outcome ∈ evidence | standard_flow | escalate
                ▼
        guide.prepare_step ──► step_card{title, instruction, evidence_ids}
                │              （证据引用必须落在 evidence 里，否则不发）
                ▼
        steps_executed / counters / guide_trace（跨 run 累积在 checkpoint）
```

## 6. 数据落点与生命周期

```
 ┌ checkpoint（LangGraph PostgresSaver）── SessionState 全量：messages / card_results /
 │   safety_flags / product_* / evidence / steps_executed / receipt …  ← 权威状态
 ├ session_events ── 每条契约事件 + seq，SSE 重放与快照派生的唯一来源
 ├ session_actions ── action_id 幂等占位与结果，重放同 action 返回同结果
 ├ session_images ── 图片字节，TTL 1h（images.runtime 清理）
 ├ sessions ── 会话行与 active_run_id（try_start_run 保证单活跃 run）
 ├ 投影表 ── 仅供列表/运维，快照 GET /sessions/{id} 不读投影，由 checkpoint+事件派生
 └ observability JSONL（+Langfuse 有界队列）── 脱敏后落盘，不占业务预算

 TTL（retention_loop）：会话 24h / 追踪 7d / 图片 1h。
```

## 7. 健康与降级

```
 GET /health ──┬─ db      psycopg ping
               ├─ redis   ping（WeKnora 流管理依赖，编排侧只观测）
               ├─ weknora HTTP 探活
               └─ models  按通道统计 provider key 就绪；GET /models/status、
                          POST /models/{alias}/probe 为真实连通性自检
                          （replay 模式与 HAIKE_LLM=off 时探测禁用并给出原因）

 降级策略：db down → 进程仍启动，/sessions 返回 503；weknora down → knowledge_status=
 unavailable，走标准排障流程且禁止常识补假设；模型链整条失败 → error(recoverable) 或
 escalate；并发门满 → error(recoverable=true, retry_with_same_action=true)。
```
