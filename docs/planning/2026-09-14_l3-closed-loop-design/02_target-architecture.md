# 第二步：目标架构与状态图改造

## 1. 分层变化

在 [06_architecture-final.md](../2026-09-12_smart-service-tech-design/06_architecture-final.md) 的四个边界（前端↔编排、编排↔知识、编排↔模型、编排↔规则）之外新增两个边界，并给「规则」补一个同级的「政策」：

```
┌──────────────────────────── 浏览器 ────────────────────────────┐
│ 用户端 SPA：+ContextCard +ProposalCard +ExecutionCard +RetakeCard │
│              +CaseStatus（等待人工 / 跟踪中 / 已结案）+RatingCard   │
│ 管理端 SPA：+审批队列页 +案件详情页（摘要 / 建议 / 政策依据 / 草稿）   │
└──────────────┬───────────────────────────────▲──────────────────┘
               │ /messages /actions(+5 kinds) /feedback │ SSE(+6 events)
               │ /admin/api/cases/{id}/decision          │
┌──────────────▼───────────────────────────────┴──────────────────┐
│ 编排服务 FastAPI + LangGraph                                        │
│  understand ─┬─ consult ──────────────────────────────┐            │
│              ├─ (原链) disambiguate → vision → retrieve → guide ──┤            │
│              ├─ escalate ─┬─ service_context → propose → authorize │            │
│              │            │      ↓ needs_human            ↓ pass   │            │
│              │            │   await_human ◀─ human_decision  execute → track │
│              │            └─ summarize（安全/人工/R7/R8 保持）        │            │
│              └─ apply_action(+confirm_proposal / confirm_context / …)          │
│  ┌──────────┐ ┌───────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ ┌────────┐ │
│  │Knowledge │ │ModelRouter│ │Rules R1–8│ │Policy ★  │ │Actions ★│ │Cases ★ │ │
│  │Adapter   │ │(+bedrock) │ │CP-in/pre │ │decide()  │ │registry │ │lifecycle│ │
│  └──────────┘ └───────────┘ └──────────┘ └──────────┘ │gate/exec│ │HITL    │ │
│                                                        └────┬────┘ └───┬────┘ │
└─────────────────────────────────────────────────────────────┼──────────┼──────┘
                                                              ▼          ▼
                                            模拟后端 ★（orders / shipments / service_orders）  PostgreSQL（cases / action_executions / human_decisions / ratings）
```

★ 为新增。四个新组件的接口与可替换点：

| 边界 | 接口 | 可替换为 |
| --- | --- | --- |
| 编排 ↔ 政策 | `PolicyEngine.decide(PolicyInput) → PolicyDecision`，纯函数，配置 `config/policy/*.yaml` | 外部规则引擎 / 真实 SOP 编译产物 |
| 编排 ↔ 动作 | `ActionRegistry.spec(kind)`、`AuthorizationGate.check(...) → GateResult`、`ActionExecutor.run(kind, params, idem_key) → Receipt` | 真实系统适配器（同一 `BackendClient` 协议） |
| 动作 ↔ 后端 | `BackendClient` 协议：`get_order / get_shipment / create_service_order / get_service_order`，异常分类 `NotFound / Conflict / Unavailable / Timeout` | 真实 OMS / WMS / RMA API |
| 编排 ↔ 案件 | `CaseService.open / transition / attach_execution / close / reopen`，事件 `case_changed` | 外部工单系统 |

## 2. 状态图改造

### 2.1 新节点
| 节点 | 职责 | 模型调用 | 出口 |
| --- | --- | --- | --- |
| `consult` | 简单咨询快路径：参数（订单号 / 单号）抽取 → 缺参追问 → 调只读动作 → 回答 + 来源 | `consult.extract_params`（轻量，可被 interpret 的 facts 覆盖而跳过） | `commit_issue`；缺参 → `dialogue`（文本追问，计 clarification） |
| `service_context` | 汇总购买地 / 使用地 / 渠道 / 平台；缺项发 ContextCard | 无 | 齐 → `propose`；缺 → `prepare_context → await_input` |
| `propose` | 政策判定 → 方案列表（确定性模板）→ 可选措辞润色 → ProposalCard | `propose.wording`（可选，失败直渲染） | `prepare_proposal → await_input`；needs_human → `await_human`；无可用方案 → `summarize` |
| `authorize` | 授权门四项检查（政策 auto_allowed、证据、用户确认、幂等） | 无 | pass → `execute`；fail → `await_human` |
| `execute` | 调 ActionExecutor，写 action_executions，发 ExecutionCard，case → tracking/closed | 无 | `track` |
| `track` | 只读同步外部状态（模拟后端）；生成用户可见进度；决定是否发 RatingCard | 无 | `close`（用户确认解决）或 `commit_issue` |
| `await_human` | 案件 → awaiting_approval，发 `case_changed` + 用户可见说明；run 正常结束 | 无 | `commit_issue` |
| `apply_human_decision` | 新输入类型 `human_decision` 进入：approve → `execute`（用批准后的方案）；reject → `reply`（解释 + 备选）；request_info → `dialogue` | 无 | 见左 |

### 2.2 路由改动
- `route_entry`：新增 `primary_intent ∈ CONSULT_INTENTS → consult`；`entry == "human_decision" → apply_human_decision`；多意图入队在 `understand` 内完成（见 06 §3）。
- `route_escalate`：`escalate_reason ∈ {R1, R1b, R1c, R2, R6}` 且 `product_state == confirmed_sku` → `service_context`（代替直接进凭证）；凭证子流程改为 service_context 的一部分（凭证是四字段的来源之一）；R3 / R4 / R7 / R8 保持 → `summarize`。
- `route_after_apply`：`confirm_proposal → authorize`；`decline_proposal → propose`（换方案）或 `summarize`；`confirm_context → propose`；`skip_retake → retrieve`；`rate_satisfaction → commit_issue`。
- `route_after_guide`：不变；`close` 增加「任务队列非空 → consult」。
- `route_after_vision`：`image_quality.usable == false 且未跳过 → prepare_retake → await_input`。

### 2.3 Stage 扩展
`Stage += consult | context | propose | execute | track | awaiting_human`。前端 ProgressBar 五段折叠：理解（intake/disambiguate/consult）→ 诊断（diagnose）→ 处理（guide/verify/context/propose）→ 办理（execute/track/awaiting_human）→ 结束（done/escalate）。

### 2.4 SessionState 新字段
```
service_context: {region_purchase, region_use, channel, platform, source: receipt|user|unknown per field}
policy_decision: PolicyDecision | None
proposal: {card_id, options:[...], chosen_option_id, status}
task_queue: [{task_id, intent, quote, status: pending|active|done|dropped, created_input_id}]
emotion_track: [{input_id, level}]   # 最近 6 轮
case_id: str | None
execution: {execution_id, action_kind, idempotency_key, status, receipt}
fault_localization: FaultLocalization | None
```
`issues[issue_id]` 同步持久化 task_queue / emotion_track / case_id（跟随 ISSUE_FIELDS）。

## 3. 一次 A5 对话的数据流
1. 用户：「三步都试了还是不吸，我要换货」→ `understand`：intent=replacement_request，R6 flag；emotion=dissatisfied。
2. `route_entry → escalate`（reason R6）→ `route_escalate → service_context`：从 receipt.verified_facts 取 channel / purchase_date；region 缺 → ContextCard（购买地 / 使用地）→ await_input。
3. 用户选 CN / CN → `apply_action(confirm_context) → propose`：`PolicyEngine.decide()` → replace eligible（保内、品质问题、官方渠道），refund 不满足 30 天，repair eligible；模板生成两项方案 + 条款引用 → ProposalCard → await_input。
4. 用户选「换货」→ `apply_action(confirm_proposal) → authorize`：auto_allowed ✓、receipt order_verified ✓、product confirmed ✓、无 R4 ✓、无重复执行 ✓ → `execute`。
5. `execute`：`replacement.create(order_no, sku, reason=fault_class, evidence_ids)`，幂等键 `case_id:replace:v1` → 模拟后端返回 service_order_no → ExecutionCard；case → tracking。
6. `track`：读取 service_order 状态（created）→ 用户可见说明「已创建换货单，预计 3 个工作日发出」→ RatingCard（可稍后）→ END。用户后续「发了吗」走 A4 路径读同一模拟后端。

## 4. 与 AWS 的关系（D-L3-2/3/4）
- `providers.bedrock: {sdk: bedrock, region_env: AWS_REGION, lane: aws}`；模型别名 `bedrock-sonnet` / `bedrock-haiku`（Claude on Bedrock，vision + native structured）；`lanes.aws` 镜像 overseas 链。ModelRouter 增加 `ChatBedrockConverse` 初始化分支（`langchain-aws`）。
- 检索不换：文档提示与 D-L3-3 一致，作为方案卖点写明「自研召回策略：范围过滤 + 双库 RRF + 可选 rerank / grade + 证据白名单」。
- Step Functions 仅在 P2 作为案件级定时器候选（物流轮询、审批超时提醒），会话图不依赖。

## 5. 对既有文档的修订点
- 02 §3 状态机 / 08 §3 节点拆分：追加 §2.1 节点与 §2.3 Stage。
- 09 §5 凭证子流程：并入 service_context，凭证成为四字段来源之一；L1–L6 不变。
- 03 §1.7 升级摘要：EscalationSummary 增加 policy_decision 摘要、case_id、task_queue、recommended_options、draft_reply（供 HITL）。
- 07 §14 工具定义即 API：以 03_action-layer 的 ActionSpec 为实例。
