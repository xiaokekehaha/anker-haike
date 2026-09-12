"""SSE 事件协议（08 §5），15 种 type 的唯一定义。"""

from __future__ import annotations

from typing import Annotated, Literal, get_args

from pydantic import Field, TypeAdapter

from haike_contracts.common import (
    EscalationSummary,
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
    kind: PendingKind
    interrupt_id: str
    card_id: str
    version: int = Field(ge=0)


class EscalationSummaryEvent(_Event):
    type: Literal["escalation_summary"]
    card_id: str
    summary: EscalationSummary


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


ServerEvent = Annotated[
    RunStarted
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
    | Done,
    Field(discriminator="type"),
]

ServerEventAdapter: TypeAdapter = TypeAdapter(ServerEvent)

EVENT_TYPES: tuple[str, ...] = tuple(
    get_args(m.model_fields["type"].annotation)[0] for m in get_args(get_args(ServerEvent)[0])
)


def parse_event(data: dict) -> ServerEvent:
    return ServerEventAdapter.validate_python(data)
