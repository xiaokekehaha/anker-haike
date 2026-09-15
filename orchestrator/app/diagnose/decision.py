"""Issue-local symptom evidence and next-move decisions.

Facts and quoted answers are the inputs. Codes/status are compatibility projections,
never independent evidence capable of overruling an accepted answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.conversation.taxonomy import canonical_codes, interview_answer, next_interview, taxonomy


def _active_facts(issue):
    return [
        f
        for f in issue.get("facts", [])
        if f.get("status") == "active" and f.get("kind") == "symptom"
    ]


def _answer_codes(interview):
    if not interview or interview.get("superseded_by_input_id"):
        return []
    # Recover old checkpoints whose `narrowed` flag was overwritten, using the
    # accepted answers and candidate set, not the stale presentation flag.
    if not interview.get("answers") or len(interview.get("candidates", [])) != 1:
        return []
    return [
        f["symptom_code"]
        for f in taxonomy()["families"]
        if f["fault_family"] in interview["candidates"]
    ]


def symptom_codes(issue):
    codes = [code for f in _active_facts(issue) for code in f.get("symptom_codes", [])]
    codes += _answer_codes(issue.get("symptom_interview"))
    return list(dict.fromkeys(codes))


def accept_answer(issue, answer, *, text, input_id, changed_fact_ids):
    """The only writer of accepted interview results; corrections explicitly supersede them."""
    interview, accepted = interview_answer(issue.get("symptom_interview"), answer, text, input_id)
    changed = [
        f
        for f in issue.get("facts", [])
        if f.get("fact_id") in changed_fact_ids and f.get("kind") == "symptom"
    ]
    corrected = any(f.get("status") != "active" for f in changed)
    if interview and corrected and not accepted:
        interview = {
            **interview,
            "status": "superseded",
            "question": None,
            "superseded_by_input_id": input_id,
        }
    elif interview and not interview.get("superseded_by_input_id"):
        # Adding a symptom does not retract earlier answers. It can make the
        # pending question unnecessary, while all accepted observations remain.
        if changed and not accepted and symptom_codes(issue):
            interview = {**interview, "question": None}
        interview = {
            **interview,
            "status": "narrowed"
            if _answer_codes(interview)
            else "asking"
            if interview.get("question")
            else "resolved",
        }
    projected = {**issue, "symptom_interview": interview}
    codes = symptom_codes(projected)
    if not codes and not issue.get("facts") and not changed_fact_ids:
        # Legacy/no-model checkpoints already carry a positively matched code.
        # It remains issue-local; changing devices creates a fresh issue.
        codes = list(issue.get("symptom_codes") or [])
    return {"symptom_interview": interview, "symptom_codes": codes}, accepted


@dataclass(frozen=True)
class DiagnosticDecision:
    outcome: Literal["continue", "clarify", "escalate"]
    codes: list[str]
    reason: str
    interview: dict[str, Any] | None = None
    source_refs: tuple[str, ...] = ()


def decide_symptoms(state, *, available_plans=()) -> DiagnosticDecision:
    issue = (state.get("issues") or {}).get(state.get("active_issue_id"), {})
    # The active issue is authoritative for facts; graph fields are its current
    # interview/product projection until commit_issue persists the turn.
    issue = {**issue, "symptom_interview": state.get("symptom_interview")}
    codes = symptom_codes(issue)
    if not issue.get("facts"):
        codes = list(dict.fromkeys([*codes, *(state.get("symptom_codes") or [])]))
    category = state.get("category") or (state.get("product_confirmed") or {}).get("category")
    # Lexical matching is only positive evidence for legacy/no-model inputs.
    # Unknown wording cannot veto an accepted model-coded fact.
    if not codes:
        for text in state.get("symptoms") or []:
            codes.extend(canonical_codes(text, category=category)[0])
        codes.extend(canonical_codes(state.get("text", ""), category=category)[0])
    codes = list(dict.fromkeys(codes))
    refs = tuple(
        dict.fromkeys(ref for f in _active_facts(issue) for ref in f.get("source_entry_ids", []))
    )
    interview = issue.get("symptom_interview")
    if interview and not interview.get("superseded_by_input_id"):
        refs = tuple(dict.fromkeys([*refs, *(a["input_id"] for a in interview.get("answers", []))]))
    if codes:
        # Known evidence is sufficient to choose applicable capabilities. A
        # diagnostic classification is not a demand for a unique hardware cause.
        return DiagnosticDecision("continue", codes, "symptom_evidence_available", interview, refs)
    if category != taxonomy()["category"]:
        return DiagnosticDecision("clarify", [], "symptom_missing", source_refs=refs)
    if interview and interview.get("superseded_by_input_id"):
        interview = None
    # Ask only when the answer changes which approved operations apply. A
    # unique fault label is unnecessary when every remaining possibility has
    # the same non-empty set of available plans.
    if interview and any(a["answer"] in {"yes", "no"} for a in interview.get("answers", [])):
        candidates = [
            f["symptom_code"]
            for f in taxonomy()["families"]
            if f["fault_family"] in interview.get("candidates", [])
        ]
        choices = [
            {p.plan_id for p in available_plans if code in p.symptom_codes} for code in candidates
        ]
        if choices and choices[0] and all(ids == choices[0] for ids in choices):
            return DiagnosticDecision(
                "continue", candidates, "same_applicable_plans", interview, refs
            )
    interview = next_interview(interview, state.get("active_issue_id"), state.get("input_id"))
    no_progress = 0
    for answer in reversed(interview.get("answers", [])):
        if answer["answer"] != "unknown":
            break
        no_progress += 1
    if no_progress >= 2 or not interview.get("question"):
        reason = "answers_unavailable" if no_progress >= 2 else "no_discriminating_question"
        return DiagnosticDecision(
            "escalate", [], reason, {**interview, "status": "insufficient", "question": None}, refs
        )
    return DiagnosticDecision("clarify", [], "symptom_missing", interview, refs)


def owns_diagnostic_reply(state):
    """Physical advice always uses published plan content, including conversational detours."""
    issue = (state.get("issues") or {}).get(state.get("active_issue_id"), {})
    return bool(
        _active_facts(issue)
        or state.get("symptoms")
        or state.get("symptom_interview")
        or state.get("symptom_codes")
        or state.get("plan_cursor")
    )


def explanation(state):
    decision = state.get("turn_decision") or {}
    if not decision.get("allowed_operations", True):
        return "这台设备还有待核实的安全风险，请暂停使用和充电。可以继续核对记录或整理给人工客服。"
    step = ((state.get("pending_card") or {}).get("payload") or {}).get("step")
    if step:
        caution = f"注意：{step['caution']}。" if step.get("caution") else ""
        return (
            f"当前已确认的排查步骤是：{step['instruction']}。{caution}"
            f"预期结果：{step['expected_result']}。这次问答不会记为已执行；"
            "请完成后反馈结果，如不能操作请反馈“无法操作”。"
        )
    if state.get("stage") == "done":
        return "此前已记录问题解决；如果问题再次出现，请描述当前现象，我会重新核对适用方案。"
    if state.get("symptom_interview", {}) and (state.get("symptom_interview") or {}).get(
        "question"
    ):
        return state["symptom_interview"]["question"]["question"]
    if state.get("exhausted_plans"):
        return "现有适用排查步骤已经尝试或无法继续，尚未确认解决。可以整理已试步骤给人工客服；不会重复建议您已做过的操作。"
    return "当前尚未有可下发的排查步骤。可以要求继续排查，我会核对已报告现象和适用方案；没有对应方案时会明确说明。"
