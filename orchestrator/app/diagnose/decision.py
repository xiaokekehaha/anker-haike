"""Issue-local symptom evidence and next-move decisions.

Facts and quoted answers are the inputs. Codes/status are compatibility projections,
never independent evidence capable of overruling an accepted answer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.conversation.taxonomy import (
    canonical_codes,
    interview_answer,
    next_interview,
    record_response,
    response_attempts,
    taxonomy,
)


def _active_facts(issue):
    return [
        f
        for f in issue.get("facts", [])
        if f.get("status") == "active" and f.get("kind") == "symptom"
    ]


def valid_interview(interview):
    return bool(
        interview
        and not interview.get("superseded_by_input_id")
        and interview.get("taxonomy_version") in {None, taxonomy()["version"]}
    )


def _answer_codes(interview):
    if not valid_interview(interview):
        return []
    # Recover old checkpoints whose `narrowed` flag was overwritten, using the
    # accepted answers and candidate set, not the stale presentation flag.
    if not interview.get("answers") or (
        len(interview.get("candidates", [])) != 1
        and not any(a.get("answer") == "selection" for a in interview["answers"])
    ):
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


def accept_answer(issue, answer, *, text, input_id, changed_fact_ids, answer_expected=False):
    """The only writer of accepted interview results; corrections explicitly supersede them."""
    original = issue.get("symptom_interview")
    interview, accepted = interview_answer(original, answer, text, input_id)
    question = (interview or {}).get("question")
    if (
        valid_interview(interview)
        and question
        and not accepted
        and answer_expected
        and text.strip()
        and question.get("asked_input_id") != input_id
    ):
        interview = record_response(
            interview,
            input_id=input_id,
            outcome="unparsed",
            candidates=interview.get("candidates", []),
            progressed=False,
            quote=text,
        )
    changed = [
        f
        for f in issue.get("facts", [])
        if f.get("fact_id") in changed_fact_ids and f.get("kind") == "symptom"
    ]
    corrected = any(f.get("status") != "active" for f in changed)
    if interview and changed and not corrected:
        # New symptom evidence starts a new consecutive-progress window, not
        # a new total budget. Retries are de-duplicated by the reducer.
        interview = {**interview, "progress_start": len(response_attempts(interview))}
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
    if not codes and not issue.get("facts") and not changed_fact_ids and not original:
        # Legacy/no-model checkpoints already carry a positively matched code.
        # It remains issue-local; changing devices creates a fresh issue.
        codes = list(issue.get("symptom_codes") or [])
    return {"symptom_interview": interview, "symptom_codes": codes}, accepted


MAX_NO_PROGRESS = 2
MAX_INTERVIEW_RESPONSES = 8


@dataclass(frozen=True)
class DiagnosticDecision:
    outcome: Literal["continue", "clarify", "escalate"]
    codes: list[str]
    reason: str
    interview: dict[str, Any] | None = None
    source_refs: tuple[str, ...] = ()
    candidate_codes: tuple[str, ...] = ()
    allowed_plans: tuple[dict[str, Any], ...] = ()
    constrain_plans: bool = False
    missing_information: tuple[str, ...] = ()
    progress: dict[str, int] = field(default_factory=dict)

    def snapshot(self, state):
        value = asdict(self)
        value.pop("interview")
        return {
            **value,
            "issue_id": state.get("active_issue_id"),
            "taxonomy_version": taxonomy()["version"],
            "input_id": state.get("input_id"),
        }


def constrain_plans(state, plans):
    """Carry the decision's intersection through ranking and operation publication."""
    decision = state.get("diagnostic_decision") or {}
    if not decision.get("constrain_plans"):
        return list(plans)
    if (
        decision.get("issue_id") != state.get("active_issue_id")
        or decision.get("taxonomy_version") != taxonomy()["version"]
    ):
        return []
    allowed = {(p["plan_id"], p["version"]) for p in decision.get("allowed_plans", [])}
    return [p for p in plans if (p.plan_id, p.version) in allowed]


def _progress(interview):
    attempts = response_attempts(interview)
    no_progress = 0
    for attempt in reversed(attempts[int((interview or {}).get("progress_start", 0)) :]):
        if attempt["progressed"]:
            break
        no_progress += 1
    return {
        "attempts": len(attempts),
        "consecutive_no_progress": no_progress,
        "hard_limit": MAX_INTERVIEW_RESPONSES,
    }


def decide_symptoms(state, *, available_plans=()) -> DiagnosticDecision:
    issue = (state.get("issues") or {}).get(state.get("active_issue_id"), {})
    raw_interview = state.get("symptom_interview")
    interview = raw_interview if valid_interview(raw_interview) else None
    issue = {**issue, "symptom_interview": interview}
    codes = symptom_codes(issue)
    if not issue.get("facts") and not raw_interview:
        codes = list(dict.fromkeys([*codes, *(state.get("symptom_codes") or [])]))
    product = state.get("product_confirmed") or {}
    category = state.get("category") or product.get("category")
    if not codes:
        for text in state.get("symptoms") or []:
            codes.extend(canonical_codes(text, category=category)[0])
        codes.extend(canonical_codes(state.get("text", ""), category=category)[0])
    codes = list(dict.fromkeys(codes))
    refs = list(
        dict.fromkeys(ref for f in _active_facts(issue) for ref in f.get("source_entry_ids", []))
    )
    if interview:
        refs = list(dict.fromkeys([*refs, *(a["input_id"] for a in response_attempts(interview))]))
    candidates = tuple(
        f["symptom_code"]
        for f in taxonomy()["families"]
        if interview and f["fault_family"] in interview.get("candidates", [])
    )
    eligible = [
        p
        for p in available_plans
        if p.applies(category=category, sku=product.get("sku"))
        and p.plan_id not in (state.get("exhausted_plans") or [])
    ]
    progress = _progress(interview)

    def result(
        outcome,
        reason,
        *,
        selected=(),
        constrained=False,
        missing=(),
        current=interview,
        resolved_codes=None,
    ):
        return DiagnosticDecision(
            outcome=outcome,
            codes=codes if resolved_codes is None else resolved_codes,
            reason=reason,
            interview=current,
            source_refs=tuple(refs),
            candidate_codes=candidates,
            allowed_plans=tuple(
                {
                    "plan_id": p.plan_id,
                    "version": p.version,
                    "step_id": p.first_step().step_id,
                    "instruction_src": p.first_step().instruction_src,
                }
                for p in selected
            ),
            constrain_plans=constrained,
            missing_information=tuple(missing),
            progress=progress,
        )

    if not (state.get("turn_decision") or {}).get("allowed_operations", True):
        return result("escalate", "safety_restriction")
    if interview and interview.get("answers") and not interview.get("candidates"):
        return result("escalate", "evidence_conflict", missing=["核对互相冲突的现象和回答"])
    if codes:
        return result(
            "continue",
            "symptom_evidence_available",
            selected=[p for p in eligible if set(codes).intersection(p.symptom_codes)],
        )
    if category != taxonomy()["category"]:
        return result("clarify", "symptom_missing", missing=["具体故障现象"])
    # Same plan identity/version guarantees compatible instructions, conditions,
    # and subsequent transitions. Similar step names do not establish equivalence.
    if interview and any(a["answer"] in {"yes", "no"} for a in interview.get("answers", [])):
        choices = [{p.plan_id for p in eligible if code in p.symptom_codes} for code in candidates]
        shared = set.intersection(*choices) if choices else set()
        if shared:
            reason = (
                "same_applicable_plans"
                if all(c == choices[0] for c in choices)
                else "common_applicable_plans"
            )
            return result(
                "continue",
                reason,
                selected=[p for p in eligible if p.plan_id in shared],
                constrained=True,
                resolved_codes=list(candidates),
            )
    interview = next_interview(interview, state.get("active_issue_id"), state.get("input_id"))
    progress = _progress(interview)
    question = (interview.get("question") or {}).get("question")
    missing = [question] if question else ["可区分当前现象的澄清问题"]
    reason = None
    if progress["consecutive_no_progress"] >= MAX_NO_PROGRESS:
        tail = response_attempts(interview)[-MAX_NO_PROGRESS:]
        reason = (
            "answers_unavailable" if all(a["outcome"] == "unknown" for a in tail) else "no_progress"
        )
    elif progress["attempts"] >= MAX_INTERVIEW_RESPONSES:
        reason = "clarification_budget_exhausted"
    elif not question:
        reason = "question_coverage_missing"
    if reason:
        return result(
            "escalate",
            reason,
            missing=missing,
            current={**interview, "status": "insufficient", "question": None},
        )
    return result("clarify", "symptom_missing", current=interview, missing=missing)


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
