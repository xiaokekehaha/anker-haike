"""物流主诉求不受附加答案字段影响；模型与后端均使用离线测试运行时。"""

import pytest

from tests.conversation_runtime import conversation as base_conversation_fixture
from tests.test_conversation_l3 import l3_runtime as l3_runtime_fixture

base_conversation = base_conversation_fixture
l3_runtime = l3_runtime_fixture


@pytest.fixture
async def conversation(l3_runtime, base_conversation):
    yield base_conversation


@pytest.mark.parametrize(
    "text,fields,expected",
    [
        pytest.param(
            "Please look into the delivery of Anker004. I previously had got one from good guys.",
            ["seller", "purchase_date"], None, id="t4-background-fields",
        ),
        pytest.param(
            "Where is my order Anker004? Receipt attached.",
            ["purchase_date"], None, id="receipt-is-background",
        ),
        pytest.param(
            "Where is my order Anker004, and how much did I pay?",
            ["logistics_status", "amount"], "Order amount:", id="mixed-amount",
        ),
        pytest.param(
            "Wo ist meine Bestellung Anker004 und wie viel habe ich bezahlt?",
            ["amount"], "Order amount:", id="mixed-german",
        ),
        pytest.param(
            "Where is Anker004, and what is the service request number?",
            ["service_order_no"], "Service request number: no confirmed record yet.", id="service-request-field",
        ),
    ],
)
async def test_logistics_obligation_survives_additional_fields(conversation, l3_runtime, text, fields, expected):
    events = await conversation.send(text, {
        "primary_intent": "logistics_query", "device_relation": "current",
        "answer_request": {"fields": fields, "quote": text},
    })
    reply = "".join(e.get("delta", "") for e in events)
    assert "Anker1234567-5: delivered on 2026-09-20" in reply
    if expected:
        assert expected in reply
    calls = [e["name"] for e in events if e["type"] == "tool_call" and e["status"] == "finished"]
    assert calls[0] == "logistics.query" and calls.count("logistics.query") == 1
    card = next(e for e in events if e["type"] == "proposal_card")
    assert [option["type"] for option in card["options"]] == ["carrier_investigation"]
    assert l3_runtime.backend.create_calls == 0
    assert not any(e["type"] == "execution_card" for e in events)


async def test_tracking_number_binds_order_before_additional_order_read(conversation, l3_runtime):
    text = "Where is my parcel Anker1234567-5, and how much did I pay?"
    order = await l3_runtime.backend.get_order("Anker004")
    events = await conversation.send(text, {
        "primary_intent": "logistics_query", "device_relation": "current",
        "answer_request": {"fields": ["amount"], "quote": text},
    })
    reply = "".join(e.get("delta", "") for e in events)
    assert "delivered on 2026-09-20" in reply
    assert f"Order amount: {order.main_line.amount}" in reply
    assert "I need the order number" not in reply
    assert l3_runtime.backend.create_calls == 0


async def test_mixed_query_preserves_an_existing_confirmation_card(conversation, l3_runtime):
    await conversation.send("Where is my order Anker004?", {
        "primary_intent": "logistics_query", "device_relation": "current",
    })
    before = await conversation.snapshot()
    assert before["pending_input"]["kind"] == "confirm_proposal"
    text = "Where is my order Anker004, and how much did I pay?"
    events = await conversation.send(text, {
        "primary_intent": "logistics_query", "device_relation": "current",
        "answer_request": {"fields": ["amount"], "quote": text},
    })
    reply = "".join(e.get("delta", "") for e in events)
    after = await conversation.snapshot()
    assert after["pending_input"]["card_id"] == before["pending_input"]["card_id"]
    assert "delivered on 2026-09-20" in reply and "Order amount:" in reply
    assert "carrier investigation" in reply
    assert not any(e["type"] == "execution_card" for e in events)
    assert l3_runtime.backend.create_calls == 0


async def test_presale_query_keeps_shipping_guidance_and_amount(conversation):
    text = "Where is my order Anker008, and how much did I pay?"
    events = await conversation.send(text, {
        "primary_intent": "logistics_query", "device_relation": "current",
        "answer_request": {"fields": ["amount"], "quote": text},
    })
    reply = "".join(e.get("delta", "") for e in events)
    assert "expected to ship on 2026-10-20" in reply and "Order amount:" in reply
    assert not any(e["type"] in {"proposal_card", "execution_card"} for e in events)


async def test_explicit_parallel_order_query_finishes_without_losing_logistics_proposal(conversation, l3_runtime):
    text = "Where is my order Anker004? How much did I pay?"
    events = await conversation.send(text, {
        "primary_intent": "logistics_query", "secondary_intents": ["order_query"], "device_relation": "current",
        "request_quotes": {"logistics_query": "Where is my order Anker004?", "order_query": "How much did I pay?"},
        "answer_request": {"fields": ["logistics_status", "amount"], "quote": text},
    })
    reply = "".join(e.get("delta", "") for e in events)
    assert "delivered on 2026-09-20" in reply and "Order amount:" in reply
    state = await conversation.state()
    # graph 将同一轮的事实查询合并到 answer_request，不应留下重复查询任务。
    assert not state["task_queue"]
    assert reply.count("Order amount:") == 1
    cards = [e for e in events if e["type"] == "proposal_card"]
    assert len(cards) == 1 and cards[0]["options"][0]["type"] == "carrier_investigation"
    assert l3_runtime.backend.create_calls == 0
