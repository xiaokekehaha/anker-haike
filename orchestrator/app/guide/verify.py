"""反馈推进（票 35；03 §1.6、09 §3.3–§3.4）：无 LLM。

solved → 结束；not_solved → executed+1、advanced+1；cannot_do → skipped+1（不计 executed）。
按 next_on[feedback] 推进；EXHAUSTED 时下一计划 confidence ≥ 0.3 则切换（plans_exhausted+1），否则 R2。
CP-verify：R1 executed ≥ 4、R1b skipped ≥ 3、R1c executed+skipped ≥ 6。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from app.plans.library import PlanLibrary

Feedback = Literal["solved", "not_solved", "cannot_do"]
SWITCH_CONFIDENCE = 0.3
LIMITS = {"R1": 4, "R1b": 3, "R1c": 6}


@dataclass
class VerifyOutcome:
    outcome: Literal["done", "next", "escalate"]
    plan_cursor: dict[str, Any] | None
    counters: dict[str, int]
    steps_executed: list[dict[str, Any]]
    exhausted_plans: list[str]
    escalate_reason: str | None = None
    switched_to: str | None = None
    trace: dict[str, Any] = field(default_factory=dict)


def _next_plan(plans_ranked: list[dict[str, Any]], exhausted: set[str]) -> dict[str, Any] | None:
    for p in plans_ranked:
        if p["plan_id"] in exhausted:
            continue
        return p
    return None


def apply_feedback(
    *,
    state: dict[str, Any],
    feedback: Feedback,
    note: str | None,
    card_id: str,
    library: PlanLibrary,
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
    executed = list(state.get("steps_executed") or [])
    exhausted = list(state.get("exhausted_plans") or [])
    executed.append(
        {
            "plan_id": plan.plan_id,
            "step_id": step_id,
            "card_id": card_id,
            "title": step.title,
            "instruction_src": step.instruction_src,
            "feedback": feedback,
            "note": note,
            "ts": datetime.now(UTC).isoformat(),
        }
    )
    if feedback == "not_solved":
        counters["executed"] += 1
        counters["advanced"] += 1
    elif feedback == "cannot_do":
        counters["skipped"] += 1
    if feedback == "solved":
        return VerifyOutcome("done", None, counters, executed, exhausted, trace={"rule": "solved"})
    # CP-verify 上限
    for rule, key in (("R1", "executed"), ("R1b", "skipped")):
        if counters[key] >= LIMITS[rule]:
            return VerifyOutcome(
                "escalate",
                cursor,
                counters,
                executed,
                exhausted,
                escalate_reason=rule,
                trace={"rule": rule, **counters},
            )
    if counters["executed"] + counters["skipped"] >= LIMITS["R1c"]:
        return VerifyOutcome(
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
        return VerifyOutcome(
            "done", None, counters, executed, exhausted, trace={"rule": "next_on:DONE"}
        )
    if nxt != "EXHAUSTED":
        return VerifyOutcome(
            "next",
            {**cursor, "step_id": nxt},
            counters,
            executed,
            exhausted,
            trace={"rule": f"next_on:{nxt}"},
        )
    return exhaust_plan(
        state,
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
    library: PlanLibrary,
    counters: dict[str, int] | None = None,
    executed: list[dict[str, Any]] | None = None,
    exhausted: list[str] | None = None,
) -> VerifyOutcome:
    """当前计划耗尽（next_on 到 EXHAUSTED，或剩余步骤全部被 CP-pre-step / 去重丢弃）：

    plans_exhausted+1；plans_ranked 里下一未耗尽计划 confidence ≥ 0.3 → 切到其首步，否则 R2（09 §3.4）。
    """
    counters = {
        "executed": 0,
        "advanced": 0,
        "skipped": 0,
        "plans_exhausted": 0,
        **(counters if counters is not None else state.get("counters") or {}),
    }
    executed = list(executed if executed is not None else state.get("steps_executed") or [])
    exhausted = list(exhausted if exhausted is not None else state.get("exhausted_plans") or [])
    if plan_id not in exhausted:
        exhausted.append(plan_id)
    counters["plans_exhausted"] += 1
    candidate = _next_plan(list(state.get("plans_ranked") or []), set(exhausted))
    if candidate is None or float(candidate.get("confidence", 0)) < SWITCH_CONFIDENCE:
        return VerifyOutcome(
            "escalate",
            None,
            counters,
            executed,
            exhausted,
            escalate_reason="R2",
            trace={"rule": "R2", "next_confidence": candidate and candidate.get("confidence")},
        )
    new_plan = library.get(candidate["plan_id"])
    new_cursor = {
        "plan_id": new_plan.plan_id,
        "version": new_plan.version,
        "step_id": new_plan.first_step().step_id,
        "source": candidate.get("source"),
    }
    return VerifyOutcome(
        "next",
        new_cursor,
        counters,
        executed,
        exhausted,
        switched_to=new_plan.plan_id,
        trace={"rule": "switch_plan", "confidence": candidate.get("confidence")},
    )
