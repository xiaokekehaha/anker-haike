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
