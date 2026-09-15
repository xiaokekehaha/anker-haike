from app.conversation.answers import AnswerRequest, conversation_view, render_answer, required_reads
from app.conversation.business import BusinessContext


def test_order_facts_survive_history_and_do_not_inherit_other_case_context():
    business = BusinessContext().accept("DEMO-X10-001", "a").remember({"region_use": "中国"}, "a")
    business = business.accept("DEMO-CN-003", "b").observe(
        "warranty.check", {"order_no": "DEMO-CN-003"},
        {"order_no": "DEMO-CN-003", "data": {"sku": "B-MODEL", "channel": "official", "purchase_date": "2026-09-01"}}, "b",
    ).remember({"region_use": "德国", "channel": "invented"}, "c")
    state = {"business_context": business.model_dump(), "history": [], "case_order_no": "DEMO-X10-001", "service_context": {"region_use": "中国"}, "product_confirmed": {"sku": "A-MODEL"}}
    view = conversation_view(state)
    request = AnswerRequest(fields=["sku", "channel", "purchase_date", "region_use"], quote="型号、渠道、购买日和使用地")
    assert required_reads(request, view) == []
    answer = render_answer(request, view)
    assert all(value in answer for value in ["B-MODEL", "official", "2026-09-01", "德国"])
    assert "中国" not in answer and "invented" not in answer and "A-MODEL" not in answer
    assert conversation_view(state, "case")["fields"]["region_use"]["value"] == "中国"
    assert BusinessContext.restore(state).bind("warranty.check").params == {"order_no": "DEMO-CN-003"}


def test_live_status_refresh_and_issue_facts_have_distinct_owners():
    business = BusinessContext().accept("DEMO-X10-001", "a").observe(
        "logistics.query", {"order_no": "DEMO-X10-001"},
        {"order_no": "DEMO-X10-001", "tracking_no": "TRACK-123456", "data": {"status": "shipped"}}, "a",
    )
    state = {"business_context": business.model_dump(), "active_issue_id": "i", "issues": {"i": {"facts": [{"kind": "symptom", "status": "active", "value": "不吸尘"}]}}, "case_order_no": "DEMO-X10-001"}
    view = conversation_view(state)
    assert required_reads(AnswerRequest(fields=["tracking_no"], quote="单号"), view) == []
    assert required_reads(AnswerRequest(fields=["logistics_status"], quote="物流状态"), view) == ["logistics.query"]
    state["business_context"] = business.accept("DEMO-CN-003", "b").model_dump()
    assert "symptoms" not in conversation_view(state)["fields"]
    assert conversation_view(state, "issue")["fields"]["symptoms"]["value"] == ["不吸尘"]
