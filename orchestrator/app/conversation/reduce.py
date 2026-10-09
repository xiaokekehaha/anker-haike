"""Validate semantic proposals against explicit sources; preserve issue-local state."""

from __future__ import annotations

import copy
import uuid

from app.conversation.interpret import TurnInterpretation
from app.conversation.operation_conditions import (
    effective_exhausted,
    resolve_operation_reply,
    update_conditions,
)
from app.conversation.quotes import quoted

# The diagnostic engine sees a projection. Only these fields may return to an issue.
ISSUE_FIELDS = {
    "business_context": None,
    "case_status": None,
    "case_order_no": None,
    "execution_key": None,
    "human_involved": False,
    "stage": "intake",
    "substage": None,
    "pending_card": None,
    "product_confirmed": None,
    "product_candidates": [],
    "product_state": "unknown",
    "category": None,
    "out_of_scope": False,
    "clarification": None,
    "abandoned_card": None,
    "observations": [],
    "product_hints": [],
    "product_question": None,
    "symptoms": [],
    "diagnostic_decision": None,
    "evidence": {},
    "current_evidence_ids": [],
    "image_observations": [],
    "knowledge_status": None,
    "plans_ranked": [],
    "retrieval_basis": None,
    "retrieval_rounds": 0,
    "rewrite_used": False,
    "evidence_quality": None,
    "query": None,
    "error_codes": [],
    "diagnose_outcome": None,
    "plan_cursor": None,
    "steps_executed": [],
    "step_attempts": [],
    "operation_conditions": {},
    "counters": {},
    "exhausted_plans": [],
    "next_action": None,
    "receipt": None,
    "vision_status": None,
    "processed_fault_image_ids": [],
    "visual_product": None,
    "visible_parts": [],
    "service_context": {}, "context_sources": {}, "warranty": None, "sop_evidence": {}, "awaiting_evidence": [], "logistics_announced": False,
    "proposal": None, "case_id": None, "execution": None, "gate_result": None,
    "requested_remedy": None, "consult_intent": None,
    "last_consult_params": {},
    "consult_params": {}, "consult_attempts": 0, "consult_answered": False,
    "emotion_trend": "stable", "emotion_actions": [], "unresolved_turns": 0,
    "emotion": {"level": None, "strategy": "normal"},
    "human_request_info": False, "human_decision_id": None,
    "task_queue": [], "emotion_track": [], "fault_localization": None,
    "image_quality": None, "retake_skipped": False, "retake_attempts": 0,
}


def stable_id(*parts) -> str:
    return uuid.uuid5(uuid.NAMESPACE_URL, ":".join(map(str, parts))).hex


def reduce_turn(state: dict, meaning: TurnInterpretation, *, precheck_risk: bool = False, business_order_no: str | None = None, new_business_subject: bool = False) -> dict:
    issues = copy.deepcopy(state.get("issues") or {})
    iid, at = state["input_id"], state["at"]
    current = state.get("active_issue_id")
    if iid in state.get("applied_input_ids", []):
        return {}
    if current in issues:
        issues[current].update(
            {key: copy.deepcopy(state.get(key, default)) for key, default in ISSUE_FIELDS.items()}
        )
    target = state.get("target_issue_id") or meaning.target_issue_id
    clarify = meaning.clarification
    if target and target not in issues:
        target, clarify = current, "您想继续哪个问题？请说明设备或之前的现象。"
    target = target or current
    if (
        meaning.primary_intent in {"history_query", "handoff_status", "explain"}
        and state.get("entry") != "action"
    ):
        target = current
    # Drafts preserve uncertainty about the device; policy still considers unresolved risks.
    new_device = (
        meaning.device_relation == "other"
        and bool(meaning.product_hints or meaning.device_category)
        and not (target in issues and target != current)
    )
    if meaning.primary_intent in {"history_query", "handoff_status", "explain", "resume_issue"} or (meaning.answer_request and meaning.primary_intent in {"order_query", "warranty_query", "logistics_query"}):
        new_device = False
    def case_order(issue):
        # Old checkpoints predate the explicit binding, but retain the case receipt.
        return issue.get("case_order_no") or (
            ((issue.get("receipt") or {}).get("fields") or {}).get("order_no")
            if issue.get("case_id") else None
        )

    business_switched = False
    business_ambiguous = False
    if new_business_subject and target in issues and case_order(issues[target]):
        target = None
        new_device = False
        business_switched = True
    if business_order_no and target in issues and case_order(issues[target]) not in {None, business_order_no}:
        matches = [key for key, value in issues.items() if case_order(value) == business_order_no]
        if len(matches) > 1:
            business_ambiguous = True
            clarify = "该订单有多个服务问题，请选择要继续处理的那一个。"
        else:
            target = matches[0] if matches else None
            new_device = False
            business_switched = True
    open_new = target is None or new_device or meaning.primary_intent == "new_issue"
    if meaning.primary_intent == "new_issue" and not new_device:
        clarify = clarify or "好的，请描述新问题，以及是否仍是同一台设备。之前的问题记录会保留。"
    if open_new:
        target = stable_id(state["session_id"], iid, "issue")
        issues[target] = copy.deepcopy(ISSUE_FIELDS)
        issues[target].update(
            issue_id=target,
            status="draft" if not meaning.facts else "open",
            opened_at=at,
            opened_by_input_id=iid,
            title=(meaning.facts[0].value if meaning.facts else "待描述的问题"),
            facts=[],
            issue_revision=0,
            device_ref={
                "device_ref_id": stable_id(target, "device"),
                "category": meaning.device_category,
                "identity_status": "provisional",
                "source_ids": [iid],
            },
            handoff={"status": "not_requested"},
        )
    pending_changes = []
    if target != current and current in issues and issues[current].get("pending_card"):
        pc = issues[current]["pending_card"]
        pc["status"] = "suspended"
        pending_changes.append(
            {
                "issue_id": current,
                "pending_id": pc["card_id"],
                "status": "suspended",
                "reason": "issue_switched",
            }
        )
    issue = issues[target]
    resumed_pending = False
    if target != current and issue.get("pending_card"):
        previous = issue["pending_card"]
        replacement_id = stable_id(iid, target, "resume_card")
        issue["pending_card"] = dict(
            previous,
            card_id=replacement_id,
            input_token=stable_id(iid, target, "resume_token"),
            status="active",
            supersedes=previous["card_id"],
        )
        pending_changes.append(
            {
                "issue_id": target,
                "pending_id": previous["card_id"],
                "status": "invalidated",
                "reason": "resumed_with_new_token",
                "superseded_by": replacement_id,
            }
        )
        resumed_pending = True
    text = state.get("text", "")
    if state.get("entry") == "action":
        text = ((state.get("last_action") or {}).get("payload") or {}).get("text", "")
    facts = issue.setdefault("facts", [])
    applied = []
    for index, correction in enumerate(meaning.corrections):
        old = next(
            (f for f in facts if f["fact_id"] == correction.fact_id and f["status"] == "active"),
            None,
        )
        if not old or not quoted(correction.quote, text):
            clarify = "请指出需要更正的是哪项记录，以及正确的情况。"
            continue
        old["status"] = "superseded" if correction.value else "retracted"
        old["superseded_by_input_id"] = iid
        applied.append(
            {
                "op": "replace" if correction.value else "retract",
                "fact_id": old["fact_id"],
                "input_id": iid,
            }
        )
        if correction.value:
            replacement = dict(
                old,
                fact_id=stable_id(iid, "replace", index),
                value=correction.value,
                status="active",
                source_entry_ids=[iid],
                recorded_at=at,
                supersedes=old["fact_id"],
                revision=old["revision"] + 1,
            )
            facts.append(replacement)
    if meaning.primary_intent == "correct" and not meaning.corrections:
        clarify = clarify or "您刚才哪句话说错了？请告诉我正确的设备或现象，我会更新对应记录。"
    for index, candidate in enumerate(meaning.facts):
        if not quoted(candidate.quote, text):
            continue
        if any(f["value"] == candidate.value and f["status"] == "active" for f in facts):
            continue
        fact = {
            "fact_id": stable_id(iid, "add", index),
            "kind": candidate.kind,
            "context_field": candidate.context_field,
            "value": candidate.value,
            "issue_id": target,
            "device_ref_id": issue["device_ref"]["device_ref_id"],
            "status": "active",
            "revision": 1,
            "source_kind": "user_report",
            "source_entry_ids": [iid],
            "recorded_at": at,
            "occurred_at": candidate.occurred_at,
            "time_expression": candidate.time_expression,
            "precision": candidate.precision,
            "quote": candidate.quote,
        }
        facts.append(fact)
        applied.append({"op": "add", "fact_id": fact["fact_id"], "input_id": iid})
    hints = [
        hint
        for hint in meaning.product_hints
        if hint.strip() and hint.casefold() in text.casefold()
    ]
    product_corrected = (
        meaning.primary_intent == "correct" and hints and hints != issue.get("product_hints")
    )
    if product_corrected:
        if not meaning.clarification:
            clarify = None
        issue.update(
            product_hints=hints,
            product_confirmed=None,
            product_candidates=[],
            product_state="unknown",
            category=None,
            current_evidence_ids=[],
            error_codes=[],
            plans_ranked=[],
            plan_cursor=None,
            query=None,
            knowledge_status=None,
        )
    elif hints:
        issue["product_hints"] = list(dict.fromkeys([*issue.get("product_hints", []), *hints]))
    changed_ids = {patch["fact_id"] for patch in applied}
    basis_changed = bool(
        product_corrected
        or any(p["op"] in {"replace", "retract"} for p in applied)
        or any(f["fact_id"] in changed_ids and f["kind"] == "symptom" for f in facts)
    )
    if basis_changed and issue.get("pending_card"):
        pc = issue["pending_card"]
        pending_changes.append(
            {
                "issue_id": target,
                "pending_id": pc["card_id"],
                "status": "invalidated",
                "reason": "basis_changed",
            }
        )
        issue["pending_card"] = None
        resumed_pending = False
    issue["symptoms"] = [
        f["value"] for f in facts if f["status"] == "active" and f["kind"] == "symptom"
    ]
    issue["observations"] = [
        f["value"] for f in facts if f["status"] == "active" and f["kind"] == "observation"
    ]
    operation_proposal, operation_clarification = resolve_operation_reply(text, issue)
    operation_proposal = operation_proposal or meaning.operation_update
    if operation_clarification:
        operation_proposal = None
        clarify = operation_clarification
    conditions, operation_changed = update_conditions(issue, operation_proposal, text=text, input_id=iid)
    issue["operation_conditions"] = conditions
    if operation_changed:
        issue["exhausted_plans"] = sorted(effective_exhausted(issue))
        pc = issue.get("pending_card")
        if pc and pc.get("kind") == "step_feedback":
            pending_changes.append({"issue_id": target, "pending_id": pc["card_id"], "status": "invalidated", "reason": "operation_conditions_changed"})
            issue["pending_card"] = None
            resumed_pending = False
    if basis_changed:
        issue["diagnostic_decision"] = None
    if issue["symptoms"]:
        issue["status"] = "open"
        issue["title"] = "、".join(issue["symptoms"])
    risks = copy.deepcopy(state.get("risk_cases") or [])
    new_risk = (
        meaning.device_safety_assertion == "reported" and quoted(meaning.device_safety_quote, text)
    )
    validated_negation = meaning.device_safety_assertion == "negated" and bool(
        quoted(meaning.device_safety_quote, text)
    )
    uncertain_risk = precheck_risk and not new_risk and not validated_negation
    if new_risk or uncertain_risk:
        risk_target = target if new_device or meaning.device_relation == "current" else None
        risks.append(
            {
                "risk_id": stable_id(iid, "risk"),
                "rule_id": "R4",
                "status": "reported",
                "source_input_ids": [iid],
                "reported_at": at,
                "issue_id": risk_target,
                "device_ref_id": issue["device_ref"]["device_ref_id"] if risk_target else None,
                "restriction": "no_operations",
                "policy_version": "2026-09-13",
                "last_evidence_seq": state.get("input_seq"),
            }
        )
    corrected_sources = {
        source
        for f in facts
        if f.get("superseded_by_input_id") == iid
        for source in f.get("source_entry_ids", [])
    }
    if corrected_sources or validated_negation:
        for risk in risks:
            if (
                risk.get("issue_id") in {None, target}
                and risk["status"] == "reported"
                and (
                    validated_negation
                    or corrected_sources.intersection(risk.get("source_input_ids", []))
                )
            ):
                risk["status"] = "disputed"
                risk.setdefault("dispute_refs", []).append(iid)
    restriction = any(
        r["status"] in {"reported", "disputed"}
        and (
            r.get("issue_id") in {None, target}
            or issue["status"] == "draft"
            or r.get("device_ref_id") == issue["device_ref"]["device_ref_id"]
        )
        for r in risks
    )
    if restriction and (issue.get("pending_card") or {}).get("kind") == "step_feedback":
        pc = issue.pop("pending_card")
        step = (pc.get("payload") or {}).get("step") or {}
        issue["observations"].append(f"已提供但未反馈（安全限制已撤回）：{step.get('title', step.get('step_id', '排查步骤'))}")
        pending_changes.append(
            {
                "issue_id": target,
                "pending_id": pc["card_id"],
                "status": "invalidated",
                "reason": "risk_restriction",
            }
        )
        issue["pending_card"] = None
        resumed_pending = False
    intent = meaning.primary_intent
    if intent in {"replacement_request", "refund_request", "address_update"}:
        issue["requested_remedy"] = {"replacement_request": "replace", "refund_request": "refund", "address_update": "address_update"}[intent]
    if intent == "request_human" and state.get("entry") != "action" and not (
        quoted(meaning.human_request_quote, text)
    ):
        # A classifier's recommendation is not a user request to cancel a task.
        intent = "complaint" if meaning.emotion_level in {"dissatisfied", "angry", "complaint_risk"} else "unknown"
        if intent == "unknown":
            clarify = clarify or "请说明是需要接入人工客服，还是继续处理当前问题。"
    mode = (
        "clarify"
        if clarify
        else "dialogue"
        if intent
        in {
            "history_query",
            "explain",
            "handoff_status",
            "preference",
            "social",
            "complaint",
            "unknown",
            "new_issue",
            "resume_issue",
        }
        else "diagnose"
    )
    if issue.get("pending_card") and intent == "supplement" and not basis_changed:
        mode = "dialogue"
    trigger = "R4" if new_risk or uncertain_risk else "R3" if intent == "request_human" else None
    if (
        intent == "request_human"
        and issue.get("handoff", {}).get("status") == "prepared"
        and not applied
    ):
        trigger, mode = None, "dialogue"
    if trigger and issue.get("pending_card"):
        pc = issue["pending_card"]
        if pc.get("kind") == "step_feedback":
            step = (pc.get("payload") or {}).get("step") or {}
            issue["observations"].append(f"已提供但未反馈（转人工已撤回）：{step.get('title', step.get('step_id', '排查步骤'))}")
        pending_changes.append(
            {
                "issue_id": target,
                "pending_id": pc["card_id"],
                "status": "invalidated",
                "reason": "human_requested" if trigger == "R3" else "risk_restriction",
            }
        )
        issue["pending_card"] = None
        resumed_pending = False
    if restriction and mode == "diagnose" and not trigger:
        mode = "dialogue"
    if applied or open_new or product_corrected or operation_changed:
        issue["issue_revision"] = issue.get("issue_revision", 0) + 1
    decision = {
        "input_id": iid,
        "primary_intent": intent,
        "answer_scope": meaning.business_reference.relation if meaning.business_reference and meaning.business_reference.relation in {"case", "issue"} and quoted(meaning.business_reference.quote, text) else "focus",
        "answer_request": meaning.answer_request.model_dump() if meaning.answer_request and quoted(meaning.answer_request.quote, text) else None,
        "secondary_intents": meaning.secondary_intents,
        "target_issue_id": target,
        "reply_mode": mode,
        "clarification": clarify,
        "allowed_operations": not restriction,
        "escalation_trigger": trigger,
        "source_refs": [iid],
        "patches": applied,
        "switched": target != current,
        "pending_changes": pending_changes,
        "resumed_pending": resumed_pending,
        "business_switched": business_switched,
        "business_ambiguous": business_ambiguous,
        "operation_changed": operation_changed,
        "diagnostic_request": quoted(meaning.diagnostic_request_quote, text),
    }
    result = {key: copy.deepcopy(issue.get(key, default)) for key, default in ISSUE_FIELDS.items()}
    preferences = dict(state.get("session_preferences") or {})
    if meaning.detail_level and quoted(meaning.preference_quote, text):
        preferences.update(detail_level=meaning.detail_level, source_input_id=iid, updated_at=at)
    result["session_preferences"] = preferences
    result.update(
        active_issue_id=target,
        issues=issues,
        risk_cases=risks,
        turn_decision=decision,
        context_revision=state.get("context_revision", 0)
        + (
            1
            if applied or open_new or product_corrected or operation_changed or risks != state.get("risk_cases", [])
            else 0
        ),
        applied_input_ids=[*state.get("applied_input_ids", []), iid],
        # Compatibility with existing pure diagnostic functions is a per-run projection, never inherited routing.
        escalate_reason=trigger,
        _decision=None,
        _verify=None,
    )
    return result


def persist_issue(state: dict) -> dict:
    issues = copy.deepcopy(state.get("issues") or {})
    active = state.get("active_issue_id")
    if active in issues:
        issues[active].update(
            {key: copy.deepcopy(state.get(key, default)) for key, default in ISSUE_FIELDS.items()}
        )
    return {"issues": issues}
