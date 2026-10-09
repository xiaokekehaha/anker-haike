import json

import pytest

from app.conversation.business import BusinessContext


def known_order():
    context = BusinessContext().accept("查物流 Anker016", "1")
    return context.observe(
        "logistics.query",
        {"order_no": "Anker016"},
        {"order_no": "Anker016", "tracking_no": "Anker1234567-19"},
        "1",
    )


def test_subject_outlives_history_and_serializes_with_provenance():
    context = known_order()
    for i in range(2, 42):
        context = context.accept("谢谢，我再考虑一下", str(i))
    state = {"business_context": json.loads(context.model_dump_json()), "history": []}
    restored = BusinessContext.restore(state)
    assert restored.bind("warranty.check").params == {"order_no": "Anker016"}
    assert restored.bind("logistics.query").params["tracking_no"] == "Anker1234567-19"
    subject = restored.subjects[restored.active_subject_id]
    assert subject.identifiers["tracking_no"].source == "backend"
    assert subject.identifiers["tracking_no"].input_id == "1"


def test_new_subject_does_not_combine_old_tracking_number():
    context = known_order().accept("查物流 Anker003", "2")
    assert context.bind("logistics.query").params == {"order_no": "Anker003"}
    assert len(context.subjects) == 2


def test_explicit_other_subject_stays_missing_even_with_legacy_receipt():
    context = known_order().accept("另一笔订单", "2", {"relation": "other", "quote": "另一笔订单"})
    state = {
        "business_context": context.model_dump(),
        "receipt": {"status": "order_verified", "fields": {"order_no": "Anker016"}},
    }
    assert (
        BusinessContext.restore(state).accept("物流呢", "3").bind("logistics.query").status
        == "missing"
    )


def test_multiple_orders_need_selection_and_never_choose_first():
    context = BusinessContext().accept("查 Anker016 和 Anker003 的物流", "1")
    assert context.bind("logistics.query").status == "ambiguous"
    assert len(context.candidate_ids) == 2
    context = context.accept("先查 Anker003", "2")
    assert context.bind("warranty.check").params == {"order_no": "Anker003"}


def test_reference_requires_existing_subject_and_current_quote():
    context = known_order()
    bad_quote = context.accept("物流呢", "2", {"relation": "other", "quote": "另一笔订单"})
    assert bad_quote.active_subject_id == context.active_subject_id
    unknown = context.accept(
        "那一单", "2", {"relation": "current", "quote": "那一单", "subject_id": "invented"}
    )
    assert unknown.bind("logistics.query").status == "missing"
    assert unknown.bind("logistics.query").params == {}  # Unknown reference must not reuse the only known order.
    another = context.accept("Anker003", "2")
    restored = another.accept(
        "最初那笔",
        "3",
        {"relation": "current", "quote": "最初那笔", "subject_id": context.active_subject_id},
    )
    assert restored.bind("warranty.check").params == {"order_no": "Anker016"}


def test_input_replay_is_idempotent():
    context = known_order()
    assert context.accept("查物流 Anker016", "1") == context


def test_conflicting_backend_receipt_cannot_relink_orders():
    context = known_order()
    with pytest.raises(ValueError, match="relink"):
        context.observe(
            "logistics.query",
            {"tracking_no": "Anker1234567-19"},
            {"tracking_no": "Anker1234567-19", "order_no": "Anker003"},
            "2",
        )
    assert context.bind("warranty.check").params["order_no"] == "Anker016"


def test_receipt_confirmation_is_a_subject_observation_not_authorization():
    context = BusinessContext().observe(
        "receipt.confirm", {"order_no": "Anker099"}, {}, "1"
    )
    assert context.bind("service_order.create").params == {"order_no": "Anker099"}
    assert context.subjects[context.active_subject_id].identifiers["order_no"].source == "user"
    assert "user_confirmed" not in context.model_dump()


def test_new_state_is_authoritative_over_legacy_fields():
    context = known_order()
    restored = BusinessContext.restore(
        {
            "business_context": context.model_dump(),
            "last_consult_params": {"order_no": "Anker003"},
            "history": [{"text": "Anker003"}],
        }
    )
    assert restored == context


def test_in_flight_result_attaches_to_requested_subject_after_focus_changes():
    original = known_order()
    context = original.accept("查物流 Anker003", "2")
    focus = context.active_subject_id
    result = context.observe(
        "service_order.create",
        {"order_no": "Anker016"},
        {"order_no": "Anker016", "service_order_no": "SRV-123456ABCDEF"},
        "3",
    )
    assert result.active_subject_id == focus
    assert (
        result.subjects[original.active_subject_id].identifiers["service_order_no"].value
        == "SRV-123456ABCDEF"
    )
    assert result.bind("logistics.query").params == {"order_no": "Anker003"}
