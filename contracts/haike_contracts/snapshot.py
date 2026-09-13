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
    """最近一次运行留下的错误；更早 run 的错误不进快照（只在事件表里供审计）。"""

    code: str
    message: str = ""
    recoverable: bool = True
    at: str


class CancelledRun(Strict):
    run_id: str
    at: str


class ImageRefItem(Strict):
    """会话期图片引用（票 29）：只有引用与摘要，字节在 session_images，1 小时后清理。"""

    image_id: str
    purpose: Literal["fault", "receipt"]
    sha256: str
    mime: str
    size: int = Field(ge=0)


class TimelineRecord(Strict):
    at: str | None = None
    first_seq: int = 0
    last_seq: int = 0
    issue_id: str | None = None


class ActionItem(TimelineRecord):
    kind: Literal["action"]
    id: str
    label: str
    action_kind: str


class UserMessageItem(TimelineRecord):
    kind: Literal["user_message"]
    id: str
    text: str
    image_ids: list[str] = Field(default_factory=list)
    images: list[ImageRefItem] = Field(default_factory=list)
    at: str


class AssistantMessageItem(TimelineRecord):
    """message_start / message / message_end 折叠后的完整文本。"""

    kind: Literal["assistant_message"]
    message_id: str
    text: str
    status: Literal["completed", "aborted", "streaming", "replaced"]
    reply_to_input_id: str | None = None
    model_tier: ModelTier | None = None
    replaces: str | None = None


class ToolItem(TimelineRecord):
    kind: Literal["tool"]
    tool_id: str
    name: str
    status: Literal["started", "finished", "failed"]
    summary: str | None = None


class ProductCardItem(TimelineRecord):
    kind: Literal["product_card"]
    card_id: str
    version: int = Field(ge=0)
    candidates: list[ProductCandidate]
    selected_sku: str | None = Field(default=None, description="用户已选结果")


class StepCardItem(TimelineRecord):
    kind: Literal["step_card"]
    card_id: str
    version: int = Field(ge=0)
    step: TroubleshootStep
    feedback: Feedback | None = None
    note: str | None = None


class ReceiptCardItem(TimelineRecord):
    kind: Literal["receipt_card"]
    card_id: str
    version: int = Field(ge=0)
    fields: ReceiptFields
    confidence: dict[str, float] = Field(default_factory=dict)
    unreadable: list[str] = Field(default_factory=list)
    confirmed_fields: ReceiptFields | None = None
    skipped_reason: Literal["none", "unreadable", "later"] | None = None


class EvidenceItemGroup(TimelineRecord):
    kind: Literal["evidence"]
    items: list[EvidenceItem]


class SummaryItem(TimelineRecord):
    kind: Literal["escalation_summary"]
    card_id: str
    summary: EscalationSummary
    summary_id: str
    revision: int
    updated_at: str
    source_through_seq: int
    previous_card_id: str | None = None
    handoff_status: Literal["prepared", "requested", "accepted", "failed", "cancelled"] = "prepared"


TimelineItem = Annotated[
    UserMessageItem
    | ActionItem
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
    active_issue_id: str | None = None
    issues: list[dict] = Field(default_factory=list)
    last_event_seq: int = 0
    latest_summaries: list[SummaryItem] = Field(default_factory=list)
