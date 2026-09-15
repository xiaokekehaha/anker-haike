"""Diagnostic decisions cross the same issue/graph seams as real conversations."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.conversation.interpret import TurnInterpretation
from app.conversation.l3_intents import symptom_question_answer
from app.conversation.reduce import reduce_turn
from app.conversation.reply import reply_to_turn
from app.diagnose.decision import decide_symptoms
from app.main import app
from app.sessions.clarify import decide
from tests.test_conversation_l3 import act, events, l3_runtime, send  # noqa: F401


def old_answer_state():
    # Captured bug shape: an old coded fact coexists with a pending discriminator.
    from app.conversation.interpret import SymptomAnswer
    from app.conversation.taxonomy import interview_answer, next_interview

    interview = next_interview(None, "issue", "first")
    interview, _ = interview_answer(
        interview,
        SymptomAnswer(question_id=interview["question"]["question_id"], answer="no", quote="不能"),
        "不能",
        "second",
    )
    interview = next_interview(interview, "issue", "second")
    fact = {
        "fact_id": "power",
        "revision": 1,
        "kind": "symptom",
        "value": "启动不了",
        "quote": "启动不了",
        "status": "active",
        "symptom_codes": ["power_failure"],
        "source_entry_ids": ["first"],
    }
    return {
        "session_id": "test",
        "input_id": "third",
        "at": "2026-09-15T02:57:34+00:00",
        "text": "不能",
        "active_issue_id": "issue",
        "issues": {
            "issue": {
                "issue_id": "issue",
                "facts": [fact],
                "device_ref": {"device_ref_id": "device"},
                "issue_revision": 1,
            }
        },
        "category": "robot_vacuum",
        "product_state": "confirmed_sku",
        "product_confirmed": {
            "sku": "EUFY-X10-PRO-OMNI",
            "name": "eufy X10 Pro Omni",
            "category": "robot_vacuum",
            "in_scope": True,
        },
        "symptoms": ["启动不了"],
        "symptom_codes": ["power_failure"],
        "symptom_interview": interview,
        "clarification": {"reason": "symptom", "attempts": 2},
    }


def test_recorded_r7_answer_preserves_report_and_narrowing():
    state = old_answer_state()
    update = reduce_turn(state, symptom_question_answer(state))
    assert update["symptom_interview"]["candidates"] == ["不充电"]
    assert update["symptom_interview"]["status"] == "narrowed"
    assert set(update["symptom_codes"]) == {"power_failure", "charging_failure"}
    assert update["issues"]["issue"]["facts"][0]["value"] == "启动不了"
    assert decide({**state, **update}, abandoned_card=None).outcome == "continue"


def test_known_fact_is_not_vetoed_by_wording():
    state = old_answer_state()
    state.update(text="eufy X10 Pro Omni 启动不了", symptom_interview=None, clarification=None)
    result = decide(state, abandoned_card=None)
    assert result.outcome == "continue"
    assert result.update["symptom_codes"] == ["power_failure"]


async def test_explanation_cannot_stream_unapproved_steps(monkeypatch):
    class ForbiddenRouter:
        def __getattr__(self, name):
            raise AssertionError("A diagnostic explanation cannot invent operations")

    monkeypatch.setattr("app.conversation.reply.get_model_router", lambda: ForbiddenRouter())
    state = old_answer_state()
    state["turn_decision"] = {"primary_intent": "explain", "allowed_operations": True}
    state["pending_card"] = {
        "kind": "step_feedback",
        "payload": {
            "step": {
                "instruction": "核对充电指示",
                "expected_result": "恢复充电",
                "caution": "如有焦味请停止使用",
            }
        },
    }
    rows = []
    await reply_to_turn(state, rows.append)
    text = "".join(e.get("delta", "") for e in rows)
    assert "核对充电指示" in text and "如有焦味请停止使用" in text
    state["turn_decision"]["allowed_operations"] = False
    rows = []
    await reply_to_turn(state, rows.append)
    assert "核对充电指示" not in "".join(e.get("delta", "") for e in rows)


@pytest.mark.usefixtures("l3_runtime")
async def test_power_failure_gets_supported_step_without_reasking(monkeypatch):
    import app.conversation.interpret as semantic

    original = semantic.interpret_turn

    async def interpretation(router, state, **kwargs):
        if "启动不了" in state.get("text", ""):
            return TurnInterpretation(
                primary_intent="report_problem",
                device_relation="current",
                device_category="robot_vacuum",
                product_hints=["eufy X10 Pro Omni"],
                facts=[{"value": "启动不了", "quote": "启动不了", "symptom_code": "power_failure"}],
            ), {"source": "recorded"}
        return await original(router, state, **kwargs)

    monkeypatch.setattr(semantic, "interpret_turn", interpretation)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, "eufy X10 Pro Omni 启动不了"))
        assert not any("能正常启动吗" in e.get("delta", "") for e in rows)
        cards = [e for e in rows if e["type"] == "step_card"]
        assert cards and cards[0]["step"]["plan_id"] == "rv_power_supply"
        assert not any(e["type"] == "escalation_summary" for e in rows)
        rows = events(await send(client, sid, "还有其他的方案吗"))
        assert all(e["step"]["step_id"] == "s1" for e in rows if e["type"] == "step_card")
        state = (
            await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})
        ).values
        assert not state.get("steps_executed")
        assert "当前已确认的排查步骤" in "".join(e.get("delta", "") for e in rows)


def test_legacy_r7_checkpoint_recovers_from_answers_without_stale_status():
    state = old_answer_state()
    update = reduce_turn(state, symptom_question_answer(state))
    state.update(update)
    state["symptom_interview"]["status"] = "superseded"
    state.update(text="继续排查", symptom_codes=[], escalation_reason="R7")
    result = decide_symptoms(state)
    assert result.outcome == "continue"
    assert set(result.codes) == {"power_failure", "charging_failure"}
    assert {"first", "second", "third"} <= set(result.source_refs)


def test_exhausted_discriminators_have_explicit_reason():
    from app.conversation.interpret import SymptomAnswer
    from app.conversation.taxonomy import interview_answer, next_interview

    interview = next_interview(None, "issue", "a")
    for iid in ["a", "b"]:
        interview, _ = interview_answer(
            interview,
            SymptomAnswer(
                question_id=interview["question"]["question_id"],
                answer="no" if iid == "b" else "yes",
                quote="答",
            ),
            "答",
            iid,
        )
        if iid == "a":
            interview = next_interview(interview, "issue", "b")
    # Missing hand-written discriminators lead to a direct symptom selection.
    result = decide_symptoms({"category": "robot_vacuum", "symptom_interview": interview})
    assert result.outcome == "clarify"
    assert result.interview["question"]["kind"] == "symptom_selection"


@pytest.mark.usefixtures("l3_runtime")
@pytest.mark.parametrize("feedback", ["solved", "not_solved", "cannot_do"])
async def test_power_flow_finishes_without_inventing_risk(feedback):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        first = events(await send(client, sid, "eufy X10 Pro Omni 启动不了"))
        card = next(e for e in first if e["type"] == "step_card")
        assert card["step"]["plan_id"] == "rv_power_supply"
        assert "焦味" in card["step"]["caution"]
        rows = events(await act(client, sid, "step_feedback", {"feedback": feedback}))
        if feedback == "not_solved":
            assert any(e["type"] == "step_card" and e["step"]["step_id"] == "s2" for e in rows)
            rows = events(await act(client, sid, "step_feedback", {"feedback": "not_solved"}))
        state = (
            await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})
        ).values
        assert not state.get("safety_flags")
        if feedback == "solved":
            assert state["stage"] == "done"
            rows = events(await send(client, sid, "还有其他的方案吗"))
            assert not any(e["type"] == "step_card" for e in rows)
            assert "此前已记录问题解决" in "".join(e.get("delta", "") for e in rows)
        else:
            assert any(
                e["type"] == "escalation_summary" and e["summary"]["reason"]["rule_id"] == "R2"
                for e in rows
            )
            rows = events(await send(client, sid, "还有其他的方案吗"))
            assert not any(e["type"] == "step_card" for e in rows)
            assert not any("主板" in e.get("delta", "") for e in rows)


@pytest.mark.usefixtures("l3_runtime")
async def test_user_reported_risk_stops_power_flow():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await send(client, sid, "eufy X10 Pro Omni 启动不了")
        rows = events(
            await act(
                client, sid, "step_feedback", {"feedback": "not_solved", "note": "闻到焦味了"}
            )
        )
        assert any(
            e["type"] == "escalation_summary" and e["summary"]["reason"]["rule_id"] == "R4"
            for e in rows
        )
        state = (
            await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})
        ).values
        assert not state.get("pending_card")
        assert state.get("safety_flags")


def test_correction_retracts_codes_and_answer_inferences():
    state = old_answer_state()
    state.update(reduce_turn(state, symptom_question_answer(state)))
    correction = "刚才说错了，不是启动不了，是吸力下降"
    state.update(text=correction, input_id="correction")
    result = reduce_turn(
        state,
        TurnInterpretation(
            primary_intent="correct",
            device_relation="current",
            corrections=[{"fact_id": "power", "value": "吸力下降", "quote": correction}],
        ),
    )
    assert result["symptom_codes"] == ["suction_low"]
    assert result["symptom_interview"]["superseded_by_input_id"] == "correction"
    assert decide_symptoms({**state, **result}).codes == ["suction_low"]


def test_product_question_does_not_inherit_symptom_attempts():
    result = decide(
        {"text": "这是另一台", "clarification": {"reason": "symptom", "attempts": 2}},
        abandoned_card=None,
    )
    assert result.outcome == "clarify" and result.reason == "product"
    assert result.update["clarification"]["attempts"] == 0


@pytest.mark.usefixtures("l3_runtime")
async def test_vague_report_never_becomes_source_text_hazard():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, "eufy X10 Pro Omni 不能用了"))
        assert any(e.get("delta") for e in rows)
        assert not any(e["type"] in {"step_card", "escalation_summary"} for e in rows)
        state = (
            await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})
        ).values
        assert not state.get("safety_flags")


def test_additional_symptom_keeps_earlier_answer_evidence():
    state = old_answer_state()
    state.update(reduce_turn(state, symptom_question_answer(state)))
    state.update(text="另外也有异响", input_id="additional")
    result = reduce_turn(
        state,
        TurnInterpretation(
            primary_intent="supplement",
            device_relation="current",
            facts=[{"value": "异响", "quote": "异响", "symptom_code": "abnormal_noise"}],
        ),
    )
    assert set(result["symptom_codes"]) == {"power_failure", "charging_failure", "abnormal_noise"}
    assert len(result["symptom_interview"]["answers"]) == 2
