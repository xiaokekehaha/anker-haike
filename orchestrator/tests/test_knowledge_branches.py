"""Knowledge sections form paths, not a flat list of every possible operation."""

import pytest

from app.diagnose.decision import decide_next
from app.guide.steps import prepare_step, step_media
from app.guide.verify import apply_feedback
from app.knowledge.runtime import set_knowledge_adapter
from app.official.models import QAEntry
from app.official.qa_index import build_guide, get_qa_index
from app.plans.models import Plan
from app.plans.qa import plan_of, qa_plan_library
from app.rules import RulesService
from app.settings import REPO_ROOT
from tests.conversation_runtime import conversation as conversation_fixture
from tests.fake_qa import QAHitAdapter

conversation = conversation_fixture


@pytest.mark.parametrize("option,expected", [("Breast pump cannot be turned on", "s2"), ("Heating Function Malfunction", "s8")])
async def test_selected_fault_is_reconstructed_from_answer_history(option, expected):
    library = qa_plan_library()
    plan = library.get("qa_bp_0114")
    state = {"category": "breast_pump", "product_confirmed": {"sku": "T8D04"},
             "plans_ranked": [{"plan_id": plan.plan_id, "confidence": 0.9}],
             "plan_cursor": {"plan_id": plan.plan_id, "step_id": "select_scope"}}
    assert plan.first_step().required_resources == []
    assert decide_next({**state, "operation_conditions": {"resources": {"device": False}}}, library=library).kind == "step"
    answered = apply_feedback(state=state, feedback=None, note=None, card_id="scope", library=library, answer={"option": option})
    state["step_attempts"] = answered.step_attempts
    decision = decide_next({**state, "plan_cursor": None}, library=library)
    state["plan_cursor"] = decision.plan_cursor
    rules = RulesService(REPO_ROOT / "config/rules/safety_terms.yaml", hot_reload=False)
    prep = await prepare_step(state=state, library=library, rules=rules, router=None, lane="domestic", session_id="branch")
    assert prep.step["step_id"] == expected
    # Restarting publication at the entry must use the recorded option as well.
    repeated = await prepare_step(state={**state, "plan_cursor": {"plan_id": plan.plan_id, "step_id": "select_scope"}},
                                  library=library, rules=rules, router=None, lane="domestic", session_id="branch")
    assert repeated.step["step_id"] == expected
    seen = []
    current = expected
    while current not in {"DONE", "EXHAUSTED"}:
        seen.append(current)
        assert len(seen) <= len(plan.steps)
        current = plan.next_step_id(current, "not_solved")
    # 第 6 段由 qa_overrides.yaml 拆成 s6 / s6c / s6d / s6e（T53），未解决沿 s6 → s6c → s6e 走
    assert seen == (["s2", "s3", "s4", "s5", "s6", "s6c", "s6e"] if expected == "s2" else [f"s{i}" for i in range(8, 13)])
    assert step_media(plan.plan_id, "select_scope") == []


def test_structural_fault_sections_are_generic_and_keep_source_positions():
    entry = QAEntry(id="example", sheet="test", directory=["QA", "Robot"], title="Two problems",
                    content="1. Camera cannot connect\n- 1. Restart the router.\n- 2. Reset the connection.\n"
                            "2. Storage failure\n- 1. Reinsert the card.\n- 2. Format the card.",
                    visible=True, pn=["T2351"], pdt="")
    guide = build_guide(entry, {})
    plan, evidence = plan_of(guide, "test")
    compiled = Plan.model_validate(plan)
    assert compiled.first_step().branches == {"Camera cannot connect": "s1", "Storage failure": "s4"}
    assert compiled.next_step_id("s3", "not_solved") == "EXHAUSTED"
    assert compiled.next_step_id("s6", "not_solved") == "EXHAUSTED"
    assert evidence["example#s5"]["snippet"] == "Reinsert the card."
    # Sequential operating stages have the same numbering shape, but are not alternative faults.
    sequential = entry.model_copy(update={"content": entry.content.replace("Camera cannot connect", "Prepare the connection")
                                           .replace("Storage failure", "Prepare the storage")})
    assert build_guide(sequential, {}).sections == ()


def test_index_fields_are_not_executable_text_and_original_data_is_preserved():
    guide = get_qa_index().guides["rv-0138"]
    plan, evidence = plan_of(guide, "test")
    assert [s["step_id"] for s in plan["steps"]] == ["s1", "s2"]
    assert evidence["rv-0138#s2"]["snippet"] == "Restart the robot and check if the robot works properly."
    assert "Applicable Models" in guide.answer


@pytest.mark.parametrize("qa_id,product,symptom,option,expected", [
    ("bp-0114", "S1 Pro breast pump", "stopped working completely", "Heating Function Malfunction", "s8"),
    ("bp-0032", "S1 Pro breast pump", "milk leaking", "Bottle connection", "s3"),
])
async def test_http_answer_reaches_selected_branch(conversation, qa_id, product, symptom, option, expected):
    set_knowledge_adapter(QAHitAdapter(qa_id))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_" + qa_id.replace("-", "_"), "confidence": 0.9, "evidence_ids": [f"chunk-{qa_id}"],
        "applicability": "supported", "supported_symptoms": [symptom],
    }]}]
    await conversation.send(f"My {product}: {symptom}", {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": [product],
        "facts": [{"value": symptom, "quote": symptom}],
    })
    snapshot = await conversation.snapshot()
    pending = snapshot["pending_input"]
    response = await conversation.client.post(f"/sessions/{conversation.sid}/actions", json={
        "action_id": "selected-branch", "expected_version": snapshot["version"],
        "target_issue_id": snapshot["active_issue_id"], "card_id": pending["card_id"],
        "input_token": pending["input_token"], "kind": "step_feedback", "payload": {"answer": {"option": option}},
    })
    card = next(e["step"] for e in conversation.check(response) if e["type"] == "step_card")
    assert card["step_id"] == expected
    state = await conversation.state()
    assert state["counters"]["executed"] == 0
