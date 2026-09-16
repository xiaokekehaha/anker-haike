"""反馈推进（票 35；03 §1.6、09 §3.3–§3.4）：无 LLM。

solved → 结束；not_solved → executed+1、advanced+1；cannot_do → skipped+1（不计 executed）。
按 next_on[feedback] 推进；EXHAUSTED 时只标记计划耗尽并返回 reassess，
下一动作由 diagnose.decision.decide_next 依据更新后的事实决定（design §3.2）。
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
    outcome: Literal["done", "next", "escalate", "reassess"]
    plan_cursor: dict[str, Any] | None
    counters: dict[str, int]
    steps_executed: list[dict[str, Any]]
    exhausted_plans: list[str]
    escalate_reason: str | None = None
    switched_to: str | None = None
    trace: dict[str, Any] = field(default_factory=dict)


def apply_feedback(
    *,
    state: dict[str, Any],
    feedback: Feedback,
    note: str | None,
    card_id: str,
    library: PlanLibrary,
    observations: list[dict[str, str]] | None = None,
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
            "observations": [
                {"observation_id": o["observation_id"], "option_id": o["option_id"]}
                for o in (observations or [])
                if o.get("observation_id") and o.get("option_id")
            ],
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
    library: PlanLibrary | None = None,
    counters: dict[str, int] | None = None,
    executed: list[dict[str, Any]] | None = None,
    exhausted: list[str] | None = None,
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
    executed = list(executed if executed is not None else state.get("steps_executed") or [])
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
    )
