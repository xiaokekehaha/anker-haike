# 第二步：总体设计

## 1. 设计原则
- 流程用显式状态机控制，LLM 只负责状态内的理解与生成。保证进度可展示、升级可解释、演示可复现。
- 检索交给 WeKnora，编排交给 LangGraph，规则交给自研服务。三者边界清楚，任何一个可替换。
- 会话状态是唯一事实来源，前端卡片和转人工摘要都从它渲染。

## 2. 系统架构

```
┌──────────────────── 前端 Vite + React + TypeScript ─────────────────┐
│ 聊天区 │ 图片上传 │ 产品卡 │ 步骤卡 │ 凭证卡 │ 进度条 │ 转人工摘要 │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ SSE 流式事件（message / card / progress / summary）
┌───────────────────────────────▼──────────────────────────────────────┐
│              编排服务 Python FastAPI + LangGraph（Python ≥ 3.11）       │
│  状态机节点：intake → disambiguate → diagnose → guide → verify → escalate │
│  等待节点三段式：prepare_card → await_input(interrupt) → apply_action    │
│  横切：CP-in/CP-pre-step/CP-verify 规则检查点 │ 情绪 │ 裁剪 │ 校验 │ 追踪 │
└──────┬─────────────────┬──────────────────┬──────────────────┬────────┘
       │ MCP / HTTP      │ OpenAI 兼容 API   │ 内部调用          │ SQL
┌──────▼──────┐  ┌───────▼───────┐  ┌───────▼────────┐  ┌──────▼───────┐
│  WeKnora    │  │ 多模态 LLM     │  │ 业务规则服务     │  │ PostgreSQL   │
│ 知识库/工单  │  │ 主：云端       │  │ 升级判定、质保   │  │ 会话状态      │
│ 混合检索     │  │ ModelRouter    │  │ 路径、步数上限   │  │ checkpoint   │
└─────────────┘  └───────────────┘  └────────────────┘  │ 产品目录/名录 │
                                                         └──────────────┘
                              Langfuse（LLM 追踪） │ Redis（会话缓存）
```

## 3. 状态机

| 状态 | 职责 | 进入条件 | 退出条件 |
| --- | --- | --- | --- |
| intake | 接收首条描述与图片，过 CP-in 规则检查，情绪识别，抽取产品线索与症状 | 会话开始 | 抽取完成；R3 / R4 命中 → escalate |
| disambiguate | 产品目录匹配，得出 product_state ∈ {confirmed_sku, category_only, unknown}；多命中出确认卡片并等待 | intake 完成 | confirmed_sku / category_only → diagnose；unknown 两次追问仍未定 → escalate(R7)；选中 in_scope=false → out_of_scope |
| out_of_scope | 说明本期仅支持扫地机，生成简短摘要 | 选中范围外产品 | → escalate(R8) |
| diagnose | 图片理解（观察项过 CP-in）+ 受 KnowledgeScope 约束的混合检索 + 相似工单，产出 plans_ranked | 产品状态允许 | plans_ranked 非空 → guide；无可用计划 → escalate(R5) |
| guide | 按 plan_cursor 取步骤，prepare_card 持久化 → CP-pre-step → await_input | diagnose 完成或 verify 继续 | 收到 step_feedback |
| verify | apply_action：更新 counters 与 plan_cursor，CP-verify 判定 | guide 收到反馈 | solved → done；继续 → guide；R1/R1b/R1c/R2 → escalate |
| escalate | 子流程：安全 / 主动升级直接 summarize；常规升级 collect_receipt → extract → confirm_fields → lookup → summarize | 任一规则命中或 request_human | escalation_summary 发出 → done |
| done | 结束，记录结果 | | |

补充边：
- guide / verify 阶段用户发送自由文本或图片 → `rediagnose` 动作 → 过 CP-in → 回到 diagnose，保留 steps_executed。
- `request_human` 在任何状态可用，取消 active run 后进入 escalate。
- 情绪识别在每个用户消息进入时运行，结果写入状态并注入系统提示，不单独占状态。
- 等待用户输入的节点一律拆成 prepare_card → await_input → apply_action 三段，见 08_session-execution-contract.md §3。

## 4. 数据流程

### 4.1 主链路（A1 排障成功）
1. 前端上传文本与图片（purpose=fault）→ 编排服务保存图片到 PostgreSQL bytea 并在状态中存引用，发出 run_started 与 progress(intake)。
2. intake 节点：CP-in 规则检查（安全词、请求人工）→ LLM 结构化抽取 {产品线索, 症状, 情绪}（internal 调用，不进聊天流）→ reply.stream 生成安抚句（user_visible）。
3. disambiguate 节点：规则服务按线索查产品目录；单命中直接确认，发 progress(diagnose)。
4. diagnose 节点：文本 query 先发检索；同时多模态 LLM 读图输出观察（过 CP-in）；观察有新增信息时补一次检索。检索受 KnowledgeScope 约束（09 §2.3）。LLM 汇总为 plans_ranked [{plan_id, confidence, evidence_ids}]，无对应计划的假设丢弃。
5. guide：prepare_card 持久化 pending_card（card_id 稳定）→ CP-pre-step → await_input 发 step_card + awaiting_input → interrupt → done(awaiting_input)。
6. 用户点「已解决」→ POST actions（action_id, expected_version）→ apply_action 去重校验 → verify 标记 solved → done(completed)。

### 4.2 分支：产品歧义（A2）
- disambiguate 多命中 → prepare_card(product) → await_input 发 product_card（含 in_scope 标记）+ 安抚 message → interrupt → 用户点选 → apply_action 写入 product_state → diagnose；选中 in_scope=false → out_of_scope。

### 4.3 分支：升级（A3）
- verify 收到「仍有问题」→ counters.executed+1，plan_cursor 按 next_on 推进；计划 EXHAUSTED 且无可切换计划，或 executed ≥ 4 → escalate。
- escalate 常规路径：collect_receipt（awaiting_input=upload_receipt，可 skip）→ extract（receipt_ocr）→ confirm_fields（receipt_card，awaiting_input=confirm_receipt）→ lookup（订单表核对 SKU、经销商名录，输出 receipt.status 与已核实事实）→ summarize → escalation_summary → done。详见 09 §5。

### 4.4 数据进入 LLM 上下文的边界
- 进入上下文：最近 K 轮对话、当前状态摘要（产品、假设、已执行步骤）、检索 top-k 片段、图片观察结果。
- 不进入上下文：完整历史、原始图片二进制（仅首次读图时传）、用户手机号等标识。

## 5. 会话状态模型

| 字段 | 类型 | 写入者 | 消费者 |
| --- | --- | --- | --- |
| session_id / version | string / int | 编排 | 全部；version 每次 checkpoint 提交 +1 |
| stage / substage | enum | 状态机 | 进度条 |
| emotion | {level, strategy} | intake / 每轮 | 系统提示 |
| safety_flags | list[{rule_id, source, ts}] | CP-in / CP-pre-step | 规则、摘要 |
| product_state | confirmed_sku / category_only / unknown | disambiguate | 检索范围、guide 校验 |
| product_candidates | list[{sku, name, category, in_scope}] | disambiguate | 产品卡片 |
| product_confirmed | {sku?, name, category} | disambiguate | 检索过滤、订单核对、摘要 |
| symptoms | list[string] | intake / rediagnose | diagnose |
| image_refs | list[{image_id, purpose: fault / receipt, sha256}] | API 层 | diagnose、warranty |
| image_observations | list[string] | diagnose | diagnose、摘要 |
| plans_ranked | list[{plan_id, version, confidence, evidence_ids}] | diagnose | guide、摘要 |
| plan_cursor | {plan_id, step_id} | guide / verify | guide |
| steps_executed | list[{plan_id, step_id, card_id, feedback, note?, ts}] | apply_action | 步骤卡片、摘要 |
| counters | {executed, advanced, skipped, plans_exhausted} | verify | 规则 |
| exhausted_plans | list[plan_id] | verify | 规则 |
| pending_card | {card_id, kind, payload, version} | prepare_card | await_input、快照 |
| receipt | {status, fields, confidence, edited, verified_facts, conflicts, next_step} | escalate 子流程 | 凭证卡、摘要 |
| escalation | {triggered, rule_id, reason} | escalate | 摘要 |
| retrieval_trace | list[{query, scope, status, hit_ids, scores}] | diagnose | 来源展示、日志 |
| model_trace | list[{task, model_used, lane, attempts}] | ModelRouter | 摘要、Langfuse |

## 6. 部署视图
Docker Compose 单机：frontend（Vite 构建的静态文件，由 orchestrator 托管）、orchestrator、weknora-app、postgres(pgvector)、redis（WeKnora 依赖与会话锁）、langfuse（可选 profile）。模型、Embedding、Rerank 全部远程 API，无本地模型容器。模拟数据通过初始化脚本导入 WeKnora 与 PostgreSQL。各组件职责与资源预算见 04 §5。
