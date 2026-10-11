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
import re
from datetime import date

from haike_contracts.common import WarrantyDecision

from app.actions.gate import EVIDENCE_LABELS, AuthorizationGate, missing_evidence
from app.actions.runtime import require_services
from app.actions.store import ExecutionBusy, ExecutionNeedsReview
from app.backends import logistics
from app.backends.protocol import BackendError
from app.cases.service import case_event
from app.conversation.answers import record_mismatch_note
from app.conversation.business import BusinessContext
from app.conversation.effects import writer
from app.conversation.quotes import quoted
from app.conversation.reduce import stable_id
from app.conversation.tasks import NOT_EXECUTABLE, REMEDY_INTENTS, settle
from app.emotion.policy import complaint_flagged
from app.escalation.summary import build_summary
from app.official.message import parse_message
from app.official.models import pn_of
from app.sessions import evidence as evidence_mod
from app.warranty.service import decide_by_dealer, decide_by_order, today

CONSULT_INTENTS = {"logistics_query", "warranty_query", "order_query"}
LOGISTICS_FIELDS = {"logistics_status", "updated_at", "carrier", "tracking_no", "order_no"}
REQUESTED_REMEDY = {"replacement_request": "replace", "refund_request": "refund",
                    "address_update": "address_update", "order_change": "order_change",
                    "parts_purchase": "parts_purchase"}
# 本系统执行不了的诉求：客户可见说明（英文，D2）与转人工摘要里的内部原因（中文）。
# 关键是不能声称已经办好 —— 订单改没改只有人工知道。
NOT_EXECUTABLE_TEXT = {
    "address_update": "Address changes need to be verified by a colleague, so I've passed your request to our team.",
    "order_change": "I can't change or hold an order myself, so I've passed your request to a colleague who can. "
                    "Please note the order may already be in process.",
    "parts_purchase": "I can't look up spare-part availability or place a parts order here, so I've passed your request "
                      "(including the part you need) to a colleague who can check it for you.",
}
NOT_EXECUTABLE_HANDOFF = {
    "address_update": "修改地址需人工核实办理",
    "order_change": "暂缓发货 / 取消 / 改购需人工办理",
    "parts_purchase": "配件采购需人工核实型号与库存",
}
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
    # reship 的理由有两条来路（退回发件人 / 在途逾期），只有看订单才知道是哪一条，
    # 所以这里不写死，由 reship_detail() 按包裹状态拼。见 logistics.RESHIP_REASON。
    "carrier_investigation": "Tracking shows the package as delivered, so under our after-sales policy we can't send another "
                             "shipment. If you really haven't received it, I can submit a carrier investigation request and a "
                             "colleague will check with the carrier.",
}
RESHIP_TAIL = " Once submitted, a colleague will arrange it."


def type_detail(kind: str, order=None, as_of_date=None) -> str:
    """方案卡上的说明。reship 的理由取决于包裹状态，查不到订单时退回通用说法。"""
    if kind != "reship":
        return TYPE_DETAILS[kind]
    if order is None or as_of_date is None:
        return logistics.RESHIP_REASON["not_delivered"] + RESHIP_TAIL
    return logistics.sop_text(order, as_of_date) + RESHIP_TAIL


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
    """客户诉求对应的服务单类型；排障升级默认是换货。

    兜底成 replace 只对「排障走不通 → 换货」这条路成立。办不了的诉求（改地址、改订单）
    没有对应服务单类型，必须在进入这里之前就被 NOT_EXECUTABLE 截住 ——
    否则会被这句兜底悄悄变成换货申请（2026-10-09 实测 order_change 走到了 warranty_replace）。
    """
    remedy = state.get("requested_remedy")
    if remedy in {"refund", "reship", "carrier_investigation"}:
        return remedy
    assert remedy not in NOT_EXECUTABLE, f"{remedy} 没有服务单类型，不该走到这里"
    return "replace"


def finish(state, route):
    """排队任务触发的办理（如物流查询转补发）走完后回到任务队列，不让任务停在进行中。"""
    return "advance_tasks" if state.get("completed_task_intent") else route


def troubleshooting_pending(state) -> bool:
    return any(t["intent"] == "report_problem" and t["status"] == "pending" for t in state.get("task_queue") or [])


def remedy_closed(state):
    """免费服务资格的结论（过保 / 非授权经销商）只结束换货退款这一项诉求。

    同一句里的排障请求仍在队列里（T51 / T53：「换货 + 电池撑不住」）：把办理任务记 done 后回到任务推进，
    由 advance_tasks 提升排障任务。以前这里直接 stage=done + commit_issue，排障任务永远 pending 而会话已结束。
    """
    active = next((t["intent"] for t in state.get("task_queue") or [] if t["status"] == "active"), None)
    intent = INTENT_OF_REMEDY.get(state.get("requested_remedy")) or active or "replacement_request"
    return {"completed_task_intent": intent, "task_outcome": "done", "l3_route": "advance_tasks"}


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
    # 本系统办不了的诉求（改地址、暂缓发货 / 取消 / 改购）到此为止，不进质保与服务单流程：
    # 它们没有对应的服务单类型，继续往下会被 requested_type 的兜底当成换货
    # （实测 order_change 一路走到 warranty_replace，还向客户要起了故障照片）。
    # 放在建 case 之后：propose 要读 case_id，提前返回会让它抛 CaseNotFound（实测客户收到空回复）。
    # 同时看 requested_remedy 与本轮意图 —— 前者只在任务队列推进时才写入，
    # 诉求作为本轮主诉求直接进来时它还是空的。
    remedy = state.get("requested_remedy")
    if remedy not in NOT_EXECUTABLE and (state.get("turn_decision") or {}).get("primary_intent") in NOT_EXECUTABLE:
        remedy = (state["turn_decision"])["primary_intent"]
    if remedy in NOT_EXECUTABLE:
        update.update(await hand_off_request({**state, "case_id": case["case_id"]}, remedy))
        return update
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
        # 「没查到订单」只有在客户真给过订单号时才成立。App 自动生成的报障表单（T14）根本没有订单号，
        # 这时说「I couldn't find an order」是假话，而且把「为什么现在谈质保」这一步跳过了：
        # 应当先说明官方指引已把这个故障判定为硬件问题、可走保修，再问订单。
        say(state, PROOF_LATER if lacks_identifier(state) else " ".join(filter(None, [
            hardware_basis(state),
            "I couldn't find that order number." if customer_gave_order_no(state)
            else "To check the warranty I'll need your order details.",
            PROOF_REQUEST,
        ])))
        update.update(escalate_reason="R6", l3_route="prepare_receipt")
        return update
    case = await services.cases.transition(
        case["case_id"], case["status"] if case["status"] != "open" else "open", "订单质保已判断",
        warranty=decision.model_dump(mode="json"),
    )
    update.update(warranty=decision.model_dump(mode="json"), l3_route="propose")
    return update


PROOF_REQUEST = (
    "Please share your order number. If you bought it from another seller, please upload your proof of "
    "purchase showing the seller name, country of purchase and purchase date."
)
# 客户已经说手上没有单号 / 凭证（B12「I don't have the order number or tracking number with me right now」、
# B17「I don't have my receipt right now. Do not submit any replacement request yet」）：逐字再要一遍等于没听见。
# 资料仍是必需的，改为说明去哪找、现在不会提交任何申请，等客户补上再继续。
# 必须同时出现单号 / 凭证类名词：T31「the robot can't get past critical low battery」不是缺资料。
IDENTIFIER_NOUN = (r"(?:receipt|invoice|proof of purchase|order (?:number|no\.?|confirmation)|tracking (?:number|no\.?)"
                   r"|bon|bonnetje|factuur|ordernummer|trackingnummer|rechnung|bestellnummer|beleg|facture|recibo|factura)")
LACKS_IDENTIFIER = re.compile(
    r"\b(?:don'?t|do not|doesn'?t|can'?t|cannot|couldn'?t)\s+(?:have|find|locate)\b[^.?!]{0,40}?\b" + IDENTIFIER_NOUN
    + r"|\bno\s+" + IDENTIFIER_NOUN + r"|\b(?:lost|threw away|misplaced)\b[^.?!]{0,20}?\b" + IDENTIFIER_NOUN
    + r"|\b(?:heb|habe|n'ai|no tengo)\b[^.?!]{0,30}?\b" + IDENTIFIER_NOUN + r"\b[^.?!]{0,20}\b(?:niet|nicht|pas)\b"
    + r"|\b" + IDENTIFIER_NOUN + r"\b[^.?!]{0,20}\b(?:kwijt|niet bij de hand)"
    + r"|没有(?:订单号?|单号|运单号?|凭证|收据|发票)|找不到(?:订单号?|单号|运单号?|凭证|收据|发票)",
    re.IGNORECASE,
)
PROOF_LATER = (
    "Understood. Without an order number or proof of purchase I can't check the warranty, so nothing will be "
    "submitted for now. The order number is in your order confirmation email or your account on the store you "
    "bought from; for another seller, a photo of the receipt or invoice works. Send it here whenever you have it "
    "and I'll continue from this point."
)
TRACKING_LATER = (
    "No problem. I can't look up the delivery without an order number or tracking number. The order number is in "
    "your order confirmation email, and the tracking number is in the shipping notification. Send either one here "
    "when you have it and I'll check the status straight away."
)


def lacks_identifier(state) -> bool:
    return bool(LACKS_IDENTIFIER.search((state.get("text") or "").replace("’", "'")))


def customer_gave_order_no(state) -> bool:
    """客户在本问题里真的给过订单号吗。没给过就不能说「没查到订单」。"""
    texts = [state.get("text", "")] + [
        e.get("text", "") for e in state.get("history") or []
        if e.get("role") == "user" and e.get("issue_id") == state.get("active_issue_id")
    ]
    return any(parse_message(t or "").order_no for t in texts)


# 走到质保判断的三条来路，各自对应一句说明为什么现在谈保修。不自己下判断：
# hardware_malfunction 是官方 Q&A 原文给的结论（rv-0028 这类 kind=warranty 条目），physical_damage 是客户自己描述的
# 可见损坏，两者由 diagnose_outcome 驱动；guide_exhausted 是官方指南走完仍未解决，或诊断树的回答走到了官方交售后结论
# （rv-0341「拆下滚刷后噪音消失」），由 decide_next 的 next_action 驱动（T19 / T36：原先只有一句索单，没说为什么转售后）。
HARDWARE_BASIS = {
    "guide_exhausted": "The official troubleshooting for this issue is complete and the problem isn't resolved, "
                       "so the next step is an after-sales review; whether it's covered by warranty depends on the check below.",
    # 只说明为什么转去售后，不先替客户确认在保（T14：「it's covered by warranty service」读起来像已确认免费）
    "hardware_malfunction": "Based on the official guidance for this error code, this is a hardware malfunction, "
                            "so the next step is an after-sales review rather than further troubleshooting; "
                            "whether it's covered by warranty depends on the check below.",
    "physical_damage": "From the damage you've described, this isn't something troubleshooting can fix, "
                       "so the next step is an after-sales review; whether it's covered by warranty depends on the check below.",
}


def hardware_basis(state) -> str | None:
    """为什么这单进了质保判断。没有明确来路时返回 None，不编理由。"""
    outcome = state.get("diagnose_outcome") or {}
    if outcome.get("mode") == "warranty":
        return HARDWARE_BASIS.get(outcome.get("reason"))
    if (state.get("next_action") or {}).get("reason") == "guide_exhausted":
        return HARDWARE_BASIS["guide_exhausted"]
    return None


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
    if case["status"] in {"closed", "closed_unresolved"}:
        say(state, "This case is closed, and the problem is not resolved. No new service request has been submitted."
            if case["status"] == "closed_unresolved"
            else "This case has already been closed. No new service request has been submitted.")
        return {**inactive_case_state(state), "stage": "done", "substage": None,
                "escalate_reason": None, "plan_cursor": None, "case_status": case["status"],
                **remedy_closed({**state, "requested_remedy": None})}
    if case["status"] not in {
        "open", "diagnosing", "proposing", "rejected", "reopened",
        "awaiting_confirmation", "tracking", "executing_failed",
    }:
        say(state, "Your case is waiting to be processed. Updates will appear in the case status.")
        return {"l3_route": "commit_issue"}
    # 本系统只能提交预定义服务单，改不了订单本身：如实说明并转人工，绝不声称已经改好。
    # 必须排在 requested_type 之前 —— 它的兜底会把这类诉求当成换货。
    if state.get("requested_remedy") in NOT_EXECUTABLE:
        return await hand_off_request(state, state["requested_remedy"])
    kind = requested_type(state)
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
            "To keep using the product, you can follow the care instructions in the user manual, or contact us about buying accessories."
            + (" I can still walk you through the official checks for this issue." if troubleshooting_pending(state) else ""),
        )
        case = await services.cases.transition(state["case_id"], "proposing", "订单已过保")
        case = await services.cases.transition(state["case_id"], "closed_unresolved", "过保，按 SOP 委婉拒绝")
        emit_case(state, case)
        return {"stage": "done", "case_status": case["status"], **remedy_closed(state)}
    if decision.status == "unauthorized_dealer":
        say(state, f"I've checked: {decision.reason}. Please contact the seller directly for after-sales support.")
        case = await services.cases.transition(state["case_id"], "proposing", "非授权经销商")
        case = await services.cases.transition(state["case_id"], "closed_unresolved", "非授权经销商，引导联系商家")
        emit_case(state, case)
        return {"stage": "done", "case_status": case["status"], **remedy_closed(state)}
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
        say(state, f"{status_line}. {logistics.sop_text(order, as_of(state))}")
        return {"stage": "consult", "l3_route": finish(state, "commit_issue")}
    # consult 已经把包裹状态告诉客户时不再复述。
    lead = "" if state.get("logistics_announced") else f"{status_line}. "
    return await _offer(state, case, kind, lead, requested=kind, order=order)


async def _offer(state, case, kind, lead, requested=None, order=None):
    services = require_services()
    detail = type_detail(kind, order, as_of(state))
    option = {"option_id": kind, "type": kind, "title": TYPE_TITLES[kind], "detail": detail, "source": "sop"}
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
    say(state, lead + detail)
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
        # 方案卡上给客户看的那句理由就在 option 里（reship 的理由按包裹状态拼过），直接沿用
        "reason": handoff_reason(state, case) if option["type"] in {"replace", "refund"} else option["detail"],
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
    return {"stage": "awaiting_human", "pending_card": None, **waiting_human(state.get("requested_remedy"))}


INTENT_OF_REMEDY = {remedy: intent for intent, remedy in REQUESTED_REMEDY.items()}


def waiting_human(remedy):
    """诉求已交人工：对应任务记 waiting_human 并回到任务推进，让排在后面的查询继续（T9 的物流）。

    等人工不等于办结 —— 任务不记 done；但机器人本轮对它已无事可做，不能让它一直 active 堵住队列。
    """
    intent = INTENT_OF_REMEDY.get(remedy)
    if intent is None:
        return {"l3_route": "commit_issue"}
    return {"completed_task_intent": intent, "task_outcome": "waiting_human", "l3_route": "advance_tasks"}


async def hand_off_request(state, remedy):
    """本系统办不了的诉求（改地址、暂缓发货 / 取消 / 改购）：先把请求持久化进人工队列，再告诉客户。

    顺序不能反：话术「已转交」必须以案件进入 awaiting_approval、记录了诉求、写了交接摘要为前提
    （2026-10-09 T9 三次复测：只说了这句话，案件仍 open、无交接，物流查询也被丢掉）。
    去重、改口、驳回后再提都在 CaseService.hand_off 里按「类型 + 原话」处理。
    交接摘要保留客户原话 —— 「if you have not shipped」这样的条件由人工核实，不由机器人改写。
    """
    quote = state.get("text") or ""

    def summary_of(row):
        summary = build_summary({**state, "requested_remedy": remedy}, reason="R6", lane=os.environ.get("MODEL_LANE", "domestic"))
        summary.reason.text = NOT_EXECUTABLE_HANDOFF[remedy] + "：" + quote
        return summary.model_dump(mode="json")

    row = await require_services().cases.hand_off(
        state["case_id"], requested=remedy, quote=quote, input_id=state["input_id"],
        reason=NOT_EXECUTABLE_HANDOFF[remedy], summary_of=summary_of,
    )
    emit_case(state, row)
    text = NOT_EXECUTABLE_TEXT[remedy]
    if remedy == "parts_purchase":
        part = (summary_of(row).get("business") or {}).get("known", {}).get("part")
        if part:
            text = text.replace("(including the part you need)", f"(the {part})")
    say(state, text)
    return {"requested_remedy": remedy, "stage": "awaiting_human", "pending_card": None, "case_status": row["status"],
            **waiting_human(remedy)}


def handoff_reason(state, row):
    """Why the case sits in the queue, in the words a desk agent reads first."""
    # 刷新摘要时沿用上一版的原因：它已经带着客户原话（「暂缓…：If you have not shipped…」），不能退化成泛泛的类型说明
    previous = next((e["payload"] for e in reversed(row["events"]) if e["type"] == "handoff_summary"), None)
    if previous and (previous.get("reason") or {}).get("text"):
        return previous["reason"]["text"]
    latest = next(
        (e["payload"]["reason"] for e in reversed(row["events"])
         if e["type"] == "status_changed" and e["payload"]["to"] == "awaiting_approval"),
        None,
    )
    if latest and latest not in {"需要人工审核", "服务单已提交，转人工处理"}:
        return latest
    remedy = state.get("requested_remedy")
    if remedy in NOT_EXECUTABLE:
        return NOT_EXECUTABLE_HANDOFF[remedy]
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
                else TRACKING_LATER if kind == "logistics.query" and lacks_identifier(state)
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
            change_pending = any(t["intent"] == "order_change" and t["status"] == "waiting_human"
                                 for t in state.get("task_queue") or [])
            logistics_note = (f"Order {order.order_no}:\n" + "\n".join("• " + logistics.describe(p) for p in order.packages)
                              + "\n" + logistics.sop_text(order, as_of(state), change_pending=change_pending))
            # 客户问的配件 / 描述的包裹内容与订单记录对不上：先说差异，不把旧整机签收当成配件已发（T47 / T2）
            mismatch = record_mismatch_note(
                state.get("text") or "", order_skus=[line.sku for line in order.lines],
                packages=[{"tracking_no": p.tracking_no, "skus": list(p.skus), "status": p.status,
                           "description": " ".join(line.description for line in order.lines if line.sku in p.skus)} for p in order.packages],
            )
            if mismatch:
                logistics_note = logistics_note.rsplit("\n", 1)[0] + "\n" + mismatch
                verdict = "mismatch"  # 不再按送达 / 补发 SOP 直接给方案，等客户确认查询对象
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
    quote = next((q for q in quotes if quoted(q, text)), None)
    if not quote:
        return None
    row = await require_services().cases.store.get(state["case_id"])
    if row["session_id"] != state["session_id"] or row["issue_id"] != state["active_issue_id"]:
        raise ValueError("案件不属于当前问题")
    if row["status"] not in {"closed", "closed_unresolved", "escalated_summary", "reopened"}:
        return None
    if eligibility_closed(row) and decision.get("primary_intent") not in REMEDY_INTENTS:
        # 案件因过保 / 非授权经销商结案，客户只是要继续排障（B15「I understand the replacement warranty has expired.
        # Please still help me troubleshoot」）：重开只会再走一遍质保、再拒一次，还把排障任务一起结束。按排障继续，不重开
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


def eligibility_closed(row) -> bool:
    """案件因免费服务资格（过保 / 非授权经销商）结案：资格结论不会因为客户再描述一次故障而改变。"""
    return row["status"] == "closed_unresolved" and (row.get("warranty") or {}).get("status") in {"out_of_warranty", "unauthorized_dealer"}


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
    requested = next((e["payload"]["requested"] for e in reversed(row["events"])
                      if e["type"] in {"review_requested", "request_changed"}), None)
    intent = INTENT_OF_REMEDY.get(requested or state.get("requested_remedy"))
    tasks = settle(state.get("task_queue") or [], intent, "pending" if decision["decision"] == "request_info" else "done") if intent else state.get("task_queue") or []
    settled = {"task_queue": tasks}
    if decision["decision"] == "approve":
        proposal = dict(row.get("proposal") or state.get("proposal") or {})
        chosen = next((o for o in proposal.get("options", []) if o["option_id"] == decision.get("option_id")), None)
        if chosen and not (row.get("external_refs") or {}).get("service_order_no"):
            # 人工批准了尚未提交的服务单（例如闸门缺证据转人工后，人工核实补齐）：按原方案提交。
            proposal.update(chosen_option_id=chosen["option_id"], user_confirmed=True, status="confirmed")
            return {**settled, "proposal": proposal, "human_request_info": False, "l3_route": "authorize"}
        return {**settled, "stage": "done", "human_request_info": False, "l3_route": "commit_issue"}
    if decision["decision"] == "reject":
        return {**settled, "stage": "done", "l3_route": "commit_issue"}
    return {**settled, "stage": "context", "human_request_info": True, "pending_card": None, "l3_route": "commit_issue"}


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
    completed_business = business.for_order(state["case_order_no"]) if state.get("case_order_no") and (decision.get("answer_scope") in {"case", "issue"} or completed in REMEDY_INTENTS) else business
    outcome = state.get("task_outcome") or "done"
    # 等人工时只继续查询类任务；排障 / 办理要等人工结论，否则会把 awaiting_human 覆盖掉（round3 P2）
    waiting = outcome == "waiting_human" or any(t["status"] == "waiting_human" for t in state.get("task_queue") or [])
    tasks, task = next_task(state.get("task_queue") or [], completed, business=completed_business,
                            task_id=decision.get("task_id"), outcome=outcome, only=CONSULT_INTENTS if waiting else None)
    update = {"task_queue": tasks, "completed_task_intent": None, "task_outcome": None}
    if completed in CONSULT_INTENTS and outcome == "done" and state.get("case_id") and state.get("case_status") == "awaiting_approval":
        # 交接已入队、查询随后才完成（T9：先交暂缓诉求，再查到预售发货日）：
        # 把后来获得的物流事实并进交接摘要；不重新入队，也不撤回人工决定。
        # 只有「已知事实」真的变了才重写，同一诉求再说一遍不会多出一条记录。
        row = await require_services().cases.store.get(state["case_id"])
        previous = next((e["payload"] for e in reversed(row["events"]) if e["type"] == "handoff_summary"), None)
        fresh = build_summary({**state, "task_queue": tasks}, reason="R6", lane=os.environ.get("MODEL_LANE", "domestic"))
        if fresh.business and (previous or {}).get("business", {}).get("known") != fresh.business.known:
            await _record_handoff({**state, "task_queue": tasks}, row)
    if task:
        say(state, "Next up: " + LABELS[task["intent"]] + ".")
        update.update(
            text=task["quote"],
            business_context=task_business(task, business).model_dump(mode="json"),
            turn_decision={**state.get("turn_decision", {}), "primary_intent": task["intent"], "secondary_intents": [], "task_id": task["task_id"], "answer_request": task.get("answer_request"), "answer_scope": task.get("answer_scope", "focus"), "clarification": None},
            l3_route="consult"
            if task["intent"] in CONSULT_INTENTS
            else "await_input"
            if task["intent"] == "report_problem" and state.get("pending_card")
            else "disambiguate"
            if task["intent"] == "report_problem"
            else "service_context",
        )
        if task["intent"] in REMEDY_INTENTS:
            update["requested_remedy"] = REQUESTED_REMEDY[task["intent"]]
        elif task["intent"] == "report_problem":
            # 换货诉求已办结（过保 / 非授权）再推进排障：清掉 requested_remedy，否则 _after_product 会把排障
            # 又送回 service_context，对已关闭的案件说「waiting to be processed」（T51 / T53 复测）。
            update["requested_remedy"] = None
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
