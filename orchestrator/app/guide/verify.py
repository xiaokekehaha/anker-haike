"""反馈推进（票 35；03 §1.6、09 §3.3–§3.4）：无 LLM。

solved → 结束；not_solved → executed+1、advanced+1；cannot_do → skipped+1（不计 executed）。
cannot_do 记录阻碍并返回 reassess；真实执行后按 next_on 推进。EXHAUSTED 只标记计划耗尽，
下一动作由 diagnose.decision.decide_next 依据更新后的事实决定（design §3.2）。
CP-verify：R1 executed ≥ 10、R1c executed+skipped ≥ 12（跨指南防失控）；正常结束是指南走完 → 质保判断。
官方 Q&A 指南最长 8 步，旧的「满 4 步转人工」会把指南拦腰截断。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from typing import Any, Literal

from app.conversation.operation_conditions import (
    conditions_for,
    effective_exhausted,
    execution_history,
    explicit_operation_reply,
    feedback_history,
    update_conditions,
)
from app.plans.library import PlanLibrary

Feedback = Literal["solved", "not_solved", "cannot_do"]
SWITCH_CONFIDENCE = 0.3
LIMITS = {"R1": 10, "R1c": 12}


@dataclass
class VerifyOutcome:
    outcome: Literal["done", "next", "escalate", "reassess"]
    plan_cursor: dict[str, Any] | None
    counters: dict[str, int]
    steps_executed: list[dict[str, Any]]
    exhausted_plans: list[str]
    escalate_reason: str | None = None
    switched_to: str | None = None
    trace: dict[str, Any] = field(default_factory=dict)
    step_attempts: list[dict] = field(default_factory=list)
    operation_conditions: dict = field(default_factory=dict)
    # 2026-10-09 第二批：问句的回答写成事实；材料请求「暂时没有」记为待补
    observation: dict[str, Any] | None = None
    missing_material: str | None = None


def step_payload_error(step: dict[str, Any], payload: dict[str, Any]) -> str | None:
    """按卡片类型校验反馈载荷（2026-10-09 第二批 I4）：操作卡交 feedback，问句 / 材料卡交 answer，说明卡可空。
    事实问题不能用「解决了 / 没解决」回答；操作步骤也不能用一个选项糊弄过去。卡片动作与文字命令共用。"""
    kind = step.get("kind") or "action"
    feedback, answer = payload.get("feedback"), payload.get("answer")
    if kind == "action":
        return "not_allowed_now" if feedback is None or answer is not None else None
    if feedback is not None:
        return "not_allowed_now"
    if kind == "statement":
        return None
    if not answer:
        return "invalid_selection"
    if kind == "question":
        option = answer.get("option")
        if option is not None and option not in (step.get("options") or []):
            return "invalid_selection"
        if option is None and not (answer.get("text") or "").strip():
            return "invalid_selection"
    if kind == "material_request" and not (answer.get("unavailable") or (answer.get("text") or "").strip()):
        return "invalid_selection"
    return None


def unanswered(step, answer: dict[str, Any] | None) -> bool:
    """问句收到的是「还没做 / 不知道」：选了审核标的 retry 选项，或有选项的问句收到对不上任何选项的短答。
    只对标了 retry_options 的问句生效，其余问句的短答照旧走 next_on（bp-0032「somewhere near the rim」）。"""
    if step.kind != "question" or not step.retry_options:
        return False
    option = (answer or {}).get("option")
    return option in step.retry_options or (option is None and bool(_answer_text(answer)))


def _answer_text(answer: dict[str, Any] | None) -> str:
    if not answer:
        return ""
    return (answer.get("option") or answer.get("text") or "").strip()


def apply_feedback(
    *,
    state: dict[str, Any],
    feedback: Feedback | None,
    note: str | None,
    card_id: str,
    library: PlanLibrary,
    answer: dict[str, Any] | None = None,
) -> VerifyOutcome:
    cursor = dict(state.get("plan_cursor") or {})
    plan = library.get(cursor["plan_id"])
    step_id = cursor["step_id"]
    step = plan.step(step_id)
    counters = {
        "executed": 0,
        "advanced": 0,
        "skipped": 0,
        "plans_exhausted": 0,
        **(state.get("counters") or {}),
    }
    executed = execution_history(state)
    attempts = feedback_history(state)
    exhausted = sorted(effective_exhausted(state))
    attempt = (
        {
            "plan_id": plan.plan_id,
            "step_id": step_id,
            "card_id": card_id,
            "title": step.title,
            "instruction_src": step.instruction_src,
            "kind": step.kind,
            **({"options": list(step.options)} if step.kind == "question" else {}),
            "feedback": feedback,
            "note": note,
            "answer": answer,
            "ts": datetime.now(UTC).isoformat(),
        }
    )
    attempts.append(attempt)
    result = partial(VerifyOutcome, step_attempts=attempts, operation_conditions=conditions_for(state).model_dump())
    if step.kind != "action":
        # 问句 / 说明 / 材料请求不是操作：不计 executed / skipped，不走 solved / not_solved 的语义。
        # 问句按 branches 分支，其余向后走；回答写成一条 observation 事实，材料暂缺记为待补（I4）。
        nxt = plan.next_step_id(step_id, "not_solved", option=(answer or {}).get("option"))
        observation = None
        missing = None
        text = _answer_text(answer)
        if unanswered(step, answer) and not any(
                a.get("retry") and a.get("instruction_src") == step.instruction_src for a in attempts[:-1]):
            # 「还没检查 / 不知道」不是答案（B21）：记下原话，这张卡不算答完，带提示重发一次；再答不上来才按原边走
            attempt["retry"] = True
            observation = {"kind": "observation", "value": f"{step.title}: {text}", "quote": text,
                           "subject": step.title.rstrip("?"), "polarity": "uncertain", "source": "user_statement"}
            return result("next", dict(cursor), counters, executed, exhausted,
                          trace={"rule": "question_retry"}, observation=observation)
        if step.kind == "question" and text:
            observation = {"kind": "observation", "value": f"{step.title}: {text}", "quote": text,
                           "subject": step.title.rstrip("?"), "polarity": "affirmed", "source": "user_statement"}
        elif step.kind == "material_request":
            if answer and answer.get("unavailable"):
                missing = step.title
            elif text:
                observation = {"kind": "observation", "value": f"{step.title}: {text}", "quote": text,
                               "subject": step.title, "polarity": "affirmed", "source": "user_statement"}
        if nxt in ("DONE", "EXHAUSTED"):
            return exhaust_plan({**state, "step_attempts": attempts}, plan.plan_id, library=library, counters=counters,
                                executed=executed, exhausted=exhausted, observation=observation, missing_material=missing)
        return result("next", {**cursor, "step_id": nxt}, counters, executed, exhausted,
                      trace={"rule": f"{step.kind}:{nxt}"}, observation=observation, missing_material=missing)
    assert feedback is not None
    if feedback == "cannot_do":
        counters["skipped"] += 1
        conditions, _ = update_conditions(
            {**state, "step_attempts": attempts}, explicit_operation_reply(note or ""),
            text=note or "", input_id=state.get("input_id", card_id),
        )
        return VerifyOutcome(
            "reassess", None, counters, executed, exhausted,
            trace={"rule": "operation_blocked", **counters},
            step_attempts=attempts, operation_conditions=conditions,
        )
    executed.append(attempt)
    if feedback == "not_solved":
        counters["executed"] += 1
        counters["advanced"] += 1
    if feedback == "solved":
        return result("done", None, counters, executed, exhausted, trace={"rule": "solved"})
    # CP-verify 上限
    for rule, key in (("R1", "executed"),):
        if counters[key] >= LIMITS[rule]:
            return result(
                "escalate",
                cursor,
                counters,
                executed,
                exhausted,
                escalate_reason=rule,
                trace={"rule": rule, **counters},
            )
    if counters["executed"] + counters["skipped"] >= LIMITS["R1c"]:
        return result(
            "escalate",
            cursor,
            counters,
            executed,
            exhausted,
            escalate_reason="R1c",
            trace={"rule": "R1c", **counters},
        )
    nxt = plan.next_step_id(step_id, feedback)
    if nxt == "DONE":
        return result(
            "done", None, counters, executed, exhausted, trace={"rule": "next_on:DONE"}
        )
    if nxt != "EXHAUSTED":
        return result(
            "next",
            {**cursor, "step_id": nxt},
            counters,
            executed,
            exhausted,
            trace={"rule": f"next_on:{nxt}"},
        )
    return exhaust_plan(
        {**state, "step_attempts": attempts},
        plan.plan_id,
        library=library,
        counters=counters,
        executed=executed,
        exhausted=exhausted,
    )


def exhaust_plan(
    state: dict[str, Any],
    plan_id: str,
    *,
    library: PlanLibrary | None = None,
    counters: dict[str, int] | None = None,
    executed: list[dict[str, Any]] | None = None,
    exhausted: list[str] | None = None,
    observation: dict[str, Any] | None = None,
    missing_material: str | None = None,
) -> VerifyOutcome:
    """当前计划耗尽（next_on 到 EXHAUSTED，或剩余步骤全部被 CP-pre-step / 去重丢弃）：

    只做记账（exhausted_plans、plans_exhausted+1）并返回 reassess。计划耗尽表示当前动作集合需要重新评估，
    不等于诊断失败，也不自动等于转人工；切换 / 追问 / 人工出口由 decide_next 统一决定。
    """
    counters = {
        "executed": 0,
        "advanced": 0,
        "skipped": 0,
        "plans_exhausted": 0,
        **(counters if counters is not None else state.get("counters") or {}),
    }
    executed = list(executed if executed is not None else execution_history(state))
    exhausted = list(exhausted if exhausted is not None else state.get("exhausted_plans") or [])
    if plan_id and plan_id not in exhausted:
        exhausted.append(plan_id)
        counters["plans_exhausted"] += 1
    return VerifyOutcome(
        "reassess",
        None,
        counters,
        executed,
        exhausted,
        trace={"rule": "plan_exhausted", "plan_id": plan_id},
        step_attempts=feedback_history(state),
        operation_conditions=conditions_for(state).model_dump(),
        observation=observation,
        missing_material=missing_material,
    )
