"""事件、动作、快照共用的枚举与小对象。"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    """所有契约模型的基类：拒绝未知字段，保证前后端漂移能被测试与 Schema 比对发现。"""

    model_config = ConfigDict(extra="forbid")


Stage = Literal[
    "intake",
    "disambiguate",
    "out_of_scope",
    "diagnose",
    "guide",
    "verify",
    "escalate",
    "done",
    "consult",
    "context",
    "propose",
    "execute",
    "track",
    "awaiting_human",
]
"""状态机阶段（02 §3）。前端 ProgressBar 把八个阶段折叠为五段展示。"""

EscalateSubstage = Literal["collect_receipt", "extract", "confirm_fields", "lookup", "summarize"]

PendingKind = Literal[
    "select_product",
    "step_feedback",
    "upload_receipt",
    "confirm_receipt",
    "confirm_context",
    "confirm_proposal",
    "upload_retake",
    "rate_satisfaction",
]

Feedback = Literal["solved", "not_solved", "cannot_do"]

ProductState = Literal["confirmed_sku", "category_only", "unknown"]

ReceiptStatus = Literal[
    "not_collected",
    "insufficient",
    "order_verified",
    "order_product_mismatch",
    "needs_manual_check",
    "channel_in_directory",
    "channel_unknown",
]

EmotionLevel = Literal["calm", "anxious", "dissatisfied", "angry", "complaint_risk"]
EmotionStrategy = Literal[
    "normal",
    "reassure_first",
    "reassure_and_shorten",
    "direct_resolution",
    "de_escalate_and_offer_human",
]

ModelTier = Literal["primary", "fallback"]


class PendingInput(Strict):
    issue_id: str | None = None
    """当前唯一允许的用户输入；与 awaiting_input 事件同结构（08 §1、§6）。"""

    kind: PendingKind
    input_token: str
    card_id: str
    version: int = Field(ge=0)


class Emotion(Strict):
    level: EmotionLevel
    strategy: EmotionStrategy


class ProductCandidate(Strict):
    sku: str
    name: str
    category: str
    image: str | None = None
    in_scope: bool


class TroubleshootStep(Strict):
    """step_card 的唯一层级：step 对象（08 §5）。"""

    step_id: str
    plan_id: str
    plan_version: int = Field(ge=1)
    step_no: int = Field(ge=1)
    title: str
    instruction: str
    expected_result: str
    caution: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class EvidenceItem(Strict):
    evidence_id: str
    source: str
    doc_id: str
    doc_version: str
    chunk_id: str
    snippet: str
    score: float = Field(ge=0, le=1)
    status: Literal["ok", "replay"] = "ok"


class ReceiptFields(Strict):
    order_no: str | None = None
    channel: str | None = None
    purchase_date: str | None = None
    amount: str | None = None


class ReceiptOutcome(Strict):
    """凭证核对结果：只有已核实事实与下一步，不含质保资格结论（D16，09 §5.2）。"""

    status: ReceiptStatus
    verified_facts: dict[str, str] = Field(default_factory=dict)
    conflicts: list[str] = Field(default_factory=list)
    next_step: str | None = None


class ExecutedStep(Strict):
    step_id: str
    title: str
    feedback: Feedback


class EscalationReason(Strict):
    rule_id: str
    text: str


class ModelTraceItem(Strict):
    task: str
    model_used: str
    lane: str
    attempts: int = Field(ge=1)


class Clause(Strict):
    clause_id: str
    text: str
    source_doc: str = "演示政策，待真实 SOP 替换"
    doc_version: str
    policy_version: str


class PolicyCondition(Strict):
    name: str
    expected: Any
    actual: Any
    met: bool


class RemedyDecision(Strict):
    remedy: Literal["repair", "replace", "refund", "none"]
    eligible: bool
    auto_allowed: bool
    cost_bearer: Literal["company", "customer", "shared"] | None = None
    conditions: list[PolicyCondition] = Field(default_factory=list)
    clauses: list[Clause] = Field(default_factory=list)


class PolicyDecision(Strict):
    policy_id: str | None = None
    policy_version: str
    matched: bool = False
    within_warranty: bool | None = None
    warranty_end: date | None = None
    fault_class: Literal["quality", "user_damage", "safety", "unknown"]
    remedies: list[RemedyDecision] = Field(default_factory=list)
    exclusions_hit: list[dict] = Field(default_factory=list)
    needs_human: bool = False
    needs_human_reasons: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    trace_id: str


class DispatchEstimate(Strict):
    working_days: int = Field(gt=0)
    action: Literal["replacement.create"] = "replacement.create"
    actions_version: str


class ProposalOption(Strict):
    option_id: str
    remedy: Literal["repair", "replace", "refund", "none"]
    title: str
    cost_bearer: Literal["company", "customer", "shared"] | None = None
    conditions: list[PolicyCondition] = Field(default_factory=list)
    clauses: list[Clause] = Field(default_factory=list)
    auto_allowed: bool = False
    source: Literal["policy", "human"] = "policy"
    dispatch_estimate: DispatchEstimate | None = None


class GateCheck(Strict):
    name: str
    passed: bool
    detail: str


class GateResult(Strict):
    passed: bool
    checks: list[GateCheck]
    fallback: Literal["await_human", "summarize"] | None = None


class Receipt(Strict):
    status: str
    service_order_no: str | None = None
    tracking_no: str | None = None
    order_no: str | None = None
    eta_days: int | None = None
    next_step: str = ""
    updated_at: str | None = None
    source: str = "业务系统（模拟）"
    data: dict = Field(default_factory=dict)


class Finding(Strict):
    part: str
    location: str | None = None
    phenomenon: str
    severity: Literal["low", "medium", "high"]
    confidence: float = Field(ge=0, le=1)
    quote_region: str | None = None
    raw: dict[str, str] = Field(default_factory=dict)


class ImageQuality(Strict):
    usable: bool
    reasons: list[Literal["blurry", "too_dark", "too_far", "wrong_subject", "occluded"]] = Field(default_factory=list)
    guidance: list[str] = Field(default_factory=list)


class FaultLocalization(Strict):
    findings: list[Finding] = Field(default_factory=list)
    image_quality: ImageQuality = Field(default_factory=lambda: ImageQuality(usable=True))
    model_hint: str | None = None
    conflicts_with_text: list[str] = Field(default_factory=list)


CaseStatus = Literal[
    "open",
    "diagnosing",
    "proposing",
    "awaiting_confirmation",
    "executing",
    "executing_failed",
    "tracking",
    "closed",
    "awaiting_approval",
    "approved",
    "rejected",
    "closed_unresolved",
    "reopened",
    "escalated_summary",
]


class EscalationSummary(Strict):
    """escalation_summary 的唯一层级：summary 对象（08 §5）。"""

    product: str
    problem: str
    observations: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    steps: list[ExecutedStep] = Field(default_factory=list)
    reason: EscalationReason
    emotion: Emotion
    receipt: ReceiptOutcome
    model_trace: list[ModelTraceItem] = Field(default_factory=list)
    case_id: str | None = None
    policy_decision_brief: dict | None = None
    recommended_options: list[ProposalOption] = Field(default_factory=list)
    gate_result: GateResult | None = None
    task_queue: list[dict] = Field(default_factory=list)
    emotion_track: list[dict] = Field(default_factory=list)
    draft_reply: str | None = None
