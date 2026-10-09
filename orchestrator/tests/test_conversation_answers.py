from app.conversation.answers import AnswerRequest, conversation_view, render_answer, required_reads
from app.conversation.business import BusinessContext


def test_order_facts_survive_history_and_do_not_inherit_other_case_context():
    business = BusinessContext().accept("Anker016", "a").remember({"address": "旧地址"}, "a")
    business = business.accept("Anker013", "b").observe(
        "warranty.check", {"order_no": "Anker013"},
        {"order_no": "Anker013", "data": {"sku": "T8D04121", "purchase_date": "2026-08-27", "warranty_end": "2027-08-27"}}, "b",
    ).remember({"address": "新地址", "seller": "invented"}, "c")
    state = {"business_context": business.model_dump(), "history": [], "case_order_no": "Anker016", "service_context": {"address": "旧地址"}, "product_confirmed": {"sku": "T2351"}}
    view = conversation_view(state)
    request = AnswerRequest(fields=["sku", "purchase_date", "warranty_end", "address"], quote="型号、购买日、保修和地址")
    assert required_reads(request, view) == ["warranty.check"]
    answer = render_answer(request, view)
    assert all(value in answer for value in ["T8D04121", "2026-08-27", "2027-08-27", "新地址"])
    assert "旧地址" not in answer and "T2351" not in answer
    assert conversation_view(state, "case")["fields"]["address"]["value"] == "旧地址"
    assert BusinessContext.restore(state).bind("warranty.check").params == {"order_no": "Anker013"}


def test_live_status_refresh_and_issue_facts_have_distinct_owners():
    business = BusinessContext().accept("Anker016", "a").observe(
        "logistics.query", {"order_no": "Anker016"},
        {"order_no": "Anker016", "tracking_no": "Anker1234567-19", "data": {"logistics_status": "已送达"}}, "a",
    )
    state = {"business_context": business.model_dump(), "active_issue_id": "i", "issues": {"i": {"facts": [{"kind": "symptom", "status": "active", "value": "不吸"}]}}, "case_order_no": "Anker016"}
    view = conversation_view(state)
    assert required_reads(AnswerRequest(fields=["tracking_no"], quote="单号"), view) == []
    assert required_reads(AnswerRequest(fields=["logistics_status"], quote="物流状态"), view) == ["logistics.query"]
    state["business_context"] = business.accept("Anker013", "b").model_dump()
    assert "symptoms" not in conversation_view(state)["fields"]
    assert conversation_view(state, "issue")["fields"]["symptoms"]["value"] == ["不吸"]


# ---- 第三批 I8：客户问的配件 SKU 与订单商品不一致（T47）；客户陈述与订单记录冲突（T2）----

from app.conversation.answers import record_mismatch_note


def test_hub_query_against_main_unit_order_is_not_reported_as_shipped():
    """T47：客户问 T8D02181-80 Hub，订单只有 T8D04121 整机：旧整机签收不等于 Hub 签收。"""
    note = record_mismatch_note(
        "Is there a tracking number for my shipment yet?\nSKU: T8D02181-80 (S1/S1 Pro Pump Hub Brown)\nOrder: Anker010",
        order_skus=["T8D04121"], packages=[{"tracking_no": "Anker1234567-13", "skus": ["T8D04121"], "status": "delivered"}],
    )
    assert note is not None
    assert "T8D02181-80" in note and "T8D04121" in note
    assert "don't see a separate shipment" in note
    assert "order number" in note.casefold() or "case" in note.casefold()


def test_matching_sku_has_no_note():
    assert record_mismatch_note("Where is my order Anker010? SKU: T8D04121", order_skus=["T8D04121"], packages=[]) is None
    assert record_mismatch_note("Where is my order Anker010?", order_skus=["T8D04121"], packages=[]) is None


def test_customer_package_description_conflicting_with_record_is_flagged():
    """T2：客户说 -2 是配件、-3 是主机；订单记录相反。答复要告知差异并澄清，不自动互换运单。"""
    note = record_mismatch_note(
        "I have received one package with tracking number Anker1234567-2. The package only contains the replacement accessories kit. "
        "I have not received the Eufy S1 robot vacuum yet. Tracking Anker1234567-3, UPS says label created.",
        order_skus=["T2080GA1", "T29C2001"],
        packages=[{"tracking_no": "Anker1234567-2", "skus": ["T2080GA1"], "status": "delivered", "description": "S1 Pro Omni robot vacuum"},
                  {"tracking_no": "Anker1234567-3", "skus": ["T29C2001"], "status": "delivered", "description": "S1 PRO REPLACEMENT ACCESSORY KIT"}],
    )
    assert note is not None and "Anker1234567-2" in note and "differs" in note
    assert "confirm" in note.casefold()
