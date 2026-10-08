"""L3 graph nodes, following the organizer's after-sales SOP.

    物流：查订单包裹 → 送达不补发（可提交承运商调查）/ 未送达且未收到 → 补发单 / 预售告知发货日
    故障：排障未解决 → 确认进入换货 / 退款 → 订单质保判断
          查不到订单 → 核实购买商家 → 授权经销（12 个月）/ 未授权 → 引导联系商家售后
          保内 → 补齐 SOP 证据 → 提交服务单 → 转人工
          过保 → 告知质保信息并委婉拒绝
服务单只是提交给售后工具，提交后一律转人工（主办方不提供订单 / 工单接口）。
"""

import hashlib
import json
import os
from datetime import date

from haike_contracts.common import WarrantyDecision

from app.actions.gate import EVIDENCE_LABELS, AuthorizationGate, missing_evidence
from app.actions.runtime import require_services
from app.actions.store import ExecutionBusy, ExecutionNeedsReview
from app.backends import logistics
from app.backends.protocol import BackendError
from app.cases.service import case_event
from app.conversation.business import BusinessContext
from app.conversation.effects import writer
from app.conversation.reduce import stable_id
from app.emotion.policy import complaint_flagged
from app.escalation.summary import build_summary
from app.official.message import parse_message
from app.official.models import pn_of
from app.sessions import evidence as evidence_mod
from app.warranty.service import decide_by_dealer, decide_by_order, today

CONSULT_INTENTS = {"logistics_query", "warranty_query", "order_query"}
LOGISTICS_FIELDS = {"logistics_status", "updated_at", "carrier", "tracking_no", "order_no"}
REQUESTED_REMEDY = {"replacement_request": "replace", "refund_request": "refund", "address_update": "address_update"}
TYPE_NAMES = {
    "replace": "replacement request",
    "refund": "refund request",
    "reship": "reship request",
    "carrier_investigation": "carrier investigation request",
}
TYPE_TITLES = {kind: "Submit a " + name for kind, name in TYPE_NAMES.items()}
# 人工交接记录（内部）用的中文单据名。
TYPE_NAMES_ZH = {"replace": "换货单", "refund": "退款单", "reship": "补发单", "carrier_investigation": "承运商调查单"}
TYPE_DETAILS = {
    "replace": "The fault is still not resolved after troubleshooting and the product is under warranty, so under our "
               "after-sales policy it qualifies for a replacement. Once submitted, a colleague will review it and arrange the shipment.",
    "refund": "The product is under warranty, so you can request a refund. Once submitted, a colleague will review and process it.",
    "reship": "Tracking doesn't show the package as delivered, so under our after-sales policy we can reship it to you. "
              "Once submitted, a colleague will arrange it.",
    "carrier_investigation": "Tracking shows the package as delivered, so under our after-sales policy we can't send another "
                             "shipment. If you really haven't received it, I can submit a carrier investigation request and a "
                             "colleague will check with the carrier.",
}


def say(state, text):
    mid = stable_id(state["input_id"], "l3", text)
    emit = writer()
    emit(
        {
            "type": "message_start",
            "message_id": mid,
            "issue_id": state.get("active_issue_id"),
            "reply_to_input_id": state["input_id"],
        }
    )
    emit({"type": "message", "message_id": mid, "delta": text})
    emit({"type": "message_end", "message_id": mid, "status": "completed"})


def pending(state, kind, payload):
    return {"kind": kind, "card_id": stable_id(state["input_id"], kind), "payload": payload}


def emit_case(state, row, reason="案件状态更新"):
    writer()(
        case_event(
            row, issue_id=state["active_issue_id"], version=state["base_version"] + 1, reason=reason
        )
    )


def as_of(state) -> date:
    return today(state.get("at"))


def requested_type(state) -> str:
    """客户诉求对应的服务单类型；排障升级默认是换货。"""
    remedy = state.get("requested_remedy")
    if remedy in {"refund", "reship", "carrier_investigation"}:
        return remedy
    return "replace"


def finish(state, route):
    """排队任务触发的办理（如物流查询转补发）走完后回到任务队列，不让任务停在进行中。"""
    return "advance_tasks" if state.get("completed_task_intent") else route


def warranty_of(state) -> WarrantyDecision | None:
    raw = state.get("warranty")
    return WarrantyDecision.model_validate(raw) if raw else None


async def service_context(state):
    """查订单、判断质保。没有订单号就收凭证（凭证上的商家与国家用来查经销商名录）。"""
    services = require_services()
    writer()({"type": "progress", "stage": "context"})
    product_update = {}
    receipt = dict(state.get("receipt") or {})
    business = BusinessContext.restore(state)
    workflow = business.for_order(state["case_order_no"]) if state.get("case_order_no") else business
    business.subjects.update(workflow.subjects)
    binding = workflow.bind("warranty.check")
    order_no = binding.params.get("order_no") or (receipt.get("verified_facts") or {}).get("order_no")
    order = None
    if order_no:
        try:
            order = await services.backend.get_order(order_no)
            business = business.observe(
                "warranty.check", {"order_no": order.order_no} if binding.params.get("order_no") else {},
                {"order_no": order.order_no, "data": order_facts(order)}, state["input_id"],
            ) if binding.params.get("order_no") else business
        except BackendError as error:
            say(state, error.user_message)
    if order is not None:
        if state.get("product_state") != "confirmed_sku":
            from app.sessions.cards import get_catalog

            product = get_catalog().get(pn_of(order.main_line.sku) or order.main_line.sku)
            if product and product.in_scope:
                product_update = {
                    "product_confirmed": product.to_candidate().model_dump(mode="json"),
                    "product_state": "confirmed_sku",
                    "category": product.category,
                }
        receipt.update(
            status="order_verified",
            fields={**receipt.get("fields", {}), "order_no": order.order_no},
            verified_facts={"order_no": order.order_no, "purchase_date": order.purchase_date.isoformat(),
                            "address": " ".join(order.address.split())},
        )
    product = product_update.get("product_confirmed") or state.get("product_confirmed") or {}
    case = await services.cases.open(state["session_id"], state["active_issue_id"], product, complaint_flagged(state))
    if not case.get("sku") and product_update.get("product_confirmed"):
        case = await services.cases.identify_product(case["case_id"], product_update["product_confirmed"])
    if order is not None:
        case = await services.cases.bind_order(case["case_id"], order.order_no)
    update = {
        "business_context": business.model_dump(mode="json"),
        **product_update,
        "case_id": case["case_id"],
        "case_order_no": (case.get("external_refs") or {}).get("order_no"),
        "receipt": receipt,
        "stage": "context",
        "escalate_reason": None,
    }
    emit_case(state, case)
    if binding.status == "ambiguous":
        say(state, "This involves more than one order. Please tell me which order number you'd like me to handle.")
        update.update(l3_route="commit_issue", pending_card=None)
        return update
    kind = requested_type(state)
    if kind in {"reship", "carrier_investigation"}:
        update["l3_route"] = "propose" if order is not None else finish(state, "commit_issue")
        if order is None:
            say(state, "Please share your order number or tracking number, and I'll check the delivery status first.")
        return update
    if order is not None:
        decision = decide_by_order(order, product.get("sku"), as_of(state))
    elif receipt.get("status") in {"dealer_authorized", "dealer_unauthorized", "insufficient", "needs_manual_check"}:
        fields = receipt.get("fields") or {}
        try:
            purchase = date.fromisoformat(fields.get("purchase_date") or "")
        except ValueError:
            purchase = None
        decision = decide_by_dealer(fields.get("seller"), fields.get("country"), purchase, as_of(state))
    elif (stated := stated_dealer(state)) is not None:
        # 首封表单里写了购买商家与国家（T45：Ordered from the reseller Aeroflow，Country: US）：先按名录判断
        decision = stated
        if decision.status == "unknown":
            say(state, f"I've checked: {decision.reason}. Please upload your proof of purchase (the purchase date must be visible) "
                     "so I can confirm whether it's within the 12-month warranty.")
            update.update(escalate_reason="R6", l3_route="prepare_receipt", warranty=decision.model_dump(mode="json"))
            return update
    elif receipt.get("skipped_reason"):
        decision = WarrantyDecision(status="unknown", basis="none", as_of=as_of(state), reason="no order or proof of purchase was provided")
    else:
        say(state, "I couldn't find an order. Please share your order number. If you bought it from another seller, please "
                   "upload your proof of purchase showing the seller name, country of purchase and purchase date.")
        update.update(escalate_reason="R6", l3_route="prepare_receipt")
        return update
    case = await services.cases.transition(
        case["case_id"], case["status"] if case["status"] != "open" else "open", "订单质保已判断",
        warranty=decision.model_dump(mode="json"),
    )
    update.update(warranty=decision.model_dump(mode="json"), l3_route="propose")
    return update


def stated_dealer(state) -> WarrantyDecision | None:
    """客户在本问题首封里自述的购买商家与国家 → 经销商名录判定；两者缺一返回 None（走凭证收集）。"""
    texts = [state.get("text", "")] + [
        e.get("text", "") for e in state.get("history") or []
        if e.get("role") == "user" and e.get("issue_id") == state.get("active_issue_id")
    ]
    for text in texts:
        parsed = parse_message(text or "")
        if parsed.seller and parsed.country:
            return decide_by_dealer(parsed.seller, parsed.country, None, as_of(state))
    return None


def order_facts(order) -> dict:
    line = order.main_line
    return {
        "sku": line.sku,
        "purchase_date": order.purchase_date.isoformat(),
        "warranty_end": line.warranty_end.isoformat() if line.warranty_end else None,
        "amount": line.amount,
    }


async def propose(state):
    services = require_services()
    writer()({"type": "progress", "stage": "propose"})
    case = await services.cases.store.get(state["case_id"])
    if case["status"] in {"approved", "awaiting_approval"} and (requested := changed_request(state, case)):
        return await _pause_for_changed_request(state, requested)
    if case["status"] not in {
        "open", "diagnosing", "proposing", "rejected", "reopened",
        "awaiting_confirmation", "tracking", "executing_failed",
    }:
        say(state, "Your case is waiting to be processed. Updates will appear in the case status.")
        return {"l3_route": "commit_issue"}
    kind = requested_type(state)
    if state.get("requested_remedy") == "address_update":
        say(state, "Address changes need to be verified by a colleague, so I've passed your request to our team.")
        return {"stage": "propose", "l3_route": "await_human"}
    if kind in {"reship", "carrier_investigation"}:
        return await _propose_logistics(state, case, kind)
    decision = warranty_of(state)
    if decision is None or decision.status == "unknown":
        say(state, "I can't confirm the warranty status yet (" + (decision.reason if decision else "order details are missing")
            + "), so I've passed the details to a colleague to check.")
        case = await services.cases.transition(state["case_id"], "escalated_summary", "质保状态无法确认")
        emit_case(state, case)
        return {"stage": "propose", "l3_route": "summarize", "escalate_reason": "R6"}
    if decision.status == "out_of_warranty":
        say(
            state,
            f"I've checked: {decision.reason}. The warranty has expired (as of {decision.as_of.isoformat()}). "
            "I'm sorry, we can't offer a free replacement or refund for products that are out of warranty. "
            "To keep using the product, you can follow the care instructions in the user manual, or contact us about buying accessories.",
        )
        case = await services.cases.transition(state["case_id"], "proposing", "订单已过保")
        case = await services.cases.transition(state["case_id"], "closed_unresolved", "过保，按 SOP 委婉拒绝")
        emit_case(state, case)
        return {"stage": "done", "case_status": case["status"], "l3_route": "commit_issue"}
    if decision.status == "unauthorized_dealer":
        say(state, f"I've checked: {decision.reason}. Please contact the seller directly for after-sales support.")
        case = await services.cases.transition(state["case_id"], "proposing", "非授权经销商")
        case = await services.cases.transition(state["case_id"], "closed_unresolved", "非授权经销商，引导联系商家")
        emit_case(state, case)
        return {"stage": "done", "case_status": case["status"], "l3_route": "commit_issue"}
    return await _offer(state, case, kind, f"I've checked: {decision.reason}. ")


async def _propose_logistics(state, case, kind):
    services = require_services()
    order = await services.backend.get_order(state["case_order_no"])
    verdict = logistics.verdict(order, as_of(state))
    pkg = logistics.main_package(order)
    status_line = logistics.describe(pkg) if pkg else "No package record found"
    if kind == "reship" and verdict == "delivered":
        kind = "carrier_investigation"
    if kind == "carrier_investigation" and verdict == "reship_eligible":
        kind = "reship"
    if (kind == "reship" and verdict != "reship_eligible") or (kind == "carrier_investigation" and verdict != "delivered"):
        say(state, f"{status_line}. {logistics.SOP_TEXT[verdict]}")
        return {"stage": "consult", "l3_route": finish(state, "commit_issue")}
    # consult 已经把包裹状态告诉客户时不再复述。
    lead = "" if state.get("logistics_announced") else f"{status_line}. "
    return await _offer(state, case, kind, lead, requested=kind)


async def _offer(state, case, kind, lead, requested=None):
    services = require_services()
    option = {"option_id": kind, "type": kind, "title": TYPE_TITLES[kind], "detail": TYPE_DETAILS[kind], "source": "sop"}
    proposal = {"options": [option], "status": "offered", "excluded": [], "chosen_option_id": None, "user_confirmed": False}
    have = evidence_mod.collect(state)
    missing = missing_evidence(kind, have)
    if case["status"] != "proposing":
        case = await services.cases.transition(state["case_id"], "proposing", "按 SOP 生成服务单方案", proposal=proposal)
    update = {"proposal": proposal, "stage": "propose", "human_request_info": False, "escalate_reason": None,
              "sop_evidence": have, **({"requested_remedy": requested} if requested else {})}
    if missing:
        labels = ", ".join(EVIDENCE_LABELS[m] for m in missing)
        say(state, f"{lead}Before I can submit the {TYPE_NAMES[kind]}, I still need: {labels}. "
                   "Please upload photos or videos here, and reply with the other details.")
        case = await services.cases.transition(state["case_id"], "awaiting_confirmation", "等待补充 SOP 证据", proposal=proposal)
        emit_case(state, case)
        update["l3_route"] = finish(state, "commit_issue")
        update["awaiting_evidence"] = missing
        return update
    case = await services.cases.transition(state["case_id"], "awaiting_confirmation", "等待客户确认提交", proposal=proposal)
    emit_case(state, case)
    say(state, lead + TYPE_DETAILS[kind])
    update.update(
        awaiting_evidence=[],
        pending_card=pending(state, "confirm_proposal", {"options": [option], "decision_summary": lead.strip().rstrip(".")}),
        l3_route=finish(state, "await_input"),
    )
    return update


def changed_request(state, case):
    """A remedy asked on a message turn that the pending approval does not cover."""
    requested = REQUESTED_REMEDY.get((state.get("turn_decision") or {}).get("primary_intent"))
    if state.get("entry") != "message" or not requested:
        return None
    decided_at = max((d["at"] for d in case["decisions"]), default="")
    latest = next(
        (
            e["payload"]["requested"]
            for e in reversed(case["events"])
            if e["type"] in {"review_requested", "request_changed"} and e["at"] > decided_at
        ),
        None,
    )
    covered = latest or case.get("chosen_option_id") or (case.get("proposal") or {}).get("chosen_option_id")
    return None if requested == covered else requested


async def _pause_for_changed_request(state, requested):
    row = await require_services().cases.request_changed(
        state["case_id"], input_id=state["input_id"], quote=state.get("text", ""), requested=requested
    )
    row = await _record_handoff(
        {**state, "requested_remedy": requested}, row, "客户变更诉求：" + (state.get("text") or "")
    )
    pc = state.get("pending_card")
    if pc:
        writer()({"type": "pending_changed", "issue_id": state["active_issue_id"],
                  "pending_id": pc["card_id"], "status": "invalidated", "reason": "request_changed",
                  "version": state["base_version"] + 1})
    emit_case(state, row, "客户变更诉求")
    say(state, "I've paused the original plan. Your new request has been passed to a colleague for review, and the result will come back to this conversation.")
    return {**inactive_case_state(state), "requested_remedy": requested, "case_status": row["status"],
            "stage": "awaiting_human", "l3_route": "commit_issue"}


async def authorize(state):
    services = require_services()
    case = await services.cases.store.get(state["case_id"])
    proposal = state.get("proposal") or {}
    option = next((o for o in proposal.get("options", []) if o["option_id"] == proposal.get("chosen_option_id")), None)
    if not option:
        say(state, "This option needs to be handled by a colleague, so I've submitted it for review.")
        return {"l3_route": "await_human"}
    key = f"{state['case_id']}:service_order.create:{option['option_id']}"
    old = await services.executor.store.get(key)
    if old and old["status"] == "succeeded":
        return {"l3_route": "execute", "execution_key": key, "gate_result": old["gate_result"]}
    logistics_ok = False
    if option["type"] in {"reship", "carrier_investigation"} and state.get("case_order_no"):
        order = await services.backend.get_order(state["case_order_no"])
        verdict = logistics.verdict(order, as_of(state))
        logistics_ok = verdict == ("reship_eligible" if option["type"] == "reship" else "delivered")
    gate = AuthorizationGate().check(
        kind=option["type"],
        warranty=warranty_of(state),
        logistics_ok=logistics_ok,
        evidence=evidence_mod.collect(state),
        risk_cases=state.get("risk_cases") or [],
        allowed_operations=(state.get("turn_decision") or {}).get("allowed_operations", False),
        user_confirmed=proposal.get("user_confirmed", False),
        case_status=case["status"],
        execution_status=old["status"] if old else None,
    )
    await services.cases.transition(
        state["case_id"], case["status"], "提交闸门已检查",
        gate_result=gate.model_dump(), chosen_option_id=option["option_id"], proposal=proposal,
    )
    return {"gate_result": gate.model_dump(), "execution_key": key, "l3_route": "execute" if gate.passed else "await_human"}


async def execute(state):
    from haike_contracts.common import GateResult

    services = require_services()
    writer()({"type": "progress", "stage": "execute"})
    case = await services.cases.store.get(state["case_id"])
    if case["status"] != "tracking":
        case = await services.cases.transition(state["case_id"], "executing", "已通过闸门，正在提交服务单")
    emit_case(state, case)
    proposal = state["proposal"]
    option = next(o for o in proposal["options"] if o["option_id"] == proposal["chosen_option_id"])
    params = {
        "type": option["type"],
        "order_no": state.get("case_order_no"),
        "sku": (state.get("product_confirmed") or {}).get("sku"),
        "reason": handoff_reason(state, case) if option["type"] in {"replace", "refund"} else TYPE_DETAILS[option["type"]],
        "evidence": evidence_mod.collect(state),
    }
    params = {k: v for k, v in params.items() if v is not None}
    try:
        result = await services.executor.run(
            "service_order.create",
            params,
            idempotency_key=state["execution_key"],
            session_id=state["session_id"],
            run_id=state["run_id"],
            case_id=state["case_id"],
            issue_id=state["active_issue_id"],
            gate_result=GateResult.model_validate(state["gate_result"]),
            writer=writer(),
        )
    except ExecutionNeedsReview:
        return await _outcome_needs_review(state, "We can't confirm the result of this submission yet. To avoid a duplicate request, I've passed it to a colleague to check.")
    except ExecutionBusy:
        say(state, "The same request is still being processed. Please check the case status a little later.")
        return {"l3_route": "commit_issue"}
    writer()(
        {
            "type": "execution_card",
            "card_id": result.execution_id,
            "version": state["base_version"] + 1,
            "execution_id": result.execution_id,
            "action_kind": "service_order.create",
            "status": result.status,
            "receipt": result.receipt.model_dump(mode="json"),
            "idempotency_key": state["execution_key"],
        }
    )
    execution = {
        "execution_id": result.execution_id,
        "status": result.status,
        "receipt": result.receipt.model_dump(mode="json"),
        "idempotency_key": state["execution_key"],
        "action_kind": "service_order.create",
    }
    if result.status != "succeeded":
        if result.needs_review:
            return {"execution": execution, **await _outcome_needs_review(state, result.receipt.next_step)}
        say(state, result.receipt.next_step)
        if result.recoverable:
            case = await services.cases.transition(state["case_id"], "executing_failed", "售后工具暂时不可用，可重试原申请")
            emit_case(state, case)
            retry = dict(proposal)
            retry.update(status="offered", chosen_option_id=None, user_confirmed=False)
            say(state, "This submission didn't go through. You can retry the original request or ask for help from a colleague; retrying won't create a duplicate service request.")
            return {
                "execution": execution, "case_status": case["status"], "proposal": retry, "stage": "propose",
                "pending_card": pending(state, "confirm_proposal", {
                    "options": [option], "retry": True,
                    "decision_summary": "Our after-sales tool is temporarily unavailable. Please retry the original request or choose help from a colleague.",
                }),
                "l3_route": "await_input",
            }
        return {"execution": execution, "l3_route": "await_human"}
    case = await services.cases.attach_execution(state["case_id"], execution["receipt"])
    case = await services.cases.record_commitment(state["case_id"], execution["receipt"]["next_step"], "receipt")
    case = await services.cases.transition(state["case_id"], "awaiting_approval", "服务单已提交，转人工处理")
    case = await _record_handoff(state, case, f"{TYPE_NAMES_ZH[option['type']]}已提交：{execution['receipt'].get('service_order_no')}")
    emit_case(state, case)
    return {
        "execution": execution,
        "stage": "awaiting_human",
        "case_status": case["status"],
        "pending_card": pending(state, "rate_satisfaction", {"case_id": state["case_id"]}),
        "completed_task_intent": "replacement_request",
        "l3_route": "advance_tasks",
    }


async def _outcome_needs_review(state, text):
    case = await require_services().cases.transition(state["case_id"], "awaiting_approval", "执行结果待人工核实")
    emit_case(state, case)
    say(state, text)
    return {"l3_route": "await_human"}


async def track(state):
    services = require_services()
    case = await services.cases.store.get(state["case_id"])
    number = case.get("external_refs", {}).get("service_order_no")
    if number:
        try:
            order = await services.backend.get_service_order(number)
            status = {
                "submitted": "submitted, waiting for a colleague to process it",
                "in_review": "being processed by a colleague",
                "completed": "completed",
                "rejected": "not approved",
            }[order.status]
            say(state, f"Service request {number} status: {status}.")
        except BackendError as error:
            say(state, error.user_message)
    else:
        say(state, "No service request has been submitted for this case yet.")
    return {"stage": state.get("stage", "track"), "l3_route": "advance_tasks", "completed_task_intent": "confirm_received"}


async def await_human(state):
    services = require_services()
    row = await services.cases.transition(
        state["case_id"],
        "awaiting_approval",
        "需要人工审核",
        warranty=state.get("warranty"),
        proposal=state.get("proposal"),
        gate_result=state.get("gate_result"),
        complaint_risk=complaint_flagged(state),
        priority="high" if complaint_flagged(state) else "normal",
    )
    if state.get("requested_remedy"):
        row = await services.cases.record_review_request(state["case_id"], state["requested_remedy"])
    row = await _record_handoff(state, row)
    emit_case(state, row)
    say(state, "I've submitted this for review by a colleague. The decision will come back to this conversation, and you can keep adding information here.")
    return {"stage": "awaiting_human", "pending_card": None, "l3_route": "commit_issue"}


def handoff_reason(state, row):
    """Why the case sits in the queue, in the words a desk agent reads first."""
    latest = next(
        (e["payload"]["reason"] for e in reversed(row["events"])
         if e["type"] == "status_changed" and e["payload"]["to"] == "awaiting_approval"),
        None,
    )
    if latest and latest not in {"需要人工审核", "服务单已提交，转人工处理"}:
        return latest
    remedy = state.get("requested_remedy")
    if remedy == "address_update":
        return "修改地址需人工核实办理"
    failed = [c["detail"] for c in (state.get("gate_result") or {}).get("checks", []) if not c.get("passed")]
    if failed:
        return "提交条件未满足：" + "；".join(failed)
    warranty = state.get("warranty") or {}
    symptoms = [f["value"] for f in ((state.get("issues") or {}).get(state.get("active_issue_id"), {}).get("facts") or [])
                if f.get("kind") == "symptom" and f.get("status") == "active"]
    parts = [warranty.get("reason"), "；".join(symptoms) or None]
    return "；".join(p for p in parts if p) or "需要人工审核"


async def _record_handoff(state, row, reason=None):
    summary = build_summary(dict(state), reason="R6", lane=os.environ.get("MODEL_LANE", "domestic"))
    summary.reason.text = reason or handoff_reason(state, row)
    return await require_services().cases.record_handoff(state["case_id"], summary.model_dump(mode="json"))


async def consult(state):
    from app.conversation.answers import (
        AnswerRequest,
        conversation_view,
        render_answer,
        request_of,
        required_reads,
    )

    services = require_services()
    decision = state.get("turn_decision") or {}
    intent = decision.get("primary_intent")
    if intent not in CONSULT_INTENTS:
        intent = state.get("consult_intent") or intent
    request = request_of(state)
    scope = decision.get("answer_scope", "focus")
    if request is None:
        fields = {
            "logistics_query": ["logistics_status"],
            "order_query": ["order_no", "sku", "purchase_date"],
            "warranty_query": ["purchase_date", "warranty_end"],
        }.get(intent, ["order_no"])
        request = AnswerRequest(fields=fields, quote=state.get("text", ""))
    business = BusinessContext.restore(state)
    workflow = business.for_order(state["case_order_no"]) if scope in {"case", "issue"} and state.get("case_order_no") else business
    business.subjects.update(workflow.subjects)
    view = conversation_view(state, scope)
    reads = required_reads(request, view)
    if intent == "logistics_query" and set(request.fields) <= LOGISTICS_FIELDS:
        # 模型给物流问题附带的字段请求（订单号 / 物流单号 / 状态）不改变诉求：仍按物流 SOP 查包裹并给方案（T5 实测）
        reads = ["logistics.query"]
    if view["status"] == "ambiguous":
        reads = reads or ["warranty.check"]
    logistics_note = ""
    offer = None
    for kind in reads:
        binding = workflow.bind(kind)
        if binding.status != "ready":
            attempts = (state.get("consult_attempts") or 0) + 1
            say(
                state,
                "This involves more than one order. Please tell me which order number you'd like me to check."
                if binding.status == "ambiguous"
                else "Please share your order number or tracking number and I'll look it up."
                if kind == "logistics.query"
                else "I need the order number to look up this order information.",
            )
            return {
                "consult_intent": intent, "consult_attempts": attempts,
                "stage": state.get("stage", "consult") if state.get("pending_card") else "consult",
                "l3_route": "commit_issue" if attempts < 3 else "summarize",
                "escalate_reason": None if attempts < 3 else "R7",
            }
        params = binding.params
        writer()({"type": "progress", "stage": "consult"})
        key = f"{state['session_id']}:{state['input_id']}:{kind}:" + hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]
        result = await services.executor.run(
            kind, params, idempotency_key=key, session_id=state["session_id"],
            run_id=state["run_id"], issue_id=state["active_issue_id"], writer=writer(), as_of=as_of(state),
        )
        if result.status != "succeeded":
            say(state, result.receipt.next_step)
            return {"business_context": business.model_dump(mode="json"), "consult_intent": intent, "l3_route": "commit_issue"}
        receipt = result.receipt.model_dump(mode="json")
        if kind == "logistics.query" and receipt["status"] == "packages":
            order = await services.backend.get_order(receipt["order_no"])
            verdict = logistics.verdict(order, as_of(state))
            logistics_note = f"Order {order.order_no}:\n" + "\n".join("• " + logistics.describe(p) for p in order.packages) + "\n" + logistics.SOP_TEXT[verdict]
            if intent == "logistics_query" and verdict in {"reship_eligible", "delivered"}:
                # 物流工单的典型诉求就是「没收到」（主办方 11 单全部如此）：直接按 SOP 给出补发 / 承运商调查方案，客户可暂不办理。
                offer = "reship" if verdict == "reship_eligible" else "carrier_investigation"
            receipt = {**receipt, "data": {**order_facts(order), "logistics_status": logistics.STATUS_TEXT[logistics.main_package(order).status]}}
        elif kind == "warranty.check":
            order = await services.backend.get_order(receipt["order_no"])
            receipt = {**receipt, "data": order_facts(order)}
        business = business.observe(kind, params, receipt, state["input_id"])
        workflow = business.for_order(state["case_order_no"]) if scope in {"case", "issue"} and state.get("case_order_no") else business
    view = conversation_view({**state, "business_context": business.model_dump(mode="json")}, scope)
    case_update = {}
    if "case_status" in request.fields and state.get("case_id") and (view["issue_matches_focus"] or scope in {"case", "issue"}):
        case = await services.cases.store.get(state["case_id"])
        if case:
            case_update["case_status"] = case["status"]
            view["fields"]["case_status"] = {"value": case["status"], "source": "case"}
    logistics_only = bool(logistics_note) and set(request.fields) <= LOGISTICS_FIELDS
    if offer and logistics_only and not state.get("pending_card"):
        say(state, logistics_note.rsplit("\n", 1)[0])
        return {
            **case_update,
            "business_context": business.model_dump(mode="json"),
            "consult_intent": None, "consult_attempts": 0,
            "requested_remedy": offer, "logistics_announced": True,
            "completed_task_intent": intent, "l3_route": "service_context",
        }
    say(state, logistics_note if logistics_only else render_answer(request, view))
    return {
        **case_update,
        "business_context": business.model_dump(mode="json"),
        "stage": state.get("stage", "done") if state.get("pending_card") or state.get("case_id") else "done",
        "consult_intent": None, "consult_attempts": 0,
        "consult_answered": not state.get("pending_card"),
        "completed_task_intent": intent, "l3_route": "advance_tasks",
    }


async def apply_l3_action(state, action, pc):
    payload = action.get("payload") or {}
    kind = action["kind"]
    results = dict(state.get("card_results") or {})
    update = {"pending_card": None, "last_action": None, "escalate_reason": None}
    if kind == "confirm_proposal":
        proposal = {**state["proposal"], "chosen_option_id": payload["option_id"], "status": "confirmed", "user_confirmed": True}
        results[pc["card_id"]] = {"chosen_option_id": payload["option_id"]}
        update.update(proposal=proposal, l3_route="authorize")
    elif kind == "decline_proposal":
        results[pc["card_id"]] = {"declined_reason": payload["reason"]}
        update.update(
            proposal={**state["proposal"], "status": "declined"},
            l3_route={"want_other": "await_human", "not_now": "commit_issue", "request_human": "await_human"}[payload["reason"]],
        )
    elif kind == "rate_satisfaction":
        await require_services().cases.rate(
            state["session_id"], state["active_issue_id"], payload["score"], payload.get("comment"), state.get("case_id"),
        )
        results[pc["card_id"]] = {"score": payload["score"]}
        say(state, "Thank you for your feedback. You can check your case progress at any time.")
        update["l3_route"] = "commit_issue"
    elif kind == "skip_retake":
        results[pc["card_id"]] = {"skipped": True}
        # 回到消歧：读图在产品确认之前发生（T55 首封带图），跳过补拍后产品仍可能未确认，直接检索会因无查询而中断。
        # 图片已记为处理过，消歧不会再次读图。
        update.update(retake_skipped=True, l3_route="disambiguate")
    update["card_results"] = results
    return update


def route(state):
    return state.get("l3_route") or "commit_issue"


async def understand_human(state):
    from copy import deepcopy

    from app.conversation.reduce import ISSUE_FIELDS

    source = state.get("last_action") or {}
    row = await require_services().cases.store.get(source["case_id"])
    if row["session_id"] != state["session_id"] or row["issue_id"] != source.get("target_issue_id"):
        raise ValueError("审批输入与案件不匹配")
    decision = next(
        (d for d in row["decisions"] if d["decision_id"] == source.get("decision_id")), None
    )
    if decision is None and state.get("entry") != "case_command":
        raise ValueError("审批决定不存在")
    issues = deepcopy(state.get("issues") or {})
    if row["issue_id"] not in issues:
        raise ValueError("案件问题已不可恢复")
    if state.get("active_issue_id") in issues:
        issues[state["active_issue_id"]].update(
            {k: deepcopy(state.get(k, v)) for k, v in ISSUE_FIELDS.items()}
        )
    issue = issues[row["issue_id"]]
    update = {k: deepcopy(issue.get(k, v)) for k, v in ISSUE_FIELDS.items()}
    allowed = not any(
        r.get("status") == "reported" and r.get("rule_id") == "R4"
        for r in state.get("risk_cases", [])
    )
    update.update(
        active_issue_id=row["issue_id"],
        issues=issues,
        human_decision_id=decision["decision_id"] if decision else None,
        case_id=row["case_id"],
        l3_route=None,
        turn_decision={
            "primary_intent": state["entry"],
            "allowed_operations": allowed,
            "reply_mode": "business",
            "pending_changes": [],
        },
    )
    writer()(
        {
            "type": "issue_changed",
            "active_issue_id": row["issue_id"],
            "issues": [
                {"issue_id": k, "title": v.get("title", ""), "status": v.get("status", "open")}
                for k, v in issues.items()
            ],
            "input_id": state["input_id"],
            "resolved_issue_id": row["issue_id"],
            "version": state["base_version"] + 1,
        }
    )
    return update


async def reopening_request(state, meaning):
    """Bind a current unresolved report to the existing case before routing it."""
    if state.get("entry") != "message" or not state.get("case_id"):
        return None
    decision = state.get("turn_decision") or {}
    if decision.get("business_ambiguous") or decision.get("primary_intent") not in {
        "report_problem", "step_feedback", "answer_pending", "correct", "complaint",
        "unknown", "replacement_request", "refund_request",
    }:
        return None
    text = state.get("text", "")
    quotes = [meaning.unresolved_quote]
    if meaning.feedback == "not_solved":
        quotes.append(meaning.feedback_quote)
    if meaning.primary_intent == "report_problem":
        quotes.extend(f.quote for f in meaning.facts if f.kind in {"symptom", "observation"})
    quote = next((q for q in quotes if q and q.strip() and q in text), None)
    if not quote:
        return None
    row = await require_services().cases.store.get(state["case_id"])
    if row["session_id"] != state["session_id"] or row["issue_id"] != state["active_issue_id"]:
        raise ValueError("案件不属于当前问题")
    if row["status"] not in {"closed", "closed_unresolved", "escalated_summary", "reopened"}:
        return None
    business = BusinessContext.restore(state)
    binding = business.bind("warranty.check")
    order_no = row.get("external_refs", {}).get("order_no")
    scope = decision.get("answer_scope")
    if scope not in {"case", "issue"} and (
        business.status == "ambiguous" or (order_no and binding.params.get("order_no") not in {None, order_no})
        or (meaning.business_reference and meaning.business_reference.relation == "other")
    ):
        return {"clarification": "Please confirm whether the unresolved problem is with your original after-sales case, "
                                 "or with the other order you just asked about."}
    return {"case_id": row["case_id"], "expected_revision": row["revision"], "quote": quote,
            "transition": row["status"] != "reopened"}


def inactive_case_state(state):
    proposal = dict(state.get("proposal") or {})
    if proposal:
        proposal.update(user_confirmed=False, chosen_option_id=None, status="inactive")
    return {"pending_card": None, "last_action": None, "proposal": proposal,
            "human_request_info": False, "human_decision_id": None, "requested_remedy": None}


async def reopen_case(state):
    request = state["turn_decision"]["reopen_request"]
    services = require_services()
    row = await services.cases.reopen(state["case_id"], expected_revision=request["expected_revision"],
                                     input_id=state["input_id"], quote=request["quote"]) if request["transition"] else await services.cases.store.get(state["case_id"])
    pc = state.get("pending_card")
    if pc:
        writer()({"type": "pending_changed", "issue_id": state["active_issue_id"],
                  "pending_id": pc["card_id"], "status": "invalidated", "reason": "case_reopened",
                  "version": state["base_version"] + 1})
    emit_case(state, row, "继续处理未解决的问题")
    say(state, "I've reopened your original case and kept the previous order and handling records. Next, I'll re-check which option applies.")
    intent = state["turn_decision"]["primary_intent"]
    return {**inactive_case_state(state), "case_status": row["status"],
            "requested_remedy": {"replacement_request": "replace", "refund_request": "refund"}.get(intent),
            "l3_route": "escalate" if state["turn_decision"].get("escalation_trigger") else "service_context"}


async def apply_case_command(state):
    source = state["last_action"]
    row = await require_services().cases.manual_action(
        state["case_id"], source["command"], command_id=state["input_id"],
        actor=source["actor"], expected_revision=source["expected_revision"],
    )
    pc = state.get("pending_card")
    if pc:
        writer()({"type": "pending_changed", "issue_id": state["active_issue_id"],
                  "pending_id": pc["card_id"], "status": "invalidated",
                  "reason": "case_" + source["command"], "version": state["base_version"] + 1})
    emit_case(state, row, "人工结案" if source["command"] == "close" else "人工重新受理")
    say(
        state,
        "A colleague has closed this case. You can still view its history; if the problem persists, please tell me more."
        if source["command"] == "close"
        else "A colleague has reopened this case. Please describe what still needs to be handled. "
        "Before anything is submitted, I'll re-check the options and ask for your confirmation.",
    )
    return {**inactive_case_state(state), "case_status": row["status"], "stage": "done",
            "l3_route": "commit_issue"}




async def apply_human_decision(state):
    """人工处理结论回到会话：通过 = 服务单由人工办结；驳回 = 告知原因；要求补充 = 等客户补充。"""
    services = require_services()
    row = await services.cases.consume_decision(state["case_id"], state["human_decision_id"], state["input_id"])
    decision = next(d for d in row["decisions"] if d["decision_id"] == state["human_decision_id"])
    emit_case(state, row)
    say(state, "Reply from our team: " + decision["note"])
    if decision["decision"] == "approve":
        proposal = dict(row.get("proposal") or state.get("proposal") or {})
        chosen = next((o for o in proposal.get("options", []) if o["option_id"] == decision.get("option_id")), None)
        if chosen and not (row.get("external_refs") or {}).get("service_order_no"):
            # 人工批准了尚未提交的服务单（例如闸门缺证据转人工后，人工核实补齐）：按原方案提交。
            proposal.update(chosen_option_id=chosen["option_id"], user_confirmed=True, status="confirmed")
            return {"proposal": proposal, "human_request_info": False, "l3_route": "authorize"}
        return {"stage": "done", "human_request_info": False, "l3_route": "commit_issue"}
    if decision["decision"] == "reject":
        return {"stage": "done", "l3_route": "commit_issue"}
    return {"stage": "context", "human_request_info": True, "pending_card": None, "l3_route": "commit_issue"}


async def prepare_retake(state):
    count = (state.get("retake_attempts") or 0) + 1
    if count > 2:
        say(state, "The photo still can't be read clearly, so I'll pass the details to a colleague to check.")
        return {
            "retake_attempts": count,
            "pending_card": None,
            "escalate_reason": "R7",
            "l3_route": "summarize",
        }
    quality = state.get("image_quality") or {}
    return {
        "retake_attempts": count,
        "clarification": {"reason": "image", "attempts": count, "asked_run_id": state["run_id"]},
        "pending_card": pending(
            state,
            "upload_retake",
            {
                "reasons": quality.get("reasons", []),
                "guidance": quality.get("guidance", []) or ["Please take a focused photo of the faulty part of the device."],
            },
        ),
        "l3_route": "await_input",
    }


async def vision_conflict(state):
    say(
        state,
        "The photo and your description don't quite match. Please confirm: "
        + "; ".join((state.get("fault_localization") or {}).get("conflicts_with_text", [])),
    )
    return {
        "pending_card": None,
        "clarification": {"reason": "conflict", "attempts": 1, "asked_run_id": state["run_id"]},
    }


async def advance_tasks(state):
    from app.conversation.tasks import LABELS, next_task, task_business

    completed = state.get("completed_task_intent") or "report_problem"
    business = BusinessContext.restore(state)
    decision = state.get("turn_decision") or {}
    completed_business = business.for_order(state["case_order_no"]) if state.get("case_order_no") and (decision.get("answer_scope") in {"case", "issue"} or completed in {"replacement_request", "refund_request", "address_update"}) else business
    tasks, task = next_task(state.get("task_queue") or [], completed, business=completed_business, task_id=decision.get("task_id"))
    update = {"task_queue": tasks, "completed_task_intent": None}
    if task:
        say(state, "Next up: " + LABELS[task["intent"]] + ".")
        update.update(
            text=task["quote"],
            business_context=task_business(task, business).model_dump(mode="json"),
            turn_decision={**state.get("turn_decision", {}), "primary_intent": task["intent"], "secondary_intents": [], "task_id": task["task_id"], "answer_request": None, "answer_scope": "focus", "clarification": None},
            l3_route="consult"
            if task["intent"] in CONSULT_INTENTS
            else "await_input"
            if task["intent"] == "report_problem" and state.get("pending_card")
            else "disambiguate"
            if task["intent"] == "report_problem"
            else "service_context",
        )
        if task["intent"] in {"replacement_request", "refund_request", "address_update"}:
            update["requested_remedy"] = {"replacement_request": "replace", "refund_request": "refund", "address_update": "address_update"}[task["intent"]]
        writer()(
            {
                "type": "issue_changed",
                "active_issue_id": state["active_issue_id"],
                "issues": [
                    {
                        "issue_id": key,
                        "title": issue.get("title", ""),
                        "status": issue.get("status", "open"),
                        "task_queue": tasks
                        if key == state["active_issue_id"]
                        else issue.get("task_queue", []),
                    }
                    for key, issue in state["issues"].items()
                ],
                "input_id": state["input_id"],
                "resolved_issue_id": state["active_issue_id"],
                "version": state["base_version"] + 1,
            }
        )
    else:
        update["l3_route"] = "await_input" if state.get("pending_card") else "commit_issue"
        if (
            state.get("stage") == "done"
            and not state.get("case_id")
            and not state.get("consult_answered")
            and not state.get("pending_card")
        ):
            update.update(
                pending_card=pending(state, "rate_satisfaction", {"case_id": None}),
                l3_route="await_input",
            )
    return update
