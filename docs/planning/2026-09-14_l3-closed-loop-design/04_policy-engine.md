# 第四步：售后政策规则引擎

目标：把「能不能办、办什么、谁承担、依据哪条」变成确定性判定，输出条款引用与版本。与安全规则（R1–R8，决定「继续排障还是升级」）分离。零 LLM。

## 1. 模块
```
orchestrator/app/policy/
  models.py    # PolicyInput / PolicyDecision / RemedyDecision / Clause
  engine.py    # PolicyEngine.decide()：匹配 → 排除 → 补救项判定 → 跨区域 → 缺输入
  loader.py    # config/policy/*.yaml 加载、校验（条款引用必须存在、优先级唯一）、mtime 热加载
  fault_class.py  # 从 diagnose_outcome / risk_cases / steps_executed 推导 fault_class（确定性）
config/policy/
  warranty_policy.yaml   # 演示规则（标 source: demo，待真实 SOP 替换）
  clauses.yaml           # 条款文本库（clause_id → text, source_doc, doc_version）
  regions.yaml           # 区域/渠道/平台枚举与别名（CN/EU/UK/US…；official_store/amazon/authorized_dealer/unauthorized）
```

## 2. 输入
```python
class PolicyInput(Strict):
    sku: str | None; category: str
    region_purchase: str | None; region_use: str | None
    channel: str | None; platform: str | None
    purchase_date: date | None
    receipt_status: ReceiptStatus
    dealer_authorized: bool | None
    fault_class: Literal["quality", "user_damage", "safety", "unknown"]
    prior_remedies: list[str]        # 本 case 已执行/已批准的补救项
    today: date
```
来源映射：sku / category ← product_confirmed；region / channel / platform ← `service_context`（凭证事实优先，用户确认卡次之）；purchase_date / receipt_status / dealer_authorized ← receipt；fault_class ← `fault_class.py`：R4 risk reported → safety；diagnose_outcome=evidence 且计划为品质类 → quality；步骤备注 / 事实含「摔 / 进水 / 宠物咬」等用户损坏词表 → user_damage；否则 unknown。

## 3. 规则格式（`warranty_policy.yaml`）
```yaml
version: 2026-09-14.1
source: demo   # 待真实 SOP 替换
policies:
  - policy_id: cn_robot_vacuum_standard
    priority: 10
    applies_to: {category: robot_vacuum, region_purchase: [CN], channel: [official_store, platform_store, authorized_dealer]}
    warranty_months: 12
    remedies:
      - {remedy: repair,  when: {fault_class: [quality], within_warranty: true}, cost_bearer: company, auto_allowed: true,  clauses: [CN-W-3.1]}
      - {remedy: replace, when: {fault_class: [quality], within_warranty: true, days_since_purchase_lte: 365, not_prior: [replace]}, cost_bearer: company, auto_allowed: true, clauses: [CN-W-3.2]}
      - {remedy: refund,  when: {fault_class: [quality], days_since_purchase_lte: 7}, cost_bearer: company, auto_allowed: false, clauses: [CN-W-3.3]}
      - {remedy: repair,  when: {fault_class: [quality], within_warranty: false}, cost_bearer: customer, auto_allowed: false, clauses: [CN-W-4.1]}
    exclusions:
      - {when: {fault_class: [user_damage]}, effect: no_free_remedy, clauses: [CN-W-5.1]}
      - {when: {channel: [unauthorized_dealer]}, effect: needs_human, clauses: [CN-W-2.2]}
      - {when: {fault_class: [safety]}, effect: needs_human, clauses: [CN-S-1.1]}   # 安全类一律人工
    cross_region:
      - {when: {region_use_not_in: [CN]}, effect: needs_human, clauses: [CN-W-6.1]}
  - policy_id: eu_robot_vacuum_standard
    priority: 10
    applies_to: {category: robot_vacuum, region_purchase: [DE, FR, IT, ES, NL], channel: [official_store, platform_store, authorized_dealer]}
    warranty_months: 24
    remedies: [...]
    cross_region:
      - {when: {region_use_in: [DE, FR, IT, ES, NL]}, effect: allow}          # 欧盟内互认
      - {when: {region_use_not_in: [DE, FR, IT, ES, NL]}, effect: needs_human, clauses: [EU-W-6.1]}
  - policy_id: uk_robot_vacuum_standard
    applies_to: {region_purchase: [UK], ...}
    cross_region:
      - {when: {region_use_not_in: [UK]}, effect: needs_human, clauses: [UK-W-6.1]}   # A6：UK 购 DE 用
defaults:
  no_policy_matched: needs_human
  missing_inputs: needs_human      # 缺 region/channel 时不猜
```
校验（loader）：所有 `clauses` 必须在 clauses.yaml；同一 `applies_to` 交叠时 priority 必须不同；`auto_allowed: true` 的 remedy 必须 `cost_bearer: company`（演示保守）；`refund` 一律 `auto_allowed: false`（D-L3-9 P0 不做退款自动执行）。

## 4. 输出
```python
class RemedyDecision(Strict):
    remedy: Literal["repair","replace","refund","none"]
    eligible: bool; auto_allowed: bool
    cost_bearer: Literal["company","customer","shared"] | None
    conditions: list[{name, expected, actual, met}]     # 可解释：每个 when 条件的实际取值
    clauses: list[Clause]                                # {clause_id, text, source_doc, doc_version}

class PolicyDecision(Strict):
    policy_id: str | None; policy_version: str
    matched: bool; within_warranty: bool | None; warranty_end: date | None
    fault_class: str
    remedies: list[RemedyDecision]
    exclusions_hit: list[{effect, clauses}]
    needs_human: bool; needs_human_reasons: list[str]
    missing_inputs: list[str]                            # → service_context 追问
    trace_id: str                                        # 与 retrieval_trace 同级，进 observability
```
判定顺序：缺输入 → 匹配 policy（priority 高者胜）→ 排除项（needs_human 立即；no_free_remedy 把 company 承担的 remedy 置 eligible=false）→ 逐 remedy 评 when → 跨区域 → 汇总 needs_human。全过程无副作用，`decide(input)` 可离线重放。

## 5. 接线
- `service_context` 节点先调 `decide()` 只看 `missing_inputs` 决定要不要发 ContextCard。
- `propose` 节点用 `remedies` 中 `eligible` 的项生成方案卡；`needs_human` → `await_human` 并把 decision 放进案件与摘要。
- `warranty.check` 只读动作：回答「保修至 {warranty_end}，可享 {eligible remedies}」+ 条款。
- `authorize` 门的第一项检查读 `auto_allowed`。
- 摘要（HITL 视图）展示 `conditions` 表格与 `clauses`，人工可覆盖（记录为 human_decision.override_reason）。

## 6. 政策文本进知识库（可选，P1）
条款文本按 `clauses.yaml` 同步导入 WeKnora 新库 `kb_policy`（front-matter：`doc_id=policy_{policy_id}`, `scope=category_generic`, 额外标量 `region_list`, `channel_list`, `policy_version`），供用户「保修政策是什么」这类咨询检索并引用；但**判定永远走引擎不走检索**。

## 7. SOP → 规则的工作流（真实 SOP 到手后）
1. 业务侧 SOP 文档 → 人工/半自动抽成 policies + clauses 草稿（LLM 可辅助抽取，输出必须经人工审核）。
2. `haike-policy lint` 校验 + `haike-policy explain --case cases.yaml` 打印每条评测样例的判定与条款。
3. 决策表测试 `data/eval/policy/cases.yaml`（输入 → 期望 remedies/needs_human）全绿后随 release 冻结 `policy_version`。
4. RELEASE.md 增加 policy_version；回放包版本四元组扩为五元组。

## 8. 测试
- 决策表 pytest（≥ 40 组：区域 × 渠道 × 故障定性 × 保内外 × 已补救）。
- 属性测试：`auto_allowed ⇒ eligible ∧ cost_bearer=company`；`needs_human ⇒ 所有 remedy auto_allowed=false`。
- 缺输入不猜：`region_purchase=None ⇒ missing_inputs 非空 ∧ needs_human`。
