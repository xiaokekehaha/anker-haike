# 第三步：业务办理执行层（Action 层）

目标：让「办事」成为图里可校验、可幂等、可回放、可替换后端的一等能力。零 LLM。

## 1. 模块布局
```
orchestrator/app/actions/
  registry.py      # ActionSpec 注册表（从 config/actions.yaml 加载 + 代码内 handler 绑定）
  gate.py          # AuthorizationGate：四项检查，输出 GateResult
  executor.py      # ActionExecutor：幂等、超时、回执、审计落库、tool_call 事件
  receipts.py      # Receipt 模型与用户可见摘要渲染
  params.py        # 参数抽取/补全（订单号、单号正则 + interpret facts；缺参列表）
orchestrator/app/backends/
  protocol.py      # BackendClient 协议 + 异常分类
  mock.py          # Postgres 演示表实现 + 故障注入
  seed.py          # haike-seed backends
config/actions.yaml
config/backends_mock.yaml   # 演示订单 / 运单 / 服务单 seed（接续 receipt_reference.yaml）
```

## 2. ActionSpec（`config/actions.yaml`）
```yaml
version: 2026-09-14.1
actions:
  logistics.query:
    kind: read
    params: {order_no: {type: str, pattern: "^[A-Z0-9-]{6,20}$", required_one_of: [order_no, tracking_no]},
             tracking_no: {type: str}}
    backend: get_shipment
    timeout_ms: 3000
    user_summary: "订单 {order_no} 当前状态：{status}（{updated_at}）"
    citation: backend            # 回答里标「来源：物流系统（模拟）」
  warranty.check:
    kind: read
    params: {order_no: {type: str}, sku: {type: str, from_state: product_confirmed.sku}}
    backend: get_order
    post: policy.decide          # 读订单后调政策引擎，回答保修状态 + 条款
    timeout_ms: 3000
  replacement.create:
    kind: write
    params: {order_no: {required: true}, sku: {from_state: product_confirmed.sku},
             reason_code: {from_state: policy_decision.fault_class},
             evidence_ids: {from_state: current_evidence_ids}}
    requires: {policy_auto_allowed: replace, receipt_status: [order_verified], product_state: [confirmed_sku], user_confirmed: true}
    idempotency: "{case_id}:replacement.create:{proposal.chosen_option_id}"
    backend: create_service_order
    timeout_ms: 5000
    receipt_fields: [service_order_no, eta_days, next_step]
```
规则：`kind: write` 必须有 `requires` 与 `idempotency`；`params.from_state` 只能引用白名单状态字段；未在注册表内的 kind 不可执行（`route_after_apply` 前置校验）。

## 3. 授权门（`gate.py`）
输入：`PolicyDecision`、`proposal.chosen_option`、`receipt`、`product_state`、`risk_cases`、`case`、`action_executions`。输出：
```python
@dataclass(frozen=True)
class GateResult:
    passed: bool
    checks: list[GateCheck]   # {name, passed, detail}
    fallback: Literal["await_human", "summarize"] | None
```
四项检查（全部通过才 passed）：
1. **政策**：`decision.remedies[chosen].eligible and auto_allowed`；`decision.needs_human == False`。
2. **证据**：`receipt.status ∈ requires.receipt_status`；`product_state ∈ requires.product_state`；`fault_class != unknown`。
3. **安全与限制**：无 `status=reported` 的 R4 risk_case（除 remedy 本身是安全召回类）；`turn_decision.allowed_operations == True`。
4. **幂等与并发**：同 idempotency_key 无 `status ∈ {running, succeeded}` 的执行；case 状态 ∈ {proposing, awaiting_confirmation}。

任一失败 → `await_human`，`GateResult.checks` 原样进案件与摘要（HITL 看得到为何没自动办）。

## 4. 执行器（`executor.py`）
```
run(kind, params, *, idempotency_key, case_id, session_id, run_id, deadline_ms) -> Receipt
```
- 先 `INSERT action_executions(status=running)`，唯一约束 idempotency_key；冲突且已 succeeded → 直接返回旧回执（重跑安全）；冲突且 running 超过 timeout → 标 stale 后重试一次。
- 调 `BackendClient`；异常分类：`NotFound → failed(user_visible: 未找到订单)`、`Conflict → failed(已存在服务单，返回其号)`、`Unavailable/Timeout → failed(recoverable=True)` 并建议稍后 / 转人工。
- 事件：`tool_call{name: kind, status: started|finished|failed, summary}`；成功后 `execution_card`。
- 审计：request / receipt / error / gate_result / policy_version / actions_version 全部落 `action_executions`。
- 隐私：日志经 `privacy.sanitize`（订单号已在脱敏正则内，补 tracking_no / service_order_no）。

### 表（迁移 0006 一部分）
```sql
action_executions(
  execution_id uuid pk, case_id uuid, session_id text, issue_id text, run_id text,
  action_kind text, idempotency_key text unique, request jsonb, gate_result jsonb,
  status text check (status in ('running','succeeded','failed','stale')),
  receipt jsonb, error jsonb, policy_version text, actions_version text,
  started_at timestamptz, finished_at timestamptz)
```

## 5. 模拟后端（`backends/`）
协议：
```python
class BackendClient(Protocol):
    async def get_order(self, order_no) -> Order
    async def get_shipment(self, *, order_no=None, tracking_no=None) -> Shipment
    async def create_service_order(self, req: ServiceOrderRequest) -> ServiceOrder
    async def get_service_order(self, service_order_no) -> ServiceOrder
```
Mock 实现：读写 Postgres 演示表 `orders_mock`（已有，补 `region_purchase, platform, amount, currency`）、`shipments_mock(tracking_no pk, order_no, carrier, status, events jsonb, updated_at)`、`service_orders_mock(service_order_no pk, order_no, sku, type, reason_code, status, created_at, eta_days)`。故障注入：`config/backends_mock.yaml` 的 `faults: [{op: create_service_order, order_no: DEMO-FAIL-001, mode: timeout|unavailable|conflict}]`，演示降级路径。`haike-seed backends` / `make seed WHAT=backends`。

## 6. 契约增量（票 51 统一落地）
- `ActionKind += confirm_context | confirm_proposal | decline_proposal | skip_retake | rate_satisfaction`；载荷：`ConfirmContextPayload{region_purchase, region_use, channel, platform}`、`ConfirmProposalPayload{option_id}`、`DeclineProposalPayload{reason: want_other|not_now|request_human}`、`SkipRetakePayload{reason}`、`RateSatisfactionPayload{score:1..5, comment?}`。
- `PendingKind += confirm_context | confirm_proposal | upload_retake | rate_satisfaction`。
- 事件：`context_card{fields, prefilled, sources}`、`proposal_card{options:[{option_id, remedy, title, cost_bearer, conditions, clauses:[{clause_id, text, policy_version}], auto_allowed}], decision_summary}`、`execution_card{execution_id, action_kind, status, receipt:{service_order_no?, status, eta_days?, next_step}, idempotency_key}`、`retake_card{reasons, guidance}`、`rating_card{}`、`case_changed{case_id, status, complaint_risk, owner?, reason}`。
- 快照 items：对应 `ContextCardItem / ProposalCardItem(+chosen_option_id) / ExecutionCardItem / RetakeCardItem(+skipped) / RatingCardItem(+score) / CaseStatusItem`。
- 前端 `reducer.ts` upsert 保留用户结果字段；`Timeline.tsx` 新增五个 case 分支。

## 7. 与图的接线
- `apply_action(confirm_proposal)` → 写 `proposal.chosen_option_id`、`card_results` → `route_after_apply → authorize`。
- `authorize` 节点无 IO，只调 `gate.check`；`execute` 节点调 `executor.run`，成功后 `CaseService.attach_execution`。
- `consult` 节点对只读动作复用 `executor.run`（幂等键 `session:run:kind:params_hash`，不落 case）。

## 8. 测试
- 单测：registry 加载校验（write 缺 requires 报错）、gate 四项各一负例、executor 幂等（同键二次返回同回执）、mock 故障注入三模式。
- 集成：A5 全链 API → SSE → 快照；A6 gate fail → await_human；中断后重跑同 run 幂等。
- 越权评测：`data/eval/authorization/cases.yaml` ≥ 20 条，断言写动作调用次数 = 期望（多数为 0）。
