"""步骤先对事实（2026-10-10 多轮复现 P2 / P3）：进指南前，用户已经说过的话回答计划里的问句、判定条件步骤是否适用。

- 问句（bp-0123「continuous or intermittent」）：原话已答 → 记一条 step_attempts（answer.source=fact），与卡片回答走同一条重放边（T46 原评测）。
- 条件步骤（rv-0106「If the robot is often stuck on the edge of stairs…」）：原话否定条件 → 跳过；
  后面的兄弟条件成立（「continues to display errors on flat ground」）→ 前面未知的条件步骤一并跳过（T22）。
模型只给判定和用户原话引文，服务端逐字校验引文、选项与步骤 id；不确定一律 unknown，照常发卡。
同一计划在同一事实修订号下只判一次；只在有用户自述事实时调用。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.conversation.operation_conditions import answered_history
from app.conversation.quotes import quoted
from app.guide.steps import step_card_id
from app.models.queue import CapacityExceeded
from app.models.router import ModelInvokeError, ModelRouter
from app.plans.library import PlanLibrary
from app.plans.models import Plan, PlanStep
from app.prompts import compose_system_prompt, wrap_data

log = logging.getLogger("guide.fact_check")
TASK = "guide.step"


class StepCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_id: str
    status: Literal["answered", "satisfied", "negated", "unknown"]
    option: str | None = Field(default=None, description="question 步骤：逐字取选项之一；对不上留空")
    text: str | None = Field(default=None, max_length=200, description="question 步骤选项对不上时的简短回答")
    quote: str | None = Field(default=None, description="支撑判定的用户原话，逐字摘录")


class FactCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    steps: list[StepCheck] = Field(default_factory=list, max_length=16)


INSTRUCTION = (
    "判断用户已经说过的话是否回答了下列排障步骤，只依据 <data> 中 user_messages 的用户原文，不推测、不补全。\n"
    "- question 步骤：用户原话已经回答时 status=answered；有选项时 option 逐字取其中一个，对不上就留空并在 text 写简短回答。\n"
    "- condition 步骤：condition 是该步骤的适用场景。用户原话表明场景成立用 satisfied，明确不成立用 negated；没提到用 unknown。\n"
    "- answered / satisfied / negated 必须在 quote 逐字引用支撑它的用户原话；助手说过的话和步骤原文都不是依据。\n"
    "- 不确定一律 unknown。只输出 JSON。"
)


def _issue(state: dict[str, Any]) -> dict[str, Any]:
    return (state.get("issues") or {}).get(state.get("active_issue_id")) or {}


def _active_facts(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [f for f in _issue(state).get("facts", []) if f.get("status") == "active"]


def user_corpus(state: dict[str, Any]) -> list[str]:
    """本问题的用户原话：事实来源消息加本轮输入。其他问题的话不算。"""
    ids = {sid for f in _active_facts(state) for sid in f.get("source_entry_ids", [])}
    ids.add(state.get("input_id"))
    return [m["text"] for m in state.get("messages") or []
            if m.get("role") == "user" and m.get("input_id") in ids and (m.get("text") or "").strip()]


def candidates(plan: Plan, state: dict[str, Any]) -> list[PlanStep]:
    """还没回答的问句和带适用条件的操作步骤。"""
    answered = {s.get("instruction_src") for s in answered_history(state)}
    return [s for s in plan.steps if s.instruction_src not in answered and (s.kind == "question" or s.condition)]


def _steps_text(steps: list[PlanStep], library: PlanLibrary) -> str:
    lines = []
    for s in steps:
        if s.kind == "question":
            options = f"（选项：{' / '.join(s.options)}）" if s.options else ""
            lines.append(f"- {s.step_id} [question] {library.evidence_snippet(s.instruction_src)}{options}")
        else:
            lines.append(f"- {s.step_id} [condition] {s.condition}")
    return "\n".join(lines)


def accept(steps: list[PlanStep], raw: list[StepCheck], corpus: list[str]) -> dict[str, dict[str, Any]]:
    """服务端校验：步骤 id 在候选内、判定与步骤类型相符、引文逐字出自用户原话、选项逐字在卡上。"""
    by_id = {s.step_id: s for s in steps}
    out: dict[str, dict[str, Any]] = {}
    for item in raw:
        step = by_id.get(item.step_id)
        if step is None or item.step_id in out or item.status == "unknown":
            continue
        if not item.quote or not any(quoted(item.quote, text) for text in corpus):
            continue
        if step.kind == "question":
            option = item.option if item.option in step.options else None
            text = (item.text or "").strip() or None
            if item.status != "answered" or not (option or text):
                continue
            out[step.step_id] = {"status": "answered", "option": option, "text": None if option else text, "quote": item.quote}
        elif item.status in {"satisfied", "negated"}:
            out[step.step_id] = {"status": item.status, "quote": item.quote}
    return out


def _skips(plan: Plan, verdicts: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """否定的条件步骤跳过；某个条件步骤成立时，它前面还未知的条件步骤也跳过（兄弟场景互斥）。"""
    conditioned = [s.step_id for s in plan.steps if s.condition]
    satisfied = [i for i, sid in enumerate(conditioned) if (verdicts.get(sid) or {}).get("status") == "satisfied"]
    last = satisfied[-1] if satisfied else -1
    steps = {}
    for i, sid in enumerate(conditioned):
        status = (verdicts.get(sid) or {}).get("status", "unknown")
        if status == "negated" or (status == "unknown" and i < last):
            steps[sid] = {**verdicts.get(sid, {"status": "unknown"}), "skip": True}
        elif sid in verdicts:
            steps[sid] = verdicts[sid]
    return steps


async def check_plan_facts(
    router: ModelRouter | None, state: dict[str, Any], plan: Plan, *, library: PlanLibrary,
    lane: str, session_id: str, budget_ms: int,
) -> dict[str, Any]:
    """返回要合并进状态的 {step_checks, step_attempts, guide_trace}；无需判定或判定不可用时返回 {}。"""
    revision = _issue(state).get("issue_revision")
    checks = dict(state.get("step_checks") or {})
    if (checks.get(plan.plan_id) or {}).get("issue_revision") == revision:
        return {}
    steps = candidates(plan, state)
    if (router is None or budget_ms < 1000 or not steps
            or not any(f.get("source") == "user_statement" for f in _active_facts(state))):
        return {}
    corpus = user_corpus(state)
    facts_text = "\n".join(f"- kind={f.get('kind')} polarity={f.get('polarity', 'affirmed')} value={f.get('value')}"
                           for f in _active_facts(state)) or "（无）"
    messages = [
        ("system", compose_system_prompt((state.get("emotion") or {}).get("strategy", "normal"), {
            "stage": "guide", "product": (state.get("product_confirmed") or {}).get("name"), "symptoms": state.get("symptoms"),
        })),
        ("human", INSTRUCTION + "\n排障步骤：\n" + wrap_data(_steps_text(steps, library), kind="plan_steps") + "\n"
         + wrap_data("\n---\n".join(corpus), kind="user_messages") + "\n" + wrap_data(facts_text, kind="structured_facts")),
    ]
    try:
        result = await router.invoke(TASK, messages, FactCheck, budget_ms=budget_ms, session_id=session_id, lane=lane)
    except (ModelInvokeError, CapacityExceeded, ValidationError) as exc:
        log.warning("fact check unavailable session=%s plan=%s: %s", session_id, plan.plan_id, type(exc).__name__)
        return {}
    verdicts = accept(steps, result.parsed.steps, corpus)
    checks[plan.plan_id] = {"issue_revision": revision, "steps": _skips(plan, verdicts)}
    now = datetime.now(UTC).isoformat()
    answered = [
        {"plan_id": plan.plan_id, "step_id": s.step_id, "card_id": step_card_id(session_id, plan.plan_id, s.step_id),
         "title": s.title, "instruction_src": s.instruction_src, "kind": s.kind, "feedback": None, "note": None,
         "answer": {"option": v["option"], "text": v["text"], "unavailable": False, "source": "fact", "quote": v["quote"]},
         "ts": now}
        for s in steps if (v := verdicts.get(s.step_id)) and v["status"] == "answered"
    ]
    trace = [{"event": "fact_check", "plan_id": plan.plan_id, "model_used": result.model_used,
              "verdicts": {sid: v["status"] for sid, v in verdicts.items()},
              "skipped": sorted(sid for sid, v in checks[plan.plan_id]["steps"].items() if v.get("skip"))}]
    update: dict[str, Any] = {"step_checks": checks, "guide_trace": trace}
    if answered:
        update["step_attempts"] = [*(state.get("step_attempts") or []), *answered]
    return update
