"""Independent requests need source evidence; internal lookups are not requests."""

import pytest

import app.conversation.interpret as semantic
from app.conversation.answers import AnswerRequest
from app.conversation.business import BusinessContext
from app.conversation.interpret import TurnInterpretation
from app.conversation.request_constraints import constrain_requests, ground_additional_queries
from app.conversation.tasks import enqueue
from app.sessions import graph
from tests.conversation_runtime import conversation as conversation_fixture
from tests.test_conversation_l3 import l3_runtime as l3_runtime_fixture

conversation = conversation_fixture
l3_runtime = l3_runtime_fixture


@pytest.mark.parametrize("text,quote,reason", [
    ("My robot is offline. Order No: Anker001", "", "request_quote_missing"),
    ("My robot is offline.", "When will it arrive?", "request_quote_ungrounded"),
    ("Product PN: T2351\nOrder No: Anker001\nProblem Description: Robot offline.", "Anker001", "metadata_is_not_request"),
    ("Problem Type: Warranty\nProblem Description: Robot offline.", "Warranty", "metadata_is_not_request"),
    ("Check my warranty please.", "Never check my warranty please", "request_quote_ungrounded"),
])
def test_metadata_missing_and_ungrounded_quotes_cannot_create_a_query(text, quote, reason):
    meaning = TurnInterpretation(primary_intent="report_problem", secondary_intents=["warranty_query"],
                                 request_quotes={"warranty_query": quote})
    result, rejected = ground_additional_queries(meaning, text)
    assert not result.secondary_intents
    assert rejected == [{"intent": "warranty_query", "reason": reason}]


def test_identical_primary_and_secondary_quotes_are_not_independent_requests():
    text = "When will my order arrive?"
    result, rejected = ground_additional_queries(TurnInterpretation(
        primary_intent="logistics_query", secondary_intents=["order_query"],
        request_quotes={"logistics_query": text, "order_query": text}), text)
    assert not result.secondary_intents and rejected[0]["reason"] == "duplicate_request_quote"


@pytest.mark.parametrize("primary,quote", [
    ("order_change", "tell me its shipping date"),
    ("report_problem", "is there an update on their arrival?"),
    ("report_problem", "When does my warranty end?"),
    ("report_problem", "What was the purchase date?"),
])
def test_independent_queries_preserve_their_quote_and_business_binding(primary, quote):
    intent = "warranty_query" if "warranty" in quote else "order_query" if "purchase" in quote else "logistics_query"
    text = f"Order No: Anker008\nProblem Description: Robot is offline. Also, {quote}"
    fields = ["warranty_end"] if intent == "warranty_query" else ["purchase_date"] if intent == "order_query" else ["logistics_status"]
    answer = AnswerRequest(fields=fields, quote=quote)
    result, rejected = ground_additional_queries(TurnInterpretation(
        primary_intent=primary, secondary_intents=[intent], request_quotes={intent: quote}, answer_request=answer), text)
    assert result.secondary_intents == [intent] and not rejected
    business = BusinessContext().accept(text, "input")
    queue, _ = enqueue([], result.primary_intent, result.secondary_intents, text, "input",
                       business=business, request_quotes=result.request_quotes, answer_request=answer)
    task = next(t for t in queue if t["intent"] == intent)
    assert task["request_quote"] == quote and task["quote"] == text
    assert task["created_input_id"] == "input" and task["business_reference"] == business.reference()
    assert task["answer_request"] == answer.model_dump()


@pytest.mark.parametrize("text,help_quote,expected", [
    ("Replace it or help me fix the robot that is offline.", "help me fix the robot that is offline", True),
    ("The robot that is offline needs attention. Please help me repair it, or refund me.", "Please help me repair it", True),
    ("The robot is offline. I only want a refund.", None, False),
    ("The robot is offline. Do not troubleshoot. I want a refund.", "The robot is offline", False),
])
def test_a_remedy_request_only_adds_diagnosis_with_a_current_help_request(text, help_quote, expected):
    result = constrain_requests(TurnInterpretation(
        primary_intent="refund_request", diagnostic_request_quote=help_quote,
        facts=[{"value": "robot is offline", "quote": "robot is offline" if not expected else "robot that is offline"}],
    ), text)
    assert ("report_problem" in result.secondary_intents) is expected


async def test_http_uses_the_same_query_gate_for_model_outputs(l3_runtime, conversation):
    await conversation.send("Product PN: T2351\nProblem Type: Warranty\nProblem Description: Robot is offline.", {
        "primary_intent": "warranty_query", "secondary_intents": ["report_problem", "order_query"],
        "device_relation": "current", "request_quotes": {"warranty_query": "Warranty"},
        "facts": [{"value": "Robot is offline", "quote": "Robot is offline"}],
    })
    state = await conversation.state()
    assert not [t for t in state["task_queue"] if t["intent"] in {"warranty_query", "order_query"}]
    assert state["turn_decision"]["request_rejections"] == [
        {"intent": "warranty_query", "reason": "metadata_is_not_request"},
        {"intent": "order_query", "reason": "request_quote_missing"},
    ]


@pytest.mark.parametrize("intent,quote,answer,reason", [
    ("order_query", "My package arrived.", None, "query_result_missing"),
    ("warranty_query", "I bought it last year.", None, "query_result_missing"),
    ("order_query", "Where is it?", {"fields": ["logistics_status"], "quote": "Where is it?"}, "query_result_missing"),
    ("order_query", "Purchase date?", {"fields": ["purchase_date"], "quote": "Imagined question"}, "query_result_ungrounded"),
])
def test_source_facts_without_an_independent_query_result_are_not_tasks(intent, quote, answer, reason):
    meaning = TurnInterpretation(primary_intent="report_problem", secondary_intents=[intent],
                                 request_quotes={intent: quote}, answer_request=answer)
    result, rejected = ground_additional_queries(meaning, "Robot is offline. " + quote)
    assert not result.secondary_intents and rejected == [{"intent": intent, "reason": reason}]


async def test_http_query_after_handoff_preserves_exact_fields_and_order(l3_runtime, conversation, monkeypatch):
    quote = "what was the purchase date?"
    events = await conversation.send("Please hold my order Anker008. Also, " + quote, {
        "primary_intent": "order_change", "secondary_intents": ["order_query"], "device_relation": "current",
        "request_quotes": {"order_change": "Please hold my order Anker008", "order_query": quote},
        "answer_request": {"fields": ["purchase_date"], "quote": quote},
    })
    state = await conversation.state()
    task = next(t for t in state["task_queue"] if t["intent"] == "order_query")
    assert task["status"] == "done" and task["answer_request"] == {"fields": ["purchase_date"], "quote": quote}
    assert state["turn_decision"]["answer_request"] == task["answer_request"]
    assert state["case_status"] == "awaiting_approval"
    text = "".join(e.get("delta", "") for e in events)
    assert "Purchase date:" in text and "Anker008" in text and "Product model:" not in text
    # A paused copy simulates restoring this validated task after another turn.
    queue = [{**t, "status": "pending"} if t["task_id"] == task["task_id"] else t for t in state["task_queue"]]
    async def resume(router, state, **kwargs):
        return TurnInterpretation(primary_intent="resume_task", target_task_id=task["task_id"], device_relation="current"), {}
    monkeypatch.setattr(semantic, "interpret_turn", resume)
    monkeypatch.setattr(graph, "get_stream_writer", lambda: lambda event: None)
    update = await graph.understand({**state, "entry": "message", "text": "Continue that pending query.",
                                    "input_id": "resume-input", "task_queue": queue})
    assert update["turn_decision"]["answer_request"] == task["answer_request"]
