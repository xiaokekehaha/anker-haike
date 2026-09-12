"""事件、动作、快照共用的枚举与小对象。"""

from __future__ import annotations

from typing import Literal

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
]
"""状态机阶段（02 §3）。前端 ProgressBar 把八个阶段折叠为五段展示。"""

EscalateSubstage = Literal["collect_receipt", "extract", "confirm_fields", "lookup", "summarize"]

PendingKind = Literal["select_product", "step_feedback", "upload_receipt", "confirm_receipt"]

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

EmotionLevel = Literal["calm", "anxious", "angry"]
EmotionStrategy = Literal["normal", "reassure_first", "reassure_and_shorten"]

ModelTier = Literal["primary", "fallback"]


class PendingInput(Strict):
    """当前唯一允许的用户输入；与 awaiting_input 事件同结构（08 §1、§6）。"""

    kind: PendingKind
    interrupt_id: str
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
