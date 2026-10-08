"""动作协议：POST /sessions/{id}/actions（08 §4）。"""

from __future__ import annotations

from typing import Annotated, Literal, get_args

from pydantic import Field, TypeAdapter

from haike_contracts.common import Feedback, ObservationAnswer, ReceiptFields, Strict

ActionKind = Literal[
    "select_product",
    "step_feedback",
    "answer_observation",
    "confirm_receipt",
    "skip_receipt",
    "request_human",
    "new_issue",
    "resume_issue",
    "confirm_proposal",
    "decline_proposal",
    "skip_retake",
    "rate_satisfaction",
]


class SelectProductPayload(Strict):
    # None = 「其他型号 / 不确定」：只在 allow_unknown 的卡片上合法，服务端退回 category_only
    sku: str | None


class StepFeedbackPayload(Strict):
    feedback: Feedback
    note: str | None = None
    # 步骤声明了 observations 时可携带的检查结果；未携带保持 unknown，不会被写成阴性
    observations: list[ObservationAnswer] = Field(default_factory=list)


class AnswerObservationPayload(Strict):
    """observation_card 的作答；option_id 必须是该卡声明过的选项。
    kind=unknown 的选项记为「答不上来」，不写成观察事实。"""

    observation_id: str
    option_id: str


class ConfirmReceiptPayload(Strict):
    fields: ReceiptFields
    edited: list[Literal["order_no", "seller", "country", "purchase_date", "amount"]] = Field(
        default_factory=list
    )


class SkipReceiptPayload(Strict):
    reason: Literal["none", "unreadable", "later"]


class RequestHumanPayload(Strict):
    pass


class _Action(Strict):
    action_id: str = Field(description="前端生成的 uuid，重试时复用，服务端据此幂等")
    expected_version: int = Field(ge=0)
    target_issue_id: str | None = None


class _CardAction(_Action):
    """针对卡片的动作：必须带 input_token 与 card_id，与当前 pending_input 一致。"""

    target_issue_id: str
    input_token: str
    card_id: str


class SelectProductAction(_CardAction):
    kind: Literal["select_product"]
    payload: SelectProductPayload


class StepFeedbackAction(_CardAction):
    kind: Literal["step_feedback"]
    payload: StepFeedbackPayload


class AnswerObservationAction(_CardAction):
    kind: Literal["answer_observation"]
    payload: AnswerObservationPayload


class ConfirmReceiptAction(_CardAction):
    kind: Literal["confirm_receipt"]
    payload: ConfirmReceiptPayload


class SkipReceiptAction(_CardAction):
    kind: Literal["skip_receipt"]
    payload: SkipReceiptPayload


class RequestHumanAction(_Action):
    """任何时刻可用；服务端忽略 version 与 pending 校验，有 active run 先取消。"""

    kind: Literal["request_human"]
    input_token: str | None = None
    card_id: str | None = None
    payload: RequestHumanPayload = Field(default_factory=RequestHumanPayload)


class NewIssueAction(_Action):
    target_issue_id: None = None
    kind: Literal["new_issue"]
    payload: RequestHumanPayload = Field(default_factory=RequestHumanPayload)


class ResumeIssueAction(_Action):
    kind: Literal["resume_issue"]
    target_issue_id: str
    payload: RequestHumanPayload = Field(default_factory=RequestHumanPayload)


class ConfirmProposalPayload(Strict):
    option_id: str


class ConfirmProposalAction(_CardAction):
    kind: Literal["confirm_proposal"]
    payload: ConfirmProposalPayload


class DeclineProposalPayload(Strict):
    reason: Literal["want_other", "not_now", "request_human"]


class DeclineProposalAction(_CardAction):
    kind: Literal["decline_proposal"]
    payload: DeclineProposalPayload


class SkipRetakePayload(Strict):
    reason: str = "skip"


class SkipRetakeAction(_CardAction):
    kind: Literal["skip_retake"]
    payload: SkipRetakePayload


class RateSatisfactionPayload(Strict):
    score: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class RateSatisfactionAction(_CardAction):
    kind: Literal["rate_satisfaction"]
    payload: RateSatisfactionPayload


ActionRequest = Annotated[
    SelectProductAction
    | StepFeedbackAction
    | AnswerObservationAction
    | ConfirmReceiptAction
    | SkipReceiptAction
    | RequestHumanAction
    | NewIssueAction
    | ResumeIssueAction
    | ConfirmProposalAction
    | DeclineProposalAction
    | SkipRetakeAction
    | RateSatisfactionAction,
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

    code: Literal["stale_version", "stale_card", "not_allowed_now", "run_active"]
    """stale_version：expected_version 不符；stale_card：input_token / card_id 过期；
    not_allowed_now：kind 不在允许时机；run_active：会话有进行中的 run（票 23，08 §4 步骤 3）。"""
    message: str
    snapshot: dict = Field(description="SessionSnapshot 序列化结果；此处用 dict 避免循环引用")


def parse_action(data: dict) -> ActionRequest:
    return ActionRequestAdapter.validate_python(data)
