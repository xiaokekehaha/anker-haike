"""步骤先对事实（2026-10-10 多轮复现 P2 / P3）：进指南前，用户已经说过的话回答计划里的问句、判定条件步骤是否适用。

- 问句（bp-0123「continuous or intermittent」）：原话已答 → 记一条 step_attempts（answer.source=fact），与卡片回答走同一条重放边（T46 原评测）。
- 条件步骤（rv-0106「If the robot is often stuck on the edge of stairs…」）：原话否定条件 → 跳过；
  后面的兄弟条件成立（「continues to display errors on flat ground」）→ 前面未知的条件步骤一并跳过（T22）。
- 同计划已处理的兄弟条件作对照一并给模型，不采纳其判定：只给一条孤立条件时，原话里的否定句
  （「has not been stuck at stairs」）会被套到平地条件上（T22 复测 B06-r2）。
- 只靠「不成立」不能让计划耗尽：最后一个可发步骤照发，用户一句话就能纠正；错跳则整段排障直接转人工。
- 操作步骤（2026-10-10 官方 63 单复测 P1：T16 T27 T31 T37）：原话表明已经做过这一步，或已确认这一步要查的
  情况不存在（「It is fully installed」「no blockage seen」「tank is still full」「wiped the contacts」）→ done，跳过。
  done 可以让计划耗尽：客户自己说试过仍未解决，按 SOP 进质保判断，不再让他重做一遍。
模型只给判定和用户原话引文，服务端逐字校验引文、选项与步骤 id；不确定一律 unknown，照常发卡。
同一计划在同一事实修订号下只判一次；只在用户自己写过话（自述事实或表单问题描述）时调用。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.conversation.operation_conditions import answered_history
from app.conversation.quotes import normalize, quoted
from app.guide.steps import step_card_id
from app.models.queue import CapacityExceeded
from app.models.router import ModelInvokeError, ModelRouter
from app.official.message import parse_message
from app.plans.library import PlanLibrary
from app.plans.models import Plan, PlanStep
from app.prompts import compose_system_prompt, wrap_data

log = logging.getLogger("guide.fact_check")
TASK = "guide.step"


class StepCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_id: str
    status: Literal["answered", "satisfied", "negated", "done", "unknown"]
    option: str | None = Field(default=None, description="question 步骤：逐字取选项之一；对不上留空")
    text: str | None = Field(default=None, max_length=200, description="question 步骤选项对不上时的简短回答")
    quote: str | None = Field(default=None, description="支撑判定的用户原话，逐字摘录")


class FactCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    steps: list[StepCheck] = Field(default_factory=list, max_length=16)


INSTRUCTION = (
    "判断用户已经说过的话是否回答了下列排障步骤，只依据 <data> 中 user_messages 的用户原文，不推测、不补全。\n"
    "- question 步骤：用户原话已经回答时 status=answered；有选项时 option 逐字取其中一个，对不上就留空并在 text 写简短回答。\n"
    "- condition 步骤：condition 是该步骤的适用场景。用户原话表明这个场景成立用 satisfied，明确说这个场景没发生用 negated；没提到用 unknown。"
    "否定一个场景不等于否定另一个场景：逐条判断，quote 必须是针对本条场景的那一句。\n"
    "- action 步骤：用户原话表明已经做过这一步，或已经确认这一步要检查的情况不存在、部件正常时用 done；"
    "步骤让用户检查某个状态（有没有水、装没装好、有没有异物），用户已经说明了该状态，也是 done（例：用户说水箱是满的，"
    "对「检查水箱有没有水，没有就加水」是 done）。用户原话可能是任何语言，按意思判断，quote 逐字摘原文。"
    "只是故障现象、设备推送原文、或只做了相近但不同的操作都用 unknown。\n"
    "  用户说已经换了新的某部件：对「检查这个部件是否堵塞 / 脏污 / 缠绕 / 变形」是 done（新部件没有这些问题）；"
    "步骤还要查用户没换的部位（盖条、安装位、轴、管路）时整步仍是 unknown，不能只看前半句。"
    "「全部清洁过」「都弄干净了」这类笼统说法只对用户点名的部件算数，步骤里的部件用户没点名就是 unknown。"
    "例：用户说「Alle filters en borstels zijn vervangen en alles is schoongemaakt」，"
    "对「检查尘盒、滤网是否堵塞」是 done；对「检查滚刷是否缠绕变形，并检查滚刷盖条与安装位的磨损」是 unknown（盖条、安装位没换）；"
    "对「拆下万向轮检查轮轴脏污」是 unknown（没点名万向轮）。\n"
    "- [reference] 是已处理过的步骤，只用来对照，不要输出它们。\n"
    "- answered / satisfied / negated / done 必须在 quote 逐字引用支撑它的用户原话；助手说过的话和步骤原文都不是依据。\n"
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
    """还没回答的问句与操作步骤（操作步骤核对是否已做过，带适用条件的还核对条件）。"""
    answered = {s.get("instruction_src") for s in answered_history(state)}
    return [s for s in plan.steps if s.instruction_src not in answered and s.kind in {"question", "action"}]


def carried_answers(plan: Plan, state: dict[str, Any], *, session_id: str, now: str) -> list[dict[str, Any]]:
    """同一个问题在另一条指南里已经答过：问句标题与选项完全一致时直接沿用那次的选项（B26：rv-0341 已答
    「拆下滚刷后仍响、不是吱吱声」，换到 rv-0349 不再问第二遍）。只认客户自己选的选项，不认 fact 推断与「还没检查」。"""
    previous = {(a.get("title"), tuple(a.get("options") or ())): a for a in answered_history(state)
                if a.get("kind") == "question" and (a.get("answer") or {}).get("option") and (a.get("answer") or {}).get("source") != "fact"}
    answered_src = {a.get("instruction_src") for a in answered_history(state)}
    out = []
    for step in plan.steps:
        if step.kind != "question" or step.instruction_src in answered_src:
            continue
        hit = previous.get((step.title, tuple(step.options)))
        if hit is None or hit.get("plan_id") == plan.plan_id:
            continue
        out.append({"plan_id": plan.plan_id, "step_id": step.step_id, "card_id": step_card_id(session_id, plan.plan_id, step.step_id),
                    "title": step.title, "instruction_src": step.instruction_src, "kind": step.kind, "options": list(step.options),
                    "feedback": None, "note": None, "ts": now,
                    "answer": {**hit["answer"], "source": "carried", "from_plan": hit.get("plan_id")}})
    return out


def _steps_text(steps: list[PlanStep], library: PlanLibrary, reference: list[PlanStep] = ()) -> str:
    lines = [f"- {s.step_id} [reference] {s.condition}" for s in reference]
    for s in steps:
        if s.kind == "question":
            options = f"（选项：{' / '.join(s.options)}）" if s.options else ""
            lines.append(f"- {s.step_id} [question] {library.evidence_snippet(s.instruction_src)}{options}")
        else:
            condition = f" [condition] {s.condition}" if s.condition else ""
            lines.append(f"- {s.step_id} [action]{condition} {library.evidence_snippet(s.instruction_src)[:400]}")
    return "\n".join(lines)


def accept(steps: list[PlanStep], raw: list[StepCheck], corpus: list[str], push: str = "") -> dict[str, dict[str, Any]]:
    """服务端校验：步骤 id 在候选内、判定与步骤类型相符、引文逐字出自用户原话、选项逐字在卡上。
    done 的引文不能只是设备推送原文（「Please insert dustbin and filter」是设备在说话，不是客户做过）。"""
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
        elif item.status == "done" and not (push and normalize(item.quote) in normalize(push)):
            out[step.step_id] = {"status": "done", "quote": item.quote}
        elif item.status in {"satisfied", "negated"} and step.condition:
            out[step.step_id] = {"status": item.status, "quote": item.quote}
    return out


def _skips(plan: Plan, verdicts: dict[str, dict[str, Any]], pending: set[str]) -> dict[str, dict[str, Any]]:
    """否定的条件步骤跳过；某个条件步骤成立时，它前面还未知的条件步骤也跳过（兄弟场景互斥）。
    已做过（done）的操作步骤跳过。
    pending 是还没处理过的步骤：只因条件否定就会跳过其中最后一个操作步骤（计划就此耗尽）时，不跳，照发；
    客户原话说已经做过的不在此列。"""
    conditioned = [s.step_id for s in plan.steps if s.condition]
    satisfied = [i for i, sid in enumerate(conditioned) if (verdicts.get(sid) or {}).get("status") == "satisfied"]
    last = satisfied[-1] if satisfied else -1
    steps = {sid: {**v, "skip": True} for sid, v in verdicts.items() if v.get("status") == "done"}
    for i, sid in enumerate(conditioned):
        if sid in steps:
            continue
        status = (verdicts.get(sid) or {}).get("status", "unknown")
        if status == "negated" or (status == "unknown" and i < last):
            steps[sid] = {**verdicts.get(sid, {"status": "unknown"}), "skip": True}
        elif sid in verdicts:
            steps[sid] = verdicts[sid]
    remaining = [s.step_id for s in plan.steps if s.step_id in pending and s.kind == "action"
                 and not (steps.get(s.step_id) or {}).get("skip")]
    if not remaining and not satisfied:
        tail = next((s.step_id for s in reversed(plan.steps) if s.step_id in pending and s.kind == "action"), None)
        if tail in steps and steps[tail].get("status") != "done":
            steps[tail] = {**steps[tail], "skip": False, "kept": "last_step"}
    return steps


def user_wrote(state: dict[str, Any]) -> bool:
    """用户自己写过话：有自述事实，或表单的问题描述不只是设备推送原文（T16 / T31 的描述在表单字段里）。"""
    facts = _active_facts(state)
    if any(f.get("source") == "user_statement" or f.get("kind") in {"action_taken", "observation"} for f in facts):
        return True
    fields = parse_message(state.get("text") or "").fields
    description = normalize(fields.get("description") or "")
    return bool(description) and description != normalize(fields.get("push") or "")


async def check_plan_facts(
    router: ModelRouter | None, state: dict[str, Any], plan: Plan, *, library: PlanLibrary,
    lane: str, session_id: str, budget_ms: int,
) -> dict[str, Any]:
    """返回要合并进状态的 {step_checks, step_attempts, guide_trace}；无需判定或判定不可用时返回 {}。"""
    now = datetime.now(UTC).isoformat()
    # 别的指南里答过的同一个问题先确定性沿用（不靠模型，也不受下面「每个计划只判一次」的限制）
    carried = carried_answers(plan, state, session_id=session_id, now=now)
    if carried:
        state = {**state, "step_attempts": [*(state.get("step_attempts") or []), *carried]}
    carried_update: dict[str, Any] = {"step_attempts": state["step_attempts"], "guide_trace": [
        {"event": "answer_carried", "plan_id": plan.plan_id, "steps": [a["step_id"] for a in carried]}]} if carried else {}
    revision = _issue(state).get("issue_revision")
    checks = dict(state.get("step_checks") or {})
    if (checks.get(plan.plan_id) or {}).get("issue_revision") == revision:
        return carried_update
    steps = candidates(plan, state)
    reference = [s for s in plan.steps if s.condition and s not in steps]
    if router is None or budget_ms < 1000 or not steps or not user_wrote(state):
        return carried_update
    corpus = user_corpus(state)
    facts_text = "\n".join(f"- kind={f.get('kind')} polarity={f.get('polarity', 'affirmed')} value={f.get('value')}"
                           for f in _active_facts(state)) or "（无）"
    messages = [
        ("system", compose_system_prompt((state.get("emotion") or {}).get("strategy", "normal"), {
            "stage": "guide", "product": (state.get("product_confirmed") or {}).get("name"), "symptoms": state.get("symptoms"),
        })),
        ("human", INSTRUCTION + "\n排障步骤：\n" + wrap_data(_steps_text(steps, library, reference), kind="plan_steps") + "\n"
         + wrap_data("\n---\n".join(corpus), kind="user_messages") + "\n" + wrap_data(facts_text, kind="structured_facts")),
    ]
    try:
        result = await router.invoke(TASK, messages, FactCheck, budget_ms=budget_ms, session_id=session_id, lane=lane)
    except (ModelInvokeError, CapacityExceeded, ValidationError) as exc:
        log.warning("fact check unavailable session=%s plan=%s: %s", session_id, plan.plan_id, type(exc).__name__)
        return carried_update
    push = "\n".join(parse_message(text).fields.get("push") or "" for text in corpus)
    verdicts = accept(steps, result.parsed.steps, corpus, push)
    pending = {s.step_id for s in plan.steps if s.instruction_src not in {a.get("instruction_src") for a in answered_history(state)}}
    checks[plan.plan_id] = {"issue_revision": revision, "steps": _skips(plan, verdicts, pending)}
    answered = [
        {"plan_id": plan.plan_id, "step_id": s.step_id, "card_id": step_card_id(session_id, plan.plan_id, s.step_id),
         "title": s.title, "instruction_src": s.instruction_src, "kind": s.kind, "feedback": None, "note": None,
         "answer": {"option": v["option"], "text": v["text"], "unavailable": False, "source": "fact", "quote": v["quote"]},
         "ts": now}
        for s in steps if (v := verdicts.get(s.step_id)) and v["status"] == "answered"
    ]
    trace = [*carried_update.get("guide_trace", []), {"event": "fact_check", "plan_id": plan.plan_id, "model_used": result.model_used,
             "verdicts": {sid: v["status"] for sid, v in verdicts.items()},
             "skipped": sorted(sid for sid, v in checks[plan.plan_id]["steps"].items() if v.get("skip"))}]
    update: dict[str, Any] = {"step_checks": checks, "guide_trace": trace}
    if answered or carried:
        update["step_attempts"] = [*(state.get("step_attempts") or []), *answered]
    return update
