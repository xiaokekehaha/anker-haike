"""One read contract for factual questions, independent of workflow advancement.

Facts remain with their owners. The view resolves scope before exposing values;
answer requests name fields, never supply values or authorize an action.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.conversation.business import BusinessContext
from app.conversation.operation_conditions import feedback_history

AnswerField = Literal[
    "order_no", "tracking_no", "service_order_no", "sku",
    "purchase_date", "amount", "address", "serial_number", "seller", "country",
    "logistics_status", "carrier", "updated_at", "warranty_end",
    "symptoms", "steps_executed", "case_status", "proposal",
]


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: list[AnswerField] = Field(min_length=1, max_length=20)
    quote: str


LABELS = {
    "order_no": "订单号", "tracking_no": "物流单号", "service_order_no": "服务单号",
    "sku": "产品型号", "purchase_date": "购买日期", "amount": "订单金额",
    "address": "收货地址", "serial_number": "产品 SN", "seller": "购买商家", "country": "购买国家",
    "logistics_status": "物流状态",
    "carrier": "承运商", "updated_at": "更新时间", "warranty_end": "保修截止日期",
    "symptoms": "已报告现象", "steps_executed": "已反馈的排查步骤",
    "case_status": "案件状态", "proposal": "当前方案",
}
FACTUAL_INTENTS = {"logistics_query", "order_query", "warranty_query", "history_query", "explain", "supplement", "unknown", "answer_pending"}
ORDER_FIELDS = {"sku", "purchase_date", "amount"}
LOGISTICS_FIELDS = {"tracking_no", "service_order_no", "logistics_status", "carrier", "updated_at"}


def request_of(state):
    raw = (state.get("turn_decision") or {}).get("answer_request")
    return AnswerRequest.model_validate(raw) if raw else None


def _fact(value, source, input_id=None):
    return {"value": value, "source": source, "input_id": input_id}


def conversation_view(state, scope="focus"):
    business = BusinessContext.restore(state)
    case_order = state.get("case_order_no")
    if scope in {"case", "issue"} and case_order:
        business = business.for_order(case_order)
    subject = business.subjects.get(business.active_subject_id)
    focus_order = subject.identifiers.get("order_no").value if subject and subject.identifiers.get("order_no") else None
    # Diagnostic state belongs to the active issue, never to a different queried order.
    issue_matches = (not case_order and not subject and business.status != "ambiguous") or (case_order is not None and focus_order == case_order)
    fields = {k: v.model_dump() for k, v in {**subject.facts, **subject.identifiers}.items()} if subject else {}
    if scope == "issue" or issue_matches:
        context = state.get("service_context") or {}
        sources = state.get("context_sources") or {}
        for key, value in context.items():
            if value and key not in fields:
                fields[key] = _fact(value, sources.get(key, "legacy"))
        if not fields.get("sku") and (state.get("product_confirmed") or {}).get("sku"):
            fields["sku"] = _fact(state["product_confirmed"]["sku"], "confirmed_product")
        issue = (state.get("issues") or {}).get(state.get("active_issue_id"), {})
        symptoms = [f["value"] for f in issue.get("facts", []) if f.get("kind") == "symptom" and f.get("status") == "active"]
        if symptoms:
            fields["symptoms"] = _fact(symptoms, "user_report")
        steps = [{"title": s.get("title"), "feedback": s.get("feedback"), "note": s.get("note")} for s in feedback_history(state)]
        if steps:
            fields["steps_executed"] = _fact(steps, "user_feedback")
        if state.get("case_status"):
            fields["case_status"] = _fact(state["case_status"], "case")
        proposal = state.get("proposal") or {}
        if proposal:
            fields["proposal"] = _fact({"status": proposal.get("status"), "options": [o.get("title") or o.get("remedy") for o in proposal.get("options", [])]}, "case")
    return {"scope": scope, "status": business.status, "order_no": focus_order, "issue_matches_focus": issue_matches, "fields": fields}


def required_reads(request, view):
    """Static known values survive history eviction; live status always refreshes."""
    fields = set(request.fields)
    known = view["fields"]
    reads = []
    if "warranty_end" in fields or any(f not in known for f in fields & ORDER_FIELDS):
        reads.append("warranty.check")
    if "logistics_status" in fields or "updated_at" in fields or any(f not in known for f in fields & LOGISTICS_FIELDS):
        reads.append("logistics.query")
    return reads


def render_answer(request, view):
    if view["status"] == "ambiguous":
        return "涉及多个订单，请明确要查询哪一个订单。"
    lines = []
    fields = list(dict.fromkeys(request.fields))
    if "logistics_status" in fields and "updated_at" not in fields:
        fields.append("updated_at")
    for field in fields:
        fact = view["fields"].get(field)
        if not fact:
            lines.append(f"{LABELS[field]}：当前对象尚无已确认记录。")
            continue
        value = fact["value"]
        if field == "steps_executed":
            value = "；".join(f"{s['title'] or '排查步骤'}（反馈：{s['feedback'] or '未提供'}{('，' + s['note']) if s.get('note') else ''}）" for s in value)
        elif field == "proposal":
            value = f"{value.get('status') or '待确认'}，可选方案：{'、'.join(filter(None, value['options']))}"
        elif isinstance(value, list):
            value = "；".join(value)
        source = {"backend": "订单系统", "user": "您提供的信息", "user_report": "您的报告", "receipt": "已核实订单"}.get(fact["source"])
        lines.append(f"{LABELS[field]}：{value}" + (f"（来源：{source}）" if source else "") + "。")
    prefix = f"订单 {view['order_no']}：\n" if view.get("order_no") and "order_no" not in request.fields else ""
    return prefix + "\n".join(lines)
