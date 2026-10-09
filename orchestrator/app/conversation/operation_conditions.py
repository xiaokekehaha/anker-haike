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
RESOURCE_SIGNALS: dict[OperationSignal, tuple[str, bool]] = {
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
    # 就该资源追问过的那一轮 input_id：资源恢复时清掉，同一次缺失不反复追问。
    resource_asks: dict[str, str] = Field(default_factory=dict)
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


def has_operation_context(state: dict) -> bool:
    """真的处在操作过程中才让确定性的操作短语抢在语义理解之前。

    issue 每轮都会写回完整的 operation_conditions，所以"字典非空"恒为真，不能当作判据：
    会话 0f8809 里它让「设备不在身边」这句判别题的答案永远走不到问题受理。
    """
    conditions = conditions_for(state)
    return bool(
        conditions.paused
        or conditions.resources
        or conditions.blockers
        or state.get("plan_cursor")
        or state.get("steps_executed")
    )


def explicit_operation_reply(text: str) -> OperationUpdate | None:
    """Exact choices work without a model. Other wording uses quoted semantic extraction."""
    phrase = text.strip(" \n。！!，,")
    resource_choices = {
        "设备不在身边": "device_missing",
        "设备不在手边": "device_missing",
        # pause_text / resource_recheck 邀请用户"拿到设备后告诉我"，这些说法必须真的能解除限制
        "设备现在在身边": "device_ready", "设备在身边了": "device_ready",
        "设备拿到了": "device_ready",
        "拿到设备了": "device_ready", "设备到手了": "device_ready", "设备在手边了": "device_ready",
        "没有刷子": "tool_missing", "没有工具": "tool_missing",
        "缺少工具": "tool_missing", "工具准备好了": "tool_ready",
        "没有备用线": "cable_missing", "没有另一台设备": "spare_missing",
        "有备用线了": "cable_ready", "买到线了": "cable_ready",
        "有另一台设备了": "spare_ready", "有充电器了": "charger_ready",
        # 英文说法：下面的复核问题会原样请客户回复这些短语（D2 2026-10-08 客户可见文字改英文）
        "device not with me": "device_missing", "i have the device now": "device_ready",
        "no tools": "tool_missing", "tools ready": "tool_ready",
        "no spare cable": "cable_missing", "i have a spare cable": "cable_ready",
        "no other device": "spare_missing", "i have another device": "spare_ready", "i have a charger": "charger_ready",
    }
    key = phrase.casefold()
    if key in resource_choices:
        return OperationUpdate(signal=resource_choices[key], quote=text)
    if key in {"暂停排查", "不想继续", "暂时不想继续", "先不查了", "pause", "pause troubleshooting", "stop for now"}:
        return OperationUpdate(signal="pause", quote=text)
    if key in {"继续排查", "继续排障", "continue", "continue troubleshooting"}:
        return OperationUpdate(signal="continue", quote=text)
    if key in {"现在可以做了", "现在可以操作了", "重试这一步", "retry this step", "i can do it now"}:
        return OperationUpdate(signal="retry", quote=text)
    if key in {"不会操作", "不知道怎么做", "i don't know how", "i don't know how to do it"}:
        return OperationUpdate(signal="explain", quote=text)
    if key in {"跳过这步", "只跳过这一步", "skip this step"}:
        return OperationUpdate(signal="skip", quote=text)
    return None


def resolve_operation_reply(text: str, state: dict) -> tuple[OperationUpdate | None, str | None]:
    """把省略对象的资源短答绑定到当前问题；没有唯一对象时返回澄清。"""
    explicit = explicit_operation_reply(text)
    if explicit is not None or text.strip(" \n。！!，,").casefold() not in {"拿到了", "已经拿到了", "got it", "i have it now"}:
        return explicit, None
    if not has_operation_context(state):
        return None, None
    conditions = conditions_for(state)
    action = state.get("next_action") or {}
    question = action.get("question") or {}
    resource = None
    if (action.get("kind") == "ask" and question.get("kind") == "operation_blocker"
            and action.get("issue_id") in {None, state.get("active_issue_id") or state.get("issue_id")}):
        resource = question.get("resource")
    if resource is None:
        missing = [name for name, available in conditions.resources.items() if available is False]
        if len(missing) == 1:
            resource = missing[0]
    for signal, (name, available) in RESOURCE_SIGNALS.items():
        if name == resource and available:
            return OperationUpdate(signal=signal, quote=text), None
    return None, "Which one do you have now: the device, the cleaning tool, a spare cable, another device, or a charger?"


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
        if available:
            # 资源回来了：下次再缺同一件东西时仍然可以追问一次
            conditions.resource_asks.pop(resource, None)
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
        "question": "Let's hold this step. Is the device not with you, are you missing a tool, unsure how to do it, or would you like to pause?",
    }


# 资源缺失导致暂停时的复核问题。每句都给出一个 explicit_operation_reply 真的认得的回复说法：
# 邀请用户"拿到设备后告诉我"却听不懂他的回答，会话就再也走不出去（会话 0f8809）。
RESOURCE_RECHECK = {
    "device": "Do you have the device with you now? If so, reply \"I have the device now\" and I'll continue from where we left off; otherwise I can prepare a summary.",
    "cleaning_tool": "Are the cleaning tools ready? If so, reply \"tools ready\" and I'll give the next step; otherwise I can prepare a summary.",
    "spare_cable": "Do you have a spare cable now? If so, reply \"I have a spare cable\" and I'll give the next step; otherwise I can prepare a summary.",
    "spare_device": "Do you have another device to cross-test with? If so, reply \"I have another device\"; otherwise I can prepare a summary.",
    "charger": "Do you have a spare charger now? If so, reply \"I have a charger\"; otherwise I can prepare a summary.",
}


def resource_recheck(state: dict) -> dict | None:
    """资源缺失挡住全部动作时再问一次，而不是逐轮重复同一段暂停文案。

    声明当轮先如实答复（那一轮 resource_sources 记的就是当前 input_id），之后才追问；
    同一次缺失只追问一次；来源未知的历史状态不追问——无法判断用户是否已经被告知过。
    """
    conditions = conditions_for(state)
    if conditions.paused:
        return None
    resource = next(
        (
            name
            for name, available in conditions.resources.items()
            if available is False
            and name in RESOURCE_RECHECK
            and name not in conditions.resource_asks
            and conditions.resource_sources.get(name) not in {None, state.get("input_id")}
        ),
        None,
    )
    if resource is None:
        return None
    return {"kind": "operation_blocker", "resource": resource, "question": RESOURCE_RECHECK[resource]}


def pause_text(state: dict) -> str:
    conditions = conditions_for(state)
    if conditions.paused:
        return "Troubleshooting is paused; everything reported and tried is kept. Say \"continue\" when you're ready, or I can prepare a summary for our support team."
    if conditions.resources.get("device") is False:
        return "Noted that the device isn't with you, so no hands-on steps for now. When you have it, reply \"I have the device now\" and I'll continue; or I can prepare a summary."
    return "I can't confirm the cause yet, so I won't add more steps for now. Everything so far is kept; we can continue when you're ready, or I can prepare a summary for our support team."
