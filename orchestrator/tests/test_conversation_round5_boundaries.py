"""Round5 routing regressions and opposing cases; model/provider I/O is fake."""

import json

import httpx
import pytest

from app.conversation.answers import AnswerRequest, render_answer
from app.conversation.business import BusinessContext
from app.conversation.interpret import TurnInterpretation, logistics_correction
from app.diagnose.synthesize import synthesize
from app.escalation.summary import build_summary
from app.knowledge.adapter import WeKnoraKnowledgeAdapter
from app.knowledge.runtime import set_knowledge_adapter
from app.knowledge.weknora_client import WeKnoraClient
from app.models.runtime import get_model_router
from app.official.models import OfficialData
from app.plans.qa import qa_plan_library
from tests.conversation_runtime import conversation as conversation_fixture
from tests.fake_weknora import FakeWeKnora
from tests.test_conversation_l3 import l3_runtime as l3_runtime_fixture

l3_runtime = l3_runtime_fixture
base_conversation = conversation_fixture
TICKETS = {ticket.id: ticket.body for ticket in OfficialData().tickets}


@pytest.fixture
async def conversation(l3_runtime, base_conversation):
    yield base_conversation


@pytest.mark.parametrize("text", [
    TICKETS["T7"], "My tracking number is not working. Where is my package?",
    "I can't track my order. When will I receive my package?",
])
def test_tracking_only_input_does_not_create_a_device_problem(text):
    wrong = TurnInterpretation(primary_intent="report_problem", secondary_intents=["logistics_query"])
    fixed = logistics_correction(wrong, text)
    assert fixed.primary_intent == "logistics_query"
    assert not fixed.secondary_intents


def test_only_tracking_bound_symptom_is_removed():
    fixed = logistics_correction(TurnInterpretation(
        primary_intent="report_problem", facts=[{"value": "tracking lookup fails", "quote": "it is not working"}],
    ), TICKETS["T7"])
    assert fixed.primary_intent == "logistics_query" and not fixed.facts


@pytest.mark.parametrize("extra", [
    "My camera is offline.", "The robot will not turn on.", "另外我的摄像头也离线了。",
])
def test_tracking_failure_never_erases_an_independent_device_problem(extra):
    text = "My tracking number is not working. " + extra
    original = TurnInterpretation(
        primary_intent="report_problem", secondary_intents=["logistics_query"],
        facts=[{"value": extra, "quote": extra}],
    )
    assert logistics_correction(original, text) == original


@pytest.mark.parametrize("text,primary,request_quote", [
    ("My camera is offline, but don't troubleshoot; only check my warranty.", "warranty_query", "My camera is offline"),
    ("My camera is offline. I want a refund.", "refund_request", None),
    ("My camera was offline last month. When does my warranty end?", "warranty_query", None),
])
def test_background_or_declined_diagnosis_does_not_add_a_task(text, primary, request_quote):
    meaning = TurnInterpretation(
        primary_intent=primary, diagnostic_request_quote=request_quote,
        facts=[{"value": "offline", "quote": "offline"}],
    )
    assert "report_problem" not in logistics_correction(meaning, text).secondary_intents


def test_current_fault_request_is_preserved_alongside_warranty():
    text = TICKETS["T56"]
    request = text.split(".", 1)[0]
    meaning = TurnInterpretation(
        primary_intent="warranty_query", secondary_intents=["complaint"],
        diagnostic_request_quote=request, facts=[{"value": "offline", "quote": "offline"}],
    )
    assert "report_problem" in logistics_correction(meaning, text).secondary_intents


def test_unquoted_request_cannot_create_a_diagnostic_task():
    text = "My camera is offline. What is the warranty period?"
    meaning = TurnInterpretation(
        primary_intent="warranty_query", diagnostic_request_quote="please troubleshoot offline",
        facts=[{"value": "offline", "quote": "offline"}],
    )
    assert "report_problem" not in logistics_correction(meaning, text).secondary_intents


def test_explicit_warranty_only_overrides_wrong_model_priority_but_keeps_facts():
    text = "My SoloCam S340 is offline, but don't troubleshoot; only check my warranty."
    wrong = TurnInterpretation(
        primary_intent="report_problem", secondary_intents=["warranty_query"],
        diagnostic_request_quote="My SoloCam S340 is offline",
        facts=[{"value": "offline", "quote": "offline"}],
    )
    fixed = logistics_correction(wrong, text)
    assert fixed.primary_intent == "warranty_query" and not fixed.secondary_intents
    assert fixed.facts == wrong.facts and fixed.diagnostic_request_quote is None


def test_deferring_one_device_does_not_erase_another_devices_explicit_request():
    text = "Don't troubleshoot my camera; check its warranty. Help me troubleshoot my robot's stuck brush."
    original = TurnInterpretation(
        primary_intent="report_problem", secondary_intents=["warranty_query"],
        diagnostic_request_quote="Help me troubleshoot my robot's stuck brush",
        facts=[{"value": "stuck brush", "quote": "stuck brush"}],
    )
    assert logistics_correction(original, text) == original


@pytest.mark.parametrize("prior", ["", "Anker001"])
def test_ambiguous_without_multiple_orders_requests_identification(prior):
    context = BusinessContext().accept(prior, "before").accept(
        "my camera", "now", {"relation": "ambiguous", "quote": "my camera"},
    )
    assert context.active_subject_id is None
    assert context.bind("warranty.check").status == "missing"
    assert context.bind("warranty.check").params == {}


def test_two_known_orders_remain_ambiguous():
    context = BusinessContext().accept("Anker001 Anker002", "now")
    assert context.bind("warranty.check").status == "ambiguous"


def test_restored_empty_ambiguity_does_not_invent_multiple_orders():
    context = BusinessContext(status="ambiguous")
    assert context.bind("warranty.check").status == "missing"
    text = render_answer(AnswerRequest(fields=["warranty_end"], quote="warranty"), {"status": "ambiguous"})
    assert "more than one" not in text


async def test_t7_fake_misclassification_is_corrected_through_http(conversation):
    rows = await conversation.send(TICKETS["T7"], {
        "primary_intent": "report_problem", "secondary_intents": ["logistics_query"],
        "facts": [{"value": "tracking fails", "quote": "it is not working"}],
    })
    snapshot = await conversation.snapshot()
    messages = " ".join(e.get("delta", "") for e in rows if e["type"] == "message")
    assert "order number or tracking number" in messages
    assert not any(e["type"] in {"step_card", "product_card"} for e in rows)
    assert snapshot["stage"] == "consult"


async def test_zero_order_warranty_query_does_not_claim_multiple_orders(conversation):
    rows = await conversation.send("Check the warranty on my camera.", {
        "primary_intent": "warranty_query",
        "business_reference": {"relation": "ambiguous", "quote": "my camera"},
    })
    messages = " ".join(e.get("delta", "") for e in rows if e["type"] == "message")
    assert "more than one order" not in messages and "order number" in messages


async def test_warranty_only_with_a_fault_never_starts_diagnosis(conversation):
    text = "My SoloCam S340 is offline, but don't troubleshoot; only check my warranty."
    rows = await conversation.send(text, {
        "primary_intent": "report_problem", "secondary_intents": ["warranty_query"],
        "product_hints": ["SoloCam S340"], "facts": [{"value": "offline", "quote": "offline"}],
    })
    state = await conversation.state()
    assert not conversation.models["diagnose.synthesize"].calls
    assert not any(e["type"] in {"product_card", "step_card"} for e in rows)
    assert state["turn_decision"]["primary_intent"] == "warranty_query"
    assert state["symptoms"] == ["offline"]


@pytest.fixture
async def scheduled_knowledge(conversation):
    entry = next(entry for entry in OfficialData().qa if entry.id == "rv-0522")
    server = FakeWeKnora()
    server.kbs["qa"] = {"id": "qa"}
    server.knowledge["schedule"] = {
        "id": "schedule", "knowledge_base_id": "qa", "title": entry.title,
        "content": entry.content, "parse_status": "completed",
        "custom_metadata": {"scope": "sku", "sku_list": "T2280", "category": "robot_vacuum",
                            "doc_id": entry.id, "doc_version": "test"},
    }
    def handle(request):
        if request.url.path.endswith("/hybrid-search"):
            # Simulate retrieval returning a neighboring topic, while retaining
            # the official evidence unchanged (FakeWeKnora otherwise requires an exact substring).
            body = {**json.loads(request.content), "query_text": ""}
            request = httpx.Request(request.method, request.url, headers=request.headers, json=body)
        return server.handle(request)

    async with WeKnoraClient("http://fake", server.api_key, transport=httpx.MockTransport(handle)) as client:
        set_knowledge_adapter(WeKnoraKnowledgeAdapter(client, {"kb_qa": "qa"}))
        yield


@pytest.mark.parametrize("hypotheses", [[], [{
    "plan_id": "qa_rv_0522", "confidence": 0.95, "evidence_ids": ["irrelevant-id"],
    "applicability": "not_applicable", "supported_symptoms": [],
    "rationale": "early start is not failure to start",
}]])
async def test_t61_rejected_candidates_do_not_reappear_as_steps(conversation, scheduled_knowledge, hypotheses):
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": hypotheses}]
    text = TICKETS["T61"]
    rows = await conversation.send(text, {
        "primary_intent": "report_problem", "product_hints": ["Omni C20"], "device_relation": "current",
        "facts": [
            {"value": "starts two hours early", "quote": "going off 2 hours before"},
            {"value": "cleaning history missing", "quote": "cleans are not being recorded"},
        ],
    })
    state = await conversation.state()
    assert conversation.models["diagnose.synthesize"].calls
    assert not any(e["type"] == "step_card" for e in rows)
    assert state["plans_ranked"] == [] and state["escalate_reason"] == "R5"
    reply = "".join(e.get("delta", "") for e in rows if e["type"] == "message")
    assert "couldn't confirm official troubleshooting guidance" in reply
    summary = next(e["summary"] for e in rows if e["type"] == "escalation_summary")
    assert "starts two hours early" in summary["problem"] and "cleaning history missing" in summary["problem"]
    assert all(any(symptom in item for item in summary["observations"]) for symptom in (
        "starts two hours early", "cleaning history missing",
    ))


async def test_t56_fault_request_does_not_get_stuck_in_warranty_consult(conversation):
    text = TICKETS["T56"]
    rows = await conversation.send(text, {
        "primary_intent": "warranty_query", "secondary_intents": ["complaint"],
        "product_hints": ["SoloCam S340"], "device_relation": "current",
        "diagnostic_request_quote": text.split(".", 1)[0],
        "facts": [{"value": "offline", "quote": "offline"}],
        "business_reference": {"relation": "ambiguous", "quote": "my SoloCam S340"},
    })
    state = await conversation.state()
    assert state["product_confirmed"]["sku"] == "T8170"
    assert state["query"] == "offline"
    assert "more than one order" not in " ".join(e.get("delta", "") for e in rows)
    assert "report_problem" in [task["intent"] for task in state["issues"][state["active_issue_id"]]["task_queue"]]


@pytest.mark.parametrize("applicability,covered,expected", [
    ("supported", ["scheduled cleaning cannot start while another task is running"], True),
    ("not_applicable", [], False),
    ("needs_confirmation", [], False),
    ("supported", ["invented symptom"], False),
])
async def test_applicability_not_missing_error_code_controls_selection(conversation, applicability, covered, expected):
    symptom = "scheduled cleaning cannot start while another task is running"
    library = qa_plan_library()
    plan = library.get("qa_rv_0522")
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": plan.plan_id, "confidence": 0.9, "evidence_ids": ["schedule"],
        "applicability": applicability, "supported_symptoms": covered,
    }]}]
    result = await synthesize(
        get_model_router(), state={"symptoms": [symptom]}, allowed=[plan],
        evidence=[{"evidence_id": "schedule", "source": "kb_qa", "doc_id": "rv-0522", "snippet": plan.fault}],
        observations=[], budget_ms=3000, max_hypotheses=3, session_id=None, lane="domestic",
    )
    assert bool(result["plans_ranked"]) is expected
    assert len(conversation.models["diagnose.synthesize"].calls) == 1


def test_handoff_marks_uncovered_symptom_without_erasing_either_problem():
    state = {
        "active_issue_id": "i", "issues": {"i": {"facts": [
            {"kind": "symptom", "status": "active", "value": "brush tangled"},
            {"kind": "symptom", "status": "active", "value": "history missing"},
        ]}},
        "plans_ranked": [{"plan_id": "qa_rv_0272", "supported_symptoms": ["brush tangled"]}],
    }
    summary = build_summary(state, reason="R2", lane="domestic")
    assert "brush tangled" in summary.problem and "history missing" in summary.problem
    assert "尚无适用步骤，待人工核实：history missing" in summary.observations
    assert "尚无适用步骤，待人工核实：brush tangled" not in summary.observations
