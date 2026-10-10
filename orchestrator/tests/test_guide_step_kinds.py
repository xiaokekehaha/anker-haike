"""步骤类型的执行语义（2026-10-09 第二批 I4 / I5）：问句写事实、说明不计操作、材料暂缺记待补、交人工段耗尽、已做操作跳步。"""

import pytest

from app.guide.verify import apply_feedback
from app.knowledge.runtime import set_knowledge_adapter
from app.plans.qa import qa_plan_library
from tests.conversation_runtime import conversation as base_conversation_fixture
from tests.fake_qa import QAHitAdapter
from tests.test_conversation_l3 import l3_runtime as l3_runtime_fixture

base_conversation = base_conversation_fixture
l3_runtime = l3_runtime_fixture
LIB = qa_plan_library()


@pytest.fixture
async def conversation(l3_runtime, base_conversation):
    yield base_conversation


def _state(plan_id, step_id, **extra):
    return {"plan_cursor": {"plan_id": plan_id, "version": 1, "step_id": step_id}, "input_id": "i1",
            "active_issue_id": "i", "issues": {"i": {"facts": [], "device_ref": {"device_ref_id": "d"}}}, **extra}


def test_question_answer_branches_and_records_an_observation_without_counting_execution():
    out = apply_feedback(state=_state("qa_bp_0032", "s1"), feedback=None, note=None, card_id="c1", library=LIB,
                         answer={"option": "Bottle connection", "text": None, "unavailable": False})
    assert out.outcome == "next" and out.plan_cursor["step_id"] == "s3"
    assert out.counters["executed"] == 0 and out.counters["skipped"] == 0
    assert out.step_attempts[-1]["answer"]["option"] == "Bottle connection"
    assert out.observation is not None
    assert out.observation["kind"] == "observation" and "Bottle connection" in out.observation["value"]
    assert out.observation["source"] == "user_statement"


def test_question_free_text_answer_goes_to_next_step():
    out = apply_feedback(state=_state("qa_bp_0032", "s1"), feedback=None, note=None, card_id="c1", library=LIB,
                         answer={"option": None, "text": "somewhere near the rim", "unavailable": False})
    assert out.outcome == "next" and out.plan_cursor["step_id"] == "s2"
    assert "somewhere near the rim" in out.observation["value"]


def test_statement_is_acknowledged_without_feedback_or_counting():
    out = apply_feedback(state=_state("qa_bp_0123", "s1"), feedback=None, note=None, card_id="c1", library=LIB, answer=None)
    assert out.outcome == "next" and out.plan_cursor["step_id"] == "s2"
    assert out.counters["executed"] == 0 and out.observation is None


async def test_statement_rides_as_context_on_the_next_card(conversation):
    """rv-0244 首段「噪音可能来自风扇、滚刷…」是说明：不单独出卡，附在第一张操作卡的 context 上。"""
    set_knowledge_adapter(QAHitAdapter("rv-0244"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_rv_0244", "confidence": 0.9, "evidence_ids": ["chunk-rv-0244"],
        "applicability": "supported", "supported_symptoms": ["runs louder than before"],
    }]}]
    events = await conversation.send("X10 Pro Omni runs louder than before", {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
        "facts": [{"value": "runs louder than before", "quote": "runs louder than before"}],
    })
    card = next(e for e in events if e["type"] == "step_card")
    assert card["step"]["step_id"] == "s2" and card["step"]["kind"] == "action"
    assert "may come from the fan" in card["step"]["context"]
    state = await conversation.state()
    assert any(t.get("reason") == "statement_context" for t in state["guide_trace"])


def test_material_request_unavailable_is_recorded_as_missing():
    out = apply_feedback(state=_state("qa_bp_0123", "s5"), feedback=None, note=None, card_id="c1", library=LIB,
                         answer={"option": None, "text": None, "unavailable": True})
    assert out.outcome == "next" and out.plan_cursor["step_id"] == "s6"
    assert out.counters["executed"] == 0
    assert out.missing_material and "video" in out.missing_material.casefold()


def test_action_feedback_still_counts():
    out = apply_feedback(state=_state("qa_bp_0123", "s6"), feedback="not_solved", note=None, card_id="c1", library=LIB, answer=None)
    assert out.counters["executed"] == 1 and out.plan_cursor["step_id"] == "s7"


async def test_t46_first_card_is_a_question_with_options(conversation):
    """T46：马达异响命中 bp-0123；第一张卡是事实问句（标题不出卡），带「continuous / intermittent」选项。"""
    set_knowledge_adapter(QAHitAdapter("bp-0123"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_bp_0123", "confidence": 0.9, "evidence_ids": ["chunk-bp-0123"],
        "applicability": "supported", "supported_symptoms": ["motor making abnormal noise"],
    }]}]
    events = await conversation.send("My S1 Pro breast pump motor is making abnormal noise", {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["S1 Pro breast pump"],
        "facts": [{"value": "motor making abnormal noise", "quote": "motor is making abnormal noise", "subject": "motor"}],
    })
    card = next(e for e in events if e["type"] == "step_card")
    assert card["step"]["kind"] == "question" and card["step"]["options"] == ["continuous", "intermittent"]
    assert card["step"]["step_id"] == "s2"
    # 回答问句：不计已操作，写成事实，下一张仍是问句
    pending = (await conversation.snapshot())["pending_input"]
    resp = await conversation.client.post(f"/sessions/{conversation.sid}/actions", json={
        "action_id": "a1", "expected_version": (await conversation.snapshot())["version"],
        "target_issue_id": (await conversation.snapshot())["active_issue_id"],
        "card_id": pending["card_id"], "input_token": pending["input_token"],
        "kind": "step_feedback", "payload": {"feedback": None, "note": None, "answer": {"option": "intermittent", "text": None, "unavailable": False}},
    })
    rows = conversation.check(resp)
    state = await conversation.state()
    assert state["counters"].get("executed", 0) == 0
    facts = state["issues"][state["active_issue_id"]]["facts"]
    assert any(f["kind"] == "observation" and "intermittent" in f["value"] for f in facts)
    nxt = next(e for e in rows if e["type"] == "step_card")
    assert nxt["step"]["kind"] == "question" and nxt["step"]["step_id"] == "s3"


async def test_question_card_rejects_feedback_and_action_card_rejects_answer(conversation):
    set_knowledge_adapter(QAHitAdapter("bp-0123"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_bp_0123", "confidence": 0.9, "evidence_ids": ["chunk-bp-0123"],
        "applicability": "supported", "supported_symptoms": ["motor making abnormal noise"],
    }]}]
    await conversation.send("My S1 Pro breast pump motor is making abnormal noise", {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["S1 Pro breast pump"],
        "facts": [{"value": "motor making abnormal noise", "quote": "motor is making abnormal noise"}],
    })
    snap = await conversation.snapshot()
    pending = snap["pending_input"]
    body = {"action_id": "a2", "expected_version": snap["version"], "target_issue_id": snap["active_issue_id"],
            "card_id": pending["card_id"], "input_token": pending["input_token"], "kind": "step_feedback"}
    resp = await conversation.client.post(f"/sessions/{conversation.sid}/actions", json={**body, "payload": {"feedback": "not_solved"}})
    assert resp.status_code == 409 and resp.json()["code"] == "not_allowed_now"
    resp = await conversation.client.post(f"/sessions/{conversation.sid}/actions", json={**body, "action_id": "a3", "payload": {"answer": {"option": "sometimes"}}})
    assert resp.status_code == 409 and resp.json()["code"] == "invalid_selection"


async def test_unspecified_cleaning_does_not_skip_all_component_checks(conversation):
    """更换滤网/刷子不代表清洁全部部件；cleaned everything 没有可核对的对象范围。"""
    set_knowledge_adapter(QAHitAdapter("rv-0244"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_rv_0244", "confidence": 0.9, "evidence_ids": ["chunk-rv-0244"],
        "applicability": "supported", "supported_symptoms": ["extremely loud noise during vacuuming"],
    }]}]
    events = await conversation.send("X10 Pro Omni makes an extremely loud noise during vacuuming; I already replaced all filters and brushes and cleaned everything", {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
        "facts": [
            {"value": "extremely loud noise during vacuuming", "quote": "extremely loud noise during vacuuming"},
            {"kind": "action_taken", "value": "replaced all filters and brushes", "quote": "replaced all filters and brushes", "subject": "filters and brushes"},
            {"kind": "action_taken", "value": "cleaned everything", "quote": "cleaned everything"},
        ],
    })
    state = await conversation.state()
    dropped = [t for t in state["guide_trace"] if t.get("event") == "step_dropped" and t.get("reason") == "user_reported"]
    assert not dropped, state["guide_trace"]
    card = next(e for e in events if e["type"] == "step_card")
    assert card["step"]["step_id"] == "s2"
