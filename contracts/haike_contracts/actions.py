"""动作协议：POST /sessions/{id}/actions（08 §4）。"""

from __future__ import annotations

from typing import Annotated, Literal, get_args

from pydantic import Field, TypeAdapter

from haike_contracts.common import Feedback, ReceiptFields, Strict

ActionKind = Literal[
    "select_product",
    "step_feedback",
    "confirm_receipt",
    "skip_receipt",
    "request_human",
    "rediagnose",
]


class SelectProductPayload(Strict):
    sku: str


class StepFeedbackPayload(Strict):
    feedback: Feedback
    note: str | None = None


class ConfirmReceiptPayload(Strict):
    fields: ReceiptFields
    edited: list[Literal["order_no", "channel", "purchase_date", "amount"]] = Field(
        default_factory=list
    )


class SkipReceiptPayload(Strict):
    reason: Literal["none", "unreadable", "later"]


class RequestHumanPayload(Strict):
    pass


class RediagnosePayload(Strict):
    text: str | None = None
    image_ids: list[str] = Field(default_factory=list)


class _Action(Strict):
    action_id: str = Field(description="前端生成的 uuid，重试时复用，服务端据此幂等")
    expected_version: int = Field(ge=0)


class _CardAction(_Action):
    """针对卡片的动作：必须带 interrupt_id 与 card_id，与当前 pending_input 一致。"""

    interrupt_id: str
    card_id: str


class SelectProductAction(_CardAction):
    kind: Literal["select_product"]
    payload: SelectProductPayload


class StepFeedbackAction(_CardAction):
    kind: Literal["step_feedback"]
    payload: StepFeedbackPayload


class ConfirmReceiptAction(_CardAction):
    kind: Literal["confirm_receipt"]
    payload: ConfirmReceiptPayload


class SkipReceiptAction(_CardAction):
    kind: Literal["skip_receipt"]
    payload: SkipReceiptPayload


class RequestHumanAction(_Action):
    """任何时刻可用；服务端忽略 version 与 pending 校验，有 active run 先取消。"""

    kind: Literal["request_human"]
    interrupt_id: str | None = None
    card_id: str | None = None
    payload: RequestHumanPayload = Field(default_factory=RequestHumanPayload)


class RediagnoseAction(_Action):
    """guide / verify 阶段且无 active run；无绑定卡片。"""

    kind: Literal["rediagnose"]
    interrupt_id: str | None = None
    card_id: str | None = None
    payload: RediagnosePayload


ActionRequest = Annotated[
    SelectProductAction
    | StepFeedbackAction
    | ConfirmReceiptAction
    | SkipReceiptAction
    | RequestHumanAction
    | RediagnoseAction,
    Field(discriminator="kind"),
]

ActionRequestAdapter: TypeAdapter = TypeAdapter(ActionRequest)

ACTION_KINDS: tuple[str, ...] = get_args(ActionKind)


class ActionResult(Strict):
    """写入 session_actions.result_json 并在幂等重放时返回。"""

    action_id: str
    run_id: str
    replayed: bool = False
    version_after: int | None = Field(default=None, ge=0)


class ActionConflict(Strict):
    """409 响应体：附最新快照供前端重建（08 §4 第 3 步）。"""

    code: Literal["version_mismatch", "stale_card", "not_allowed_now", "run_active"]
    message: str
    snapshot: dict = Field(description="SessionSnapshot 序列化结果；此处用 dict 避免循环引用")


def parse_action(data: dict) -> ActionRequest:
    return ActionRequestAdapter.validate_python(data)
