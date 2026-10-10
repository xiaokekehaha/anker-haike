"""A missed extraction is different from an uncertain customer claim."""

import pytest

from app.conversation.history import ConversationEntry
from app.conversation.interpret import TurnInterpretation, complete_problem_facts
from app.diagnose.query import build_query
from app.knowledge.runtime import set_knowledge_adapter
from app.models.runtime import get_model_router
from app.sessions.graph import _diagnose_outcome
from tests.conversation_runtime import conversation as conversation_fixture
from tests.fake_qa import QAHitAdapter

conversation = conversation_fixture


def source_state(text):
    at = "2026-10-09T12:00:00Z"
    entry = ConversationEntry(entry_id="input", session_id="session", run_id="run", kind="message", role="user",
                              first_seq=1, last_seq=1, recorded_at=at, text=text)
    return {"session_id": "session", "input_id": "input", "text": text, "at": at, "history": [entry.as_dict()],
            "evidence": {"forbidden": {"snippet": "CANDIDATE_KNOWLEDGE_MUST_NOT_ENTER_EXTRACTION"}}}


@pytest.mark.parametrize("label", ["Problem Description", "Probleembeschrijving", "Problembeschreibung"])
async def test_missing_symptom_is_recovered_from_its_own_source(conversation, label):
    state = source_state(f"Product PN: T2351\n{label}: Water tray will not empty. I cleaned the hose.")
    meaning = TurnInterpretation(primary_intent="report_problem", facts=[
        {"kind": "action_taken", "value": "cleaned the hose", "quote": "cleaned the hose"},
    ])
    model = conversation.models["intake"]
    model.script = [{"facts": [{"value": "Water tray will not empty", "quote": "Water tray will not empty", "subject": "Water tray"}]}]
    result, trace = await complete_problem_facts(get_model_router(), meaning, state, lane="domestic")
    assert trace["outcome"] == "extracted" and len(model.calls) == 1
    assert result.facts[0].kind == "action_taken" and result.facts[1].polarity == "affirmed"
    assert result.primary_intent == meaning.primary_intent and not result.secondary_intents
    assert "CANDIDATE_KNOWLEDGE_MUST_NOT_ENTER_EXTRACTION" not in str(model.calls[0]["messages"])


@pytest.mark.parametrize("facts", [[], [{"kind": "action_taken", "value": "cleaned hose", "quote": "cleaned the hose"}],
                                    [{"value": "battery failed", "quote": "battery failed"}],
                                    [{"value": "never cleaned hose", "quote": "Never cleaned the hose"}]])
async def test_empty_action_only_or_ungrounded_recovery_does_not_create_a_symptom(conversation, facts):
    model = conversation.models["intake"]
    model.script = [{"facts": facts}]
    meaning = TurnInterpretation(primary_intent="report_problem")
    result, trace = await complete_problem_facts(get_model_router(), meaning,
        source_state("Product PN: T2351\nProblem Description: I cleaned the hose."), lane="domestic")
    assert not result.facts and trace["outcome"] == "empty" and len(model.calls) == 1


@pytest.mark.parametrize("polarity", ["affirmed", "negated", "uncertain"])
async def test_existing_grounded_polarity_does_not_trigger_recovery(conversation, polarity):
    meaning = TurnInterpretation(primary_intent="report_problem", facts=[
        {"value": "left one does work", "quote": "left one does work", "polarity": polarity},
    ])
    result, trace = await complete_problem_facts(get_model_router(), meaning,
        source_state("Product PN: T8D04\nProblem Description: The left one does work."), lane="domestic")
    assert result == meaning and trace["outcome"] == "not_needed" and not conversation.models["intake"].calls


@pytest.mark.parametrize("text,meaning", [
    ("Product PN: T2351\nProblem Description: Water tray will not empty.\nProblem Code: 1092", {"primary_intent": "report_problem"}),
    ("The tray will not empty", {"primary_intent": "report_problem"}),
    ("Product PN: T2351\nProblem Description: Water tray will not empty.", {"primary_intent": "warranty_query"}),
    ("Product PN: T2351\nProblem Description: Water tray will not empty.", {"primary_intent": "report_problem",
        "corrections": [{"fact_id": "f1", "value": None, "quote": "Water tray will not empty"}]}),
])
async def test_exact_codes_emails_other_intents_and_corrections_do_not_trigger_recovery(conversation, text, meaning):
    result, trace = await complete_problem_facts(get_model_router(), TurnInterpretation(**meaning), source_state(text), lane="domestic")
    assert result == TurnInterpretation(**meaning)
    assert trace["outcome"] == "not_needed" and not conversation.models["intake"].calls


async def test_failed_recovery_is_bounded_and_does_not_change_the_interpretation(conversation):
    model = conversation.models["intake"]
    model.script = [RuntimeError("offline")]
    meaning = TurnInterpretation(primary_intent="report_problem")
    result, trace = await complete_problem_facts(get_model_router(), meaning,
        source_state("Product PN: T2351\nProblem Description: Water tray will not empty."), lane="domestic")
    assert result == meaning and trace["outcome"] == "unavailable" and len(model.calls) == 1


def test_unparsed_description_survives_product_selection_but_does_not_authorize_operations():
    state = {"product_state": "confirmed_sku", "text": "X10 Pro Omni", "symptoms": [],
             "unparsed_problem": {"status": "unparsed", "text": "Water tray will not empty.", "source_entry_ids": ["i"]}}
    assert build_query(state) == "Water tray will not empty"
    decision = _diagnose_outcome([], knowledge_status="ok", exact_hits=[], state=state)
    assert decision["diagnose_outcome"]["reason"] == "unparsed_problem"
    assert decision["plan_cursor"] is None
    assert "I've kept your description" in decision["_decision"]["question"]


async def test_http_recovery_is_recorded_before_retrieval(conversation):
    set_knowledge_adapter(QAHitAdapter("rv-0254"))
    conversation.models["intake"].script = [
        {"primary_intent": "report_problem", "device_relation": "current", "facts": [
            {"kind": "action_taken", "value": "cleaned the hose", "quote": "cleaned the hose"},
        ]},
        {"facts": [{"value": "Water tray will not empty", "quote": "Water tray will not empty", "subject": "Water tray"}]},
    ]
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_rv_0254", "confidence": 0.9, "evidence_ids": ["chunk-rv-0254"],
        "applicability": "supported", "supported_symptoms": ["Water tray will not empty"],
    }]}]
    snapshot = await conversation.snapshot()
    response = await conversation.client.post(f"/sessions/{conversation.sid}/messages", data={
        "input_id": "recovery-input", "expected_version": snapshot["version"],
        "text": "Product PN: T2351\nProblem Description: Water tray will not empty. I cleaned the hose.",
    })
    events = conversation.check(response)
    state = await conversation.state()
    assert len(conversation.models["intake"].calls) == 2
    trace = [t for t in state["model_trace"] if t.get("purpose") == "problem_description"]
    assert len(trace) == 1 and trace[0]["outcome"] == "extracted" and trace[0]["accepted"] == 1
    assert state["symptoms"] == ["Water tray will not empty"] and state["unparsed_problem"] is None
    assert any(e["type"] == "step_card" for e in events)
    facts = state["issues"][state["active_issue_id"]]["facts"]
    assert all(f["source_entry_ids"] == ["recovery-input"] for f in facts)
