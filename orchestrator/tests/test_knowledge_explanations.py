"""Knowledge speech acts have the same semantics at every parsing entry point."""

import pytest

from app.analytics.derive import classify
from app.diagnose.decision import explanation
from app.guide.steps import prepare_step
from app.knowledge.runtime import set_knowledge_adapter
from app.official.models import QAEntry
from app.official.qa_index import build_guide, classify_step, get_qa_index
from app.plans.qa import plan_of, qa_plan_library
from app.rules import RulesService
from app.settings import REPO_ROOT
from tests.conversation_runtime import conversation as conversation_fixture
from tests.fake_qa import QAHitAdapter

conversation = conversation_fixture


@pytest.mark.parametrize(("text", "kind"), [
    ("When the battery is low, the robot will return to charge and then resume cleaning.", "statement"),
    ("The map data will be removed when the button is pressed for five seconds.", "statement"),
    ("Power issue: Even if the indicator is green, the actual level may be low.", "statement"),
    ("Connection fault: Loose internal contacts can cause intermittent operation.", "statement"),
    ("The device may stop unexpectedly. Please restart it.", "action"),
    ("If the device is offline, please restart it.", "action"),
    ("After disconnecting the cable, press the button.", "action"),
    ("Please upload a video of the display.", "material_request"),
    ("Is the indicator blinking?", "question"),
    ("If it is installed correctly, further check whether the sensor is present.", "action"),
    ("If the camera detects passers-by, it is recommended to set a privacy zone.", "action"),
    ("The sensor may be displaced. You can apply tape to hold it in position.", "action"),
    ("*The sensor may be displaced.*\n*You can apply tape to hold it in position.*", "action"),
    ("The device can apply updates automatically when it returns to the charger.", "statement"),
    ("The battery may charge slowly in cold weather. You can expect it to resume later.", "statement"),
])
def test_single_paragraph_uses_same_type_and_source(text, kind):
    entry = QAEntry(id="test-1", sheet="test", directory=["QA", "Robot"], title="Example",
                    content=text, visible=True, pn=["T2351"], pdt="")
    guide = build_guide(entry, {})
    plan, evidence = plan_of(guide, "v1")
    assert classify_step(text) == kind
    assert plan["steps"][0]["kind"] == kind
    assert evidence["test-1#s1"]["snippet"] == text


def test_restart_warranty_tail_is_not_an_operation():
    guide = get_qa_index().guides["rv-0256"]
    assert [s.kind for s in guide.steps] == ["action", "handoff"]
    plan, _ = plan_of(guide, "test")
    assert plan["steps"][0]["next_on"]["not_solved"] == "s2"


def test_possible_causes_are_not_executable():
    plan, _ = plan_of(get_qa_index().guides["bp-0111"], "test")
    assert all(s["kind"] == "statement" for s in plan["steps"][:4])
    assert any(s["kind"] == "action" for s in plan["steps"][4:])


@pytest.mark.parametrize(("qa_id", "position"), [("rv-0056", 1), ("rv-0106", 0), ("rv-0061", 0)])
def test_official_indirect_instructions_remain_actions(qa_id, position):
    assert get_qa_index().guides[qa_id].steps[position].kind == "action"


@pytest.mark.parametrize("qa_id", ["rv-0076"])
async def test_statement_only_plan_preserves_explanation_and_evidence(qa_id):
    guide = get_qa_index().guides[qa_id]
    state = {"plan_cursor": {"plan_id": guide.plan_id, "step_id": "s1"},
             "category": guide.category, "product_confirmed": {"sku": guide.pns[0]}}
    result = await prepare_step(state=state, library=qa_plan_library(),
                                rules=RulesService(REPO_ROOT / "config/rules/safety_terms.yaml", hot_reload=False),
                                router=None, lane="domestic", session_id="explanation")
    assert result.outcome == "explained"
    assert result.explanation and result.evidence
    assert result.step is None and result.card_id is None


async def test_trailing_statement_is_visible_without_faking_resolution():
    result = await prepare_step(
        state={"plan_cursor": {"plan_id": "qa_rv_0312", "step_id": "s3"},
               "category": "robot_vacuum", "product_confirmed": {"sku": "T2080"}},
        library=qa_plan_library(), rules=RulesService(REPO_ROOT / "config/rules/safety_terms.yaml", hot_reload=False),
        router=None, lane="domestic", session_id="tail",
    )
    assert result.outcome == "exhausted"
    assert "map data" in result.explanation
    assert result.step is None


async def test_explanation_context_is_not_repeated_on_subsequent_actions():
    library = qa_plan_library()
    rules = RulesService(REPO_ROOT / "config/rules/safety_terms.yaml", hot_reload=False)
    state = {"plan_cursor": {"plan_id": "qa_bp_0111", "step_id": "s1"},
             "category": "breast_pump", "product_confirmed": {"sku": "T8D04"}}
    first = await prepare_step(state=state, library=library, rules=rules, router=None, lane="domestic", session_id="one")
    assert first.step["context"] and first.displayed_nodes
    second = await prepare_step(
        state={**state, "displayed_knowledge_nodes": first.displayed_nodes,
               "steps_executed": [{"instruction_src": "evidence:bp-0111#s5", "feedback": "not_solved"}]},
        library=library, rules=rules, router=None, lane="domestic", session_id="one",
    )
    assert second.step["step_id"] == "s6" and not second.step.get("context")
    # A new issue has no presentation history and receives its own explanation.
    fresh = await prepare_step(state=state, library=library, rules=rules, router=None, lane="domestic", session_id="two")
    assert fresh.step["context"] == first.step["context"]


async def test_explanation_http_endpoint_does_not_claim_repair_or_request_warranty(conversation):
    set_knowledge_adapter(QAHitAdapter("rv-0076"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_rv_0076", "confidence": 0.9, "evidence_ids": ["chunk-rv-0076"],
        "applicability": "supported", "supported_symptoms": ["returns to recharge during cleaning"],
    }]}]
    events = await conversation.send("Omni E25 returns to recharge during cleaning", {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["Omni E25"],
        "facts": [{"value": "returns to recharge during cleaning", "quote": "returns to recharge during cleaning"}],
    })
    state = await conversation.state()
    assert state["stage"] == "done" and state["pending_card"] is None
    assert state["diagnose_outcome"]["mode"] == "explained"
    assert not any(e["type"] == "step_card" for e in events)
    assert "return to the base station to charge" in "".join(e.get("delta", "") for e in events)
    assert not state.get("steps_executed") and not state.get("case_id") and not state.get("escalate_reason")
    assert not any(m["kind"] == "closing" for m in state.get("visible_messages", []))
    assert classify(state, done_reason="completed")[0] == "consult_answered"
    assert "does not mark the device as repaired" in explanation(state)


async def test_displayed_context_survives_http_feedback_without_counting_as_operations(conversation):
    set_knowledge_adapter(QAHitAdapter("bp-0111"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_bp_0111", "confidence": 0.9, "evidence_ids": ["chunk-bp-0111"],
        "applicability": "supported", "supported_symptoms": ["motor shuts off during use"],
    }]}]
    events = await conversation.send("S1 Pro breast pump motor shuts off during use", {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["S1 Pro breast pump"],
        "facts": [{"value": "motor shuts off during use", "quote": "motor shuts off during use"}],
    })
    first = next(e["step"] for e in events if e["type"] == "step_card")
    assert first["step_id"] == "s5" and first["context"]
    snapshot = await conversation.snapshot()
    pending = snapshot["pending_input"]
    response = await conversation.client.post(f"/sessions/{conversation.sid}/actions", json={
        "action_id": "context-next", "expected_version": snapshot["version"],
        "target_issue_id": snapshot["active_issue_id"], "card_id": pending["card_id"],
        "input_token": pending["input_token"], "kind": "step_feedback", "payload": {"feedback": "not_solved"},
    })
    second = next(e["step"] for e in conversation.check(response) if e["type"] == "step_card")
    assert second["step_id"] == "s6" and not second.get("context")
    state = await conversation.state()
    assert state["counters"]["executed"] == 1
    assert state["issues"][state["active_issue_id"]]["displayed_knowledge_nodes"]
