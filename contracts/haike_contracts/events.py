"""SSE 事件协议（08 §5），15 种 type 的唯一定义。"""

from __future__ import annotations

from typing import Annotated, Literal, get_args

from pydantic import Field, TypeAdapter

from haike_contracts.common import (
    EscalationSummary,
    CaseStatus as CaseStatusValue,
    ProposalOption,
    Receipt,
    EvidenceItem,
    ModelTier,
    PendingKind,
    ProductCandidate,
    ReceiptFields,
    Stage,
    Strict,
    TroubleshootStep,
)


class _Event(Strict):
    seq: int = Field(ge=1, description="会话内单调递增")
    run_id: str
    event_id: str
    recorded_at: str


class InputReceived(_Event):
    type: Literal["input_received"]
    input_id: str
    input_kind: Literal["message", "action", "human_decision"]
    payload: dict
    issue_id: str | None = None


class IssueChanged(_Event):
    type: Literal["issue_changed"]
    active_issue_id: str
    issues: list[dict]
    input_id: str
    resolved_issue_id: str
    version: int = Field(ge=0)


class PendingChanged(_Event):
    type: Literal["pending_changed"]
    issue_id: str
    pending_id: str
    status: Literal["active", "suspended", "consumed", "invalidated"]
    reason: str
    superseded_by: str | None = None
    version: int = Field(ge=0)


class SummaryUpdated(_Event):
    type: Literal["summary_updated"]
    issue_id: str
    summary_id: str
    revision: int = Field(ge=1)
    card_id: str
    previous_card_id: str | None = None
    source_through_seq: int
    updated_at: str


class RunStarted(_Event):
    type: Literal["run_started"]
    resumed: bool
    deadline_ms: int = Field(
        gt=0, description="本 run 故障时的最大总时长；前端硬上限 = deadline + 5 s"
    )


class Ping(_Event):
    type: Literal["ping"]


class Progress(_Event):
    type: Literal["progress"]
    stage: Stage
    substage: str | None = None


class ToolCall(_Event):
    type: Literal["tool_call"]
    tool_id: str
    name: str
    status: Literal["started", "finished", "failed"]
    summary: str | None = None


class MessageStart(_Event):
    type: Literal["message_start"]
    message_id: str
    reply_to_input_id: str | None = None
    issue_id: str | None = None
    replaces: str | None = Field(default=None, description="替换先前中断的消息")


class Message(_Event):
    type: Literal["message"]
    message_id: str
    delta: str


class MessageEnd(_Event):
    type: Literal["message_end"]
    message_id: str
    status: Literal["completed", "aborted"]
    model_tier: ModelTier | None = None


class _Card(_Event):
    card_id: str
    issue_id: str | None = None
    version: int = Field(ge=0)


class ProductCard(_Card):
    type: Literal["product_card"]
    candidates: list[ProductCandidate] = Field(min_length=1)


class StepCard(_Card):
    type: Literal["step_card"]
    step: TroubleshootStep


class Evidence(_Event):
    type: Literal["evidence"]
    items: list[EvidenceItem]


class ReceiptCard(_Card):
    type: Literal["receipt_card"]
    fields: ReceiptFields
    confidence: dict[str, float] = Field(default_factory=dict)
    unreadable: list[str] = Field(default_factory=list)


class AwaitingInput(_Event):
    type: Literal["awaiting_input"]
    issue_id: str | None = None
    kind: PendingKind
    input_token: str
    card_id: str
    version: int = Field(ge=0)


class EscalationSummaryEvent(_Event):
    type: Literal["escalation_summary"]
    card_id: str
    summary: EscalationSummary
    summary_id: str
    revision: int = Field(ge=1)
    issue_id: str
    updated_at: str
    source_through_seq: int
    previous_card_id: str | None = None
    handoff_status: Literal["prepared", "requested", "accepted", "failed", "cancelled"] = "prepared"


class Error(_Event):
    type: Literal["error"]
    code: str
    message: str
    recoverable: bool
    retry_with_same_action: bool = False


class Done(_Event):
    type: Literal["done"]
    reason: Literal["completed", "awaiting_input", "error", "cancelled"]
    version: int = Field(ge=0, description="本 run 结束后的会话版本")


class ContextCardEvent(_Card):
    type: Literal["context_card"]
    fields: list[str]
    prefilled: dict[str, str] = Field(default_factory=dict)
    sources: dict[str, str] = Field(default_factory=dict)
    choices: dict[str, list[str]] = Field(default_factory=dict)


class ProposalCardEvent(_Card):
    type: Literal["proposal_card"]
    options: list[ProposalOption]
    decision_summary: str
    policy_version: str
    retry: bool = False


class ExecutionCardEvent(_Card):
    type: Literal["execution_card"]
    execution_id: str
    action_kind: str
    status: Literal["succeeded", "failed"]
    receipt: Receipt
    idempotency_key: str


class RetakeCardEvent(_Card):
    type: Literal["retake_card"]
    reasons: list[str]
    guidance: list[str]


class RatingCardEvent(_Card):
    type: Literal["rating_card"]
    case_id: str | None = None


class CaseStatusEvent(_Card):
    type: Literal["case_changed"]
    case_id: str
    status: CaseStatusValue
    complaint_risk: bool = False
    priority: Literal["normal", "high"] = "normal"
    owner: str | None = None
    reason: str
    external_refs: dict[str, str] = Field(default_factory=dict)
    updated_at: str


ServerEvent = Annotated[
    RunStarted
    | InputReceived
    | IssueChanged
    | PendingChanged
    | SummaryUpdated
    | Ping
    | Progress
    | ToolCall
    | MessageStart
    | Message
    | MessageEnd
    | ProductCard
    | StepCard
    | Evidence
    | ReceiptCard
    | AwaitingInput
    | EscalationSummaryEvent
    | Error
    | Done
    | ContextCardEvent
    | ProposalCardEvent
    | ExecutionCardEvent
    | RetakeCardEvent
    | RatingCardEvent
    | CaseStatusEvent,
    Field(discriminator="type"),
]

ServerEventAdapter: TypeAdapter = TypeAdapter(ServerEvent)

EVENT_TYPES: tuple[str, ...] = tuple(
    get_args(m.model_fields["type"].annotation)[0] for m in get_args(get_args(ServerEvent)[0])
)


def parse_event(data: dict) -> ServerEvent:
    return ServerEventAdapter.validate_python(data)
