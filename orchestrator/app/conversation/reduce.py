"""Validate semantic proposals against explicit sources; preserve issue-local state."""

from __future__ import annotations

import copy
import re
import uuid

from app.conversation.interpret import TurnInterpretation
from app.conversation.operation_conditions import (
    effective_exhausted,
    resolve_operation_reply,
    update_conditions,
)
from app.conversation.quotes import normalize, quoted
from app.official.message import parse_message

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
    # intake 给的英文现象描述，只参与检索（官方 Q&A 是英文，T43 西语「desconectado」与英文条目没有词面交集）；
    # 不是事实，不进摘要和适用性判断
    "search_query_en": None,
    "unparsed_problem": None,
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
    "displayed_knowledge_nodes": [],
    "step_attempts": [],
    "step_checks": {},
    # 客户答过的候选前提追问：{plan_id, missing_fact, question, answer, input_id}。答过就是证据，同一前提不再问
    "precondition_answers": [],
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


def device_message_spans(text: str) -> list[str]:
    """首封表单里由设备 / App 写出的句子：推送提示与问题描述字段。

    T11：「Click to contact customer service for assistance」出现在 Problem Push 里，是错误码附带的固定文案。
    引文落在这些字段里说明是设备在说话，不能当作用户自己的请求；作为故障现象仍然有效。
    """
    fields = parse_message(text or "").fields
    spans = []
    for key in ("push", "description"):
        value = (fields.get(key) or "").strip()
        if not value:
            continue
        norm = normalize(value)
        if any(norm in normalize(s) or normalize(s) in norm for s in spans):
            continue
        spans.append(value)
    return spans


def quote_source(quote: str | None, spans: list[str]) -> str:
    return "device_message" if quote and any(normalize(quote) in normalize(span) for span in spans) else "user_statement"


SAFETY_CONFIRM_QUESTION = (
    "Before we continue, I need to check one thing for your safety: is there any smoke, burning smell, "
    "visible swelling of the battery, leaking liquid, or is the device too hot to touch? Please reply yes or no."
)


def _unconfirmed_risk(risks: list[dict], target: str | None) -> dict | None:
    return next((r for r in risks if r.get("status") == "unconfirmed" and r.get("issue_id") in {None, target}), None)


def answers_pending_step(meaning: TurnInterpretation, pending: dict | None, text: str) -> bool:
    """本轮是否在回答当前步骤卡：反馈或问句回答，且引文出自本轮原话。"""
    if not pending or pending.get("kind") != "step_feedback":
        return False
    answer = meaning.pending_answer
    if answer is not None and answer.kind == "step_answer":
        return bool(quoted(answer.quote, text))
    return meaning.feedback is not None and bool(quoted(meaning.feedback_quote, text))


_CODE_OR_MODEL = re.compile(r"\b(?:T\d{4}[A-Z0-9]*|T8D\d+|E[0-9A-Z]{1,3}|EB[0-9A-Z]{1,2}|\d{4})\b")


def search_query_en(meaning: TurnInterpretation, text: str) -> str | None:
    """本轮报告了现象时的英文检索描述；不允许出现原文没有的型号 / 错误码（检索范围与精确命中另有来源，凭空的码会把检索带偏）。
    没有现象的轮次返回 None，保留上一轮的描述。"""
    english = " ".join((meaning.search_query_en or "").split())
    if not english or not any(f.kind == "symptom" for f in meaning.facts):
        return None
    source = text.upper()
    if any(token.upper() not in source for token in _CODE_OR_MODEL.findall(english)):
        return None
    return english[:160]


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
    spans = device_message_spans(text)
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
    candidates = list(meaning.facts)
    parsed = parse_message(text)
    grounded_symptoms = [candidate for candidate in candidates if candidate.kind == "symptom" and quoted(candidate.quote, text)]
    if grounded_symptoms and issue.get("unparsed_problem"):
        issue["unparsed_problem"] = {**issue["unparsed_problem"], "status": "interpreted", "interpreted_by_input_id": iid}
    if (
        meaning.primary_intent == "report_problem"
        and state.get("entry") != "action"
        and parsed.format in {"app_report", "rma"}
        and parsed.description
        and not grounded_symptoms
        and not meaning.corrections
    ):
        # 原文证据和语义事实是两层：解析未完成不代表用户“不确定”。
        issue["unparsed_problem"] = {"text": parsed.description, "source_entry_ids": [iid], "status": "unparsed"}
    for index, candidate in enumerate(candidates):
        if not quoted(candidate.quote, text):
            continue
        previous = next((f for f in facts if f["value"] == candidate.value
                         and f["kind"] == candidate.kind and f["status"] == "active"), None)
        if previous:
            if previous.get("polarity") != "uncertain" or candidate.polarity == "uncertain":
                continue
            # 新的、有本轮引文支持的明确事实可确认原先不确定的记录；保留旧版本来源。
            previous["status"] = "superseded"
            previous["superseded_by_input_id"] = iid
        fact = {
            "fact_id": stable_id(iid, "add", index),
            "kind": candidate.kind,
            "context_field": candidate.context_field,
            "value": candidate.value,
            "issue_id": target,
            "device_ref_id": issue["device_ref"]["device_ref_id"],
            "status": "active",
            "revision": previous["revision"] + 1 if previous else 1,
            "source_kind": "user_report",
            "source": quote_source(candidate.quote, spans),
            "subject": candidate.subject,
            "polarity": candidate.polarity,
            "timing": candidate.timing,
            "source_entry_ids": [iid],
            "recorded_at": at,
            "occurred_at": candidate.occurred_at,
            "time_expression": candidate.time_expression,
            "precision": candidate.precision,
            "quote": candidate.quote,
        }
        if previous:
            fact["supersedes"] = previous["fact_id"]
        facts.append(fact)
        applied.append({"op": "replace" if previous else "add",
                        "fact_id": previous["fact_id"] if previous else fact["fact_id"], "input_id": iid})
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
    corrected = bool(product_corrected or any(p["op"] in {"replace", "retract"} for p in applied))
    basis_changed = bool(
        corrected
        or any(f["fact_id"] in changed_ids and f["kind"] == "symptom" for f in facts)
    )
    # 先承接再撤卡（2026-10-10 多轮复现 T22 / T46）：本轮有引文支持的回答指向当前步骤卡时，同句新增的现象
    # 不撤这张卡，回答由 resolve_command 提交、verify 写进 step_attempts；新现象照常进事实。纠正旧记录仍撤卡。
    keeps_card = not corrected and answers_pending_step(meaning, issue.get("pending_card"), text)
    if basis_changed and issue.get("pending_card") and not keeps_card:
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
    if (english := search_query_en(meaning, text)) is not None:
        issue["search_query_en"] = english
    elif applied:
        # 本轮只更正了事实、没报新现象：旧的英文描述是按更正前的事实写的，作废；下一轮有现象再生成
        issue["search_query_en"] = None
    # 否定句（「没有冒烟」「no suction loss」）是反证，不是现象：留在 facts 里供摘要与适用性核对，不进症状。
    issue["symptoms"] = [
        f["value"] for f in facts
        if f["status"] == "active" and f["kind"] == "symptom" and f.get("polarity", "affirmed") != "negated"
    ]
    issue["observations"] = [
        f["value"] for f in facts if f["status"] == "active" and f["kind"] == "observation"
    ]
    operation_proposal, operation_clarification = resolve_operation_reply(text, issue)
    operation_proposal = operation_proposal or meaning.operation_update
    # 「despite wiping clean the electrical connections」是已做过的排查（action_taken），不是操作条件变了（T31）。
    # 同一段原话既被抽成已做操作又被当成 operation_update 时，以事实为准，不触发 reassess。
    if operation_proposal is not None and any(
        f.kind == "action_taken" and f.quote and (
            normalize(operation_proposal.quote) in normalize(f.quote) or normalize(f.quote) in normalize(operation_proposal.quote)
        )
        for f in meaning.facts
    ):
        operation_proposal = None
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
    # R4 语义门（2026-10-10）：模型标 reported 且原话存在，只证明「客户说过这句话」，不证明它是物理危险。
    # T23 第十轮：设备推送「E41: Battery abnormal」被当成安全事件。与 R3 同一模式——引文落在设备字段里不算用户报告；
    # 用户自己写的但词表没命中，先问一句封闭式确认（期间暂停动作），确认再升级；词表命中仍立即 R4，保护不降。
    claimed = meaning.device_safety_assertion == "reported" and quoted(meaning.device_safety_quote, text)
    claim_source = quote_source(meaning.device_safety_quote, spans) if claimed else None
    validated_negation = meaning.device_safety_assertion == "negated" and bool(
        quoted(meaning.device_safety_quote, text)
    )
    pending = _unconfirmed_risk(risks, target)
    new_risk = (precheck_risk and not validated_negation) or (claimed and claim_source == "user_statement" and pending is not None)
    unconfirmed_claim = claimed and claim_source == "user_statement" and not new_risk
    if unconfirmed_claim:
        clarify = clarify or SAFETY_CONFIRM_QUESTION
    if pending is not None and (new_risk or validated_negation):
        pending["status"] = "reported" if new_risk else "cleared"
        pending.setdefault("source_input_ids", []).append(iid)
    elif new_risk or unconfirmed_claim:
        risk_target = target if new_device or meaning.device_relation == "current" else None
        risks.append(
            {
                "risk_id": stable_id(iid, "risk"),
                "rule_id": "R4",
                "status": "reported" if new_risk else "unconfirmed",
                "source_input_ids": [iid],
                "reported_at": at,
                "issue_id": risk_target,
                "device_ref_id": issue["device_ref"]["device_ref_id"] if risk_target else None,
                "restriction": "no_operations",
                "policy_version": "2026-10-10",
                "last_evidence_seq": state.get("input_seq"),
                **({"quote": meaning.device_safety_quote} if claimed else {}),
            }
        )
    uncertain_risk = False
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
        r["status"] in {"reported", "disputed", "unconfirmed"}
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
    human_request_source = None
    if intent == "request_human" and state.get("entry") != "action":
        in_text = quoted(meaning.human_request_quote, text)
        if in_text and quote_source(meaning.human_request_quote, spans) == "user_statement":
            human_request_source = "user_statement"
        elif in_text and (parse_codes(text) or any(c.kind == "symptom" for c in meaning.facts)):
            # 引文确实在原文里，但落在设备推送字段（T11 的「Click to contact customer service」），
            # 而这封消息报的是故障：这是一条故障求助，按排障处理。
            intent = "report_problem"
        else:
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
        "human_request_source": human_request_source,
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


def parse_codes(text: str) -> tuple[str, ...]:
    return parse_message(text or "").codes


def persist_issue(state: dict) -> dict:
    issues = copy.deepcopy(state.get("issues") or {})
    active = state.get("active_issue_id")
    if active in issues:
        issues[active].update(
            {key: copy.deepcopy(state.get(key, default)) for key, default in ISSUE_FIELDS.items()}
        )
    return {"issues": issues}
