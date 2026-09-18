"""Issue-local execution evidence and reversible operation constraints.

Feedback history is immutable evidence of what the user said. Only actual execution
deduplicates operations; temporary constraints are re-evaluated before selection and publication.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# One signal per turn keeps the interpret schema small and rules out contradictory
# combinations (pause + retry). Resource signals name the resource and whether it is at hand.
OperationSignal = Literal[
    "device_missing", "device_ready", "tool_missing", "tool_ready",
    "cable_missing", "cable_ready", "spare_missing", "spare_ready",
    "charger_missing", "charger_ready",
    "pause", "continue", "explain", "skip", "retry",
]
RESOURCE_SIGNALS: dict[str, tuple[str, bool]] = {
    "device_missing": ("device", False), "device_ready": ("device", True),
    "tool_missing": ("cleaning_tool", False), "tool_ready": ("cleaning_tool", True),
    "cable_missing": ("spare_cable", False), "cable_ready": ("spare_cable", True),
    "spare_missing": ("spare_device", False), "spare_ready": ("spare_device", True),
    "charger_missing": ("charger", False), "charger_ready": ("charger", True),
}
# retry / skip mean "keep going with this issue"; explain asks about the step without resuming.
RESUMING_SIGNALS = {"continue", "retry", "skip"}
# Consecutive skips since the last explicit "continue" stop the step loop. Reversible,
# unlike the executed-step limits in guide/verify.py.
BURDEN_SKIP_LIMIT = 3


class OperationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    signal: OperationSignal
    quote: str


class StepBlocker(BaseModel):
    plan_id: str
    step_id: str
    instruction_src: str
    card_id: str
    reason: Literal["unknown", "resource", "explain", "skip"] = "unknown"
    quote: str = ""
    resources: list[str] = Field(default_factory=list)
    asked: bool = False
    cleared: bool = False


class OperationConditions(BaseModel):
    paused: bool = False
    resources: dict[str, bool] = Field(default_factory=dict)
    resource_sources: dict[str, str] = Field(default_factory=dict)
    blockers: list[StepBlocker] = Field(default_factory=list)
    # A burden stop is reversible by an explicit request, without deleting historical counters.
    skip_baseline: int = 0
    continue_input_id: str | None = None


def feedback_history(state: dict) -> list[dict]:
    """Read historical snapshots by feedback semantics; never rewrite the original records."""
    history = list(state.get("step_attempts") or [])
    cards = {s.get("card_id") for s in history}
    return [*history, *(s for s in state.get("steps_executed") or [] if s.get("card_id") not in cards)]


def execution_history(state: dict) -> list[dict]:
    return [s for s in feedback_history(state) if s.get("feedback") in {"solved", "not_solved"}]


def conditions_for(state: dict) -> OperationConditions:
    conditions = OperationConditions.model_validate(state.get("operation_conditions") or {})
    recorded = {b.card_id for b in conditions.blockers}
    for attempt in feedback_history(state):
        if attempt.get("feedback") == "cannot_do" and attempt.get("card_id") not in recorded:
            conditions.blockers.append(StepBlocker(
                plan_id=attempt.get("plan_id", ""), step_id=attempt.get("step_id", ""),
                instruction_src=attempt.get("instruction_src", ""), card_id=attempt.get("card_id", ""),
                quote=attempt.get("note") or "",
            ))
    return conditions


def explicit_operation_reply(text: str) -> OperationUpdate | None:
    """Exact choices work without a model. Other wording uses quoted semantic extraction."""
    phrase = text.strip(" \n。！!，,")
    resource_choices = {
        "设备不在身边": "device_missing", "充电宝不在身边": "device_missing",
        "设备不在手边": "device_missing", "设备现在在身边": "device_ready",
        "没有刷子": "tool_missing", "没有工具": "tool_missing",
        "缺少工具": "tool_missing", "工具准备好了": "tool_ready",
        "没有备用线": "cable_missing", "没有另一台设备": "spare_missing",
    }
    if phrase in resource_choices:
        return OperationUpdate(signal=resource_choices[phrase], quote=text)
    if phrase in {"暂停排查", "不想继续", "暂时不想继续", "先不查了"}:
        return OperationUpdate(signal="pause", quote=text)
    if phrase in {"继续排查", "继续排障"}:
        return OperationUpdate(signal="continue", quote=text)
    if phrase in {"现在可以做了", "现在可以操作了", "重试这一步"}:
        return OperationUpdate(signal="retry", quote=text)
    if phrase in {"不会操作", "不知道怎么做"}:
        return OperationUpdate(signal="explain", quote=text)
    if phrase in {"跳过这步", "只跳过这一步"}:
        return OperationUpdate(signal="skip", quote=text)
    return None


def update_conditions(state: dict, proposal: OperationUpdate | None, *, text: str, input_id: str) -> tuple[dict, bool]:
    conditions = conditions_for(state)
    before = conditions.model_dump()
    # One turn carries one quote: nothing in an update applies unless that quote is in this text.
    if proposal is None or not (proposal.quote.strip() and proposal.quote in text):
        return before, False
    current = next((b for b in reversed(conditions.blockers) if not b.cleared), None)
    if proposal.signal in RESOURCE_SIGNALS:
        resource, available = RESOURCE_SIGNALS[proposal.signal]
        conditions.resources[resource] = available
        conditions.resource_sources[resource] = input_id
        if not available and current:
            current.reason = "resource"
            current.quote = proposal.quote
            current.resources = list(dict.fromkeys([*current.resources, resource]))
    for blocker in conditions.blockers:
        if blocker.reason == "resource" and blocker.resources and all(
            conditions.resources.get(r) is True for r in blocker.resources
        ):
            blocker.cleared = True
    if proposal.signal == "pause":
        conditions.paused = True
    elif proposal.signal in RESUMING_SIGNALS:
        conditions.paused = False
        conditions.skip_baseline = int((state.get("counters") or {}).get("skipped", 0))
        conditions.continue_input_id = input_id
    if current and proposal.signal in {"explain", "skip", "retry"}:
        if proposal.signal == "retry":
            # "Retry" only clears the selected blocker, never unrelated resource restrictions.
            if all(conditions.resources.get(r) is not False for r in current.resources):
                current.cleared = True
        else:
            current.reason = proposal.signal
            current.quote = proposal.quote
    return conditions.model_dump(), conditions.model_dump() != before


def step_unavailable(state: dict, plan_id: str, step) -> str | None:
    """Shared by action selection and the final publisher, including historical snapshots."""
    conditions = conditions_for(state)
    if conditions.paused:
        return "user_paused"
    if any(conditions.resources.get(r) is False for r in step.required_resources):
        return "resource_unavailable"
    if any(not b.cleared and (
        (b.plan_id == plan_id and b.step_id == step.step_id)
        or (b.instruction_src and b.instruction_src == step.instruction_src)
    ) for b in conditions.blockers):
        return "step_blocked"
    return None


def effective_exhausted(state: dict) -> set[str]:
    """A plan exhausted only by historical cannot_do records is still recoverable."""
    exhausted = set(state.get("exhausted_plans") or [])
    actual = {(s.get("plan_id"), s.get("step_id")) for s in execution_history(state)}
    for attempt in feedback_history(state):
        key = (attempt.get("plan_id"), attempt.get("step_id"))
        if attempt.get("feedback") == "cannot_do" and key not in actual:
            exhausted.discard(attempt.get("plan_id"))
    return exhausted


def support_question(state: dict) -> dict | None:
    conditions = conditions_for(state)
    blocker = next((b for b in reversed(conditions.blockers) if not b.cleared), None)
    if not blocker or blocker.reason != "unknown" or blocker.asked or conditions.paused:
        return None
    if conditions.continue_input_id and conditions.continue_input_id == state.get("input_id"):
        return None
    return {
        "kind": "operation_blocker", "card_id": blocker.card_id,
        "question": "这一步先不做。当前是设备不在身边、缺少工具、不知道怎么做，还是想暂停排查？",
    }


def pause_text(state: dict) -> str:
    conditions = conditions_for(state)
    if conditions.paused:
        return "已暂停排查，已有现象和操作记录会保留。准备好后可以要求继续；需要联系人工客服时，我可以整理问题摘要。"
    if conditions.resources.get("device") is False:
        return "已记下设备不在身边，先不安排读屏或动手操作。拿到设备后告诉我，再结合已有记录继续；也可以先整理问题摘要。"
    return "目前还不能确认故障原因，先不继续增加操作。已有现象和未执行的步骤都已保留；条件具备后可以继续，或要求整理给客服的问题摘要。"
