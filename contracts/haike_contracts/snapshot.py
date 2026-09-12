"""快照协议：GET /sessions/{id}（08 §6）。"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from haike_contracts.common import (
    EscalationSummary,
    EvidenceItem,
    Feedback,
    ModelTier,
    PendingInput,
    ProductCandidate,
    ReceiptFields,
    Stage,
    Strict,
    TroubleshootStep,
)


class ActiveRun(Strict):
    run_id: str
    started_at: str
    deadline_at: str


class LastError(Strict):
    code: str
    at: str


class CancelledRun(Strict):
    run_id: str
    at: str


class UserMessageItem(Strict):
    kind: Literal["user_message"]
    id: str
    text: str
    image_ids: list[str] = Field(default_factory=list)
    at: str


class AssistantMessageItem(Strict):
    """message_start / message / message_end 折叠后的完整文本。"""

    kind: Literal["assistant_message"]
    message_id: str
    text: str
    status: Literal["completed", "aborted", "streaming"]
    model_tier: ModelTier | None = None
    replaces: str | None = None


class ToolItem(Strict):
    kind: Literal["tool"]
    tool_id: str
    name: str
    status: Literal["started", "finished", "failed"]
    summary: str | None = None


class ProductCardItem(Strict):
    kind: Literal["product_card"]
    card_id: str
    version: int = Field(ge=0)
    candidates: list[ProductCandidate]
    selected_sku: str | None = Field(default=None, description="用户已选结果")


class StepCardItem(Strict):
    kind: Literal["step_card"]
    card_id: str
    version: int = Field(ge=0)
    step: TroubleshootStep
    feedback: Feedback | None = None
    note: str | None = None


class ReceiptCardItem(Strict):
    kind: Literal["receipt_card"]
    card_id: str
    version: int = Field(ge=0)
    fields: ReceiptFields
    confidence: dict[str, float] = Field(default_factory=dict)
    unreadable: list[str] = Field(default_factory=list)
    confirmed_fields: ReceiptFields | None = None
    skipped_reason: Literal["none", "unreadable", "later"] | None = None


class EvidenceItemGroup(Strict):
    kind: Literal["evidence"]
    items: list[EvidenceItem]


class SummaryItem(Strict):
    kind: Literal["escalation_summary"]
    card_id: str
    summary: EscalationSummary


TimelineItem = Annotated[
    UserMessageItem
    | AssistantMessageItem
    | ToolItem
    | ProductCardItem
    | StepCardItem
    | ReceiptCardItem
    | EvidenceItemGroup
    | SummaryItem,
    Field(discriminator="kind"),
]


class SessionSnapshot(Strict):
    session_id: str
    version: int = Field(ge=0)
    stage: Stage
    substage: str | None = None
    active_run: ActiveRun | None = None
    pending_input: PendingInput | None = None
    timeline: list[TimelineItem] = Field(default_factory=list)
    last_error: LastError | None = None
    cancelled_run: CancelledRun | None = None
