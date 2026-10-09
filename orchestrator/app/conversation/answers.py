"""One read contract for factual questions, independent of workflow advancement.

Facts remain with their owners. The view resolves scope before exposing values;
answer requests name fields, never supply values or authorize an action.
"""
import re
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
    "order_no": "Order number", "tracking_no": "Tracking number", "service_order_no": "Service request number",
    "sku": "Product model", "purchase_date": "Purchase date", "amount": "Order amount",
    "address": "Shipping address", "serial_number": "Serial number (SN)", "seller": "Seller", "country": "Country of purchase",
    "logistics_status": "Delivery status",
    "carrier": "Carrier", "updated_at": "Last updated", "warranty_end": "Warranty end date",
    "symptoms": "Reported symptoms", "steps_executed": "Troubleshooting steps you tried",
    "case_status": "Case status", "proposal": "Current option",
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
        return "I couldn't identify which order you mean. Please share the order number you'd like me to check."
    lines = []
    fields = list(dict.fromkeys(request.fields))
    if "logistics_status" in fields and "updated_at" not in fields:
        fields.append("updated_at")
    for field in fields:
        fact = view["fields"].get(field)
        if not fact:
            lines.append(f"{LABELS[field]}: no confirmed record yet.")
            continue
        value = fact["value"]
        if field == "steps_executed":
            value = "; ".join(f"{s['title'] or 'Troubleshooting step'} (result: {s['feedback'] or 'not provided'}{(', ' + s['note']) if s.get('note') else ''})" for s in value)
        elif field == "proposal":
            value = f"{value.get('status') or 'pending'}, options: {', '.join(filter(None, value['options']))}"
        elif isinstance(value, list):
            value = "; ".join(value)
        source = {"backend": "order system", "user": "information you provided", "user_report": "your report", "receipt": "verified order"}.get(fact["source"])
        lines.append(f"{LABELS[field]}: {value}" + (f" (source: {source})" if source else "") + ".")
    prefix = f"Order {view['order_no']}:\n" if view.get("order_no") and "order_no" not in request.fields else ""
    return prefix + "\n".join(lines)


# ---- 第三批 I8：客户说的与订单记录不一致时的注记（T47 / T2）----
# 客户消息里的商品编码：SKU: T8D02181-80 / T8D04121 / T2080GA1 这类主办方编码
_SKU_IN_TEXT = re.compile(r"\b(T8D\d{2}[A-Z0-9-]{0,8}|T\d{4}[A-Z0-9]{0,6})\b")
_TRACKING = re.compile(r"\b(Anker\d{7}-\d+)\b")
_MAIN_WORDS = ("robot vacuum", "robot", "vacuum", "main unit", "machine", "pump itself")
_ACCESSORY_WORDS = ("accessor", "kit", "filter", "brush", "part", "hub", "spare")


def _family(sku: str) -> str:
    return sku.upper()[:5]


def record_mismatch_note(text: str, *, order_skus: list[str], packages: list[dict]) -> str | None:
    """客户问的东西和订单记录对不上时，答复里先说清楚差异，不把旧记录当成客户问的那件事。

    T47：客户问 Hub（T8D02181-80）的运单，订单只有整机 T8D04121 的旧包裹 —— 旧整机签收不等于 Hub 已发。
    T2：客户说 -2 是配件、-3 是主机，订单记录相反 —— 两条记录照答，差异告知并请客户确认实际收到的商品。
    7.1 复核：这两种都不是官方数据错误，是查询对象 / 来源冲突，不能自动互换或推定。
    """
    low = text.casefold()
    asked = [m.group(1) for m in _SKU_IN_TEXT.finditer(text)]
    known = {sku.upper() for sku in order_skus}
    foreign = [sku for sku in dict.fromkeys(asked) if sku.upper() not in known and not any(k.startswith(sku.upper()) or sku.upper().startswith(k) for k in known)]
    if foreign:
        sku = foreign[0]
        same_family = next((k for k in known if _family(k) == _family(sku.upper())), None)
        on_record = ", ".join(sorted(known))
        return (
            f"The order record shows {on_record}" + (" (main unit)" if same_family else "") + f"; I don't see a separate shipment for {sku}. "
            "If this part came from a separate order or a service replacement, please share that order number or case number and I'll check it."
        )
    # 客户描述某条运单装的是什么，与记录里该运单的商品类别相反。只看运单号所在的那一两句，
    # 否则一封信里两条运单互相串味（T2 两条运单各带「accessories kit」与「robot vacuum」）。
    sentences = re.split(r"(?<=[.!?])\s+", low)
    for match in _TRACKING.finditer(text):
        tracking = match.group(1)
        pkg = next((p for p in packages if p.get("tracking_no") == tracking), None)
        if not pkg:
            continue
        idx = next((i for i, sent in enumerate(sentences) if tracking.casefold() in sent), None)
        if idx is None:
            continue
        window = " ".join(sentences[idx: idx + 2])
        says_accessory = any(w in window for w in _ACCESSORY_WORDS) and "only contains" in window or ("accessor" in window and "received" in window and "not received" not in window)
        desc = (pkg.get("description") or " ".join(pkg.get("skus") or [])).casefold()
        record_accessory = any(w in desc for w in _ACCESSORY_WORDS)
        record_main = any(w in desc for w in _MAIN_WORDS) or not record_accessory
        if says_accessory and record_main:
            return (
                f"Our record for {tracking} differs from what you received: it is listed as the main unit, while you mention the accessory kit. "
                "I've kept both records as they are; please confirm which item each package contained (the label on the box helps) so a colleague can check with the carrier."
            )
    return None
