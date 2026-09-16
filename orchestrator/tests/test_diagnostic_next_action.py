"""Decision constraints survive synthesis and remain inspectable at handoff."""

import pytest

from app.conversation.interpret import SymptomAnswer, TurnInterpretation
from app.conversation.reduce import reduce_turn
from app.conversation.taxonomy import interview_answer, next_interview
from app.diagnose.decision import decide_symptoms
from app.escalation.summary import build_summary
from app.plans.library import PlanLibrary
from app.sessions.clarify import decide
from app.settings import REPO_ROOT
from tests.test_conversation_diagnostic import old_answer_state
from tests.test_conversation_l3 import l3_runtime  # noqa: F401


def plans():
    shared = PlanLibrary.from_yaml(REPO_ROOT / "config/plans.yaml").get("rv_power_supply")
    power = shared.model_copy(update={"plan_id": "power_only", "symptom_codes": ["power_failure"]})
    charging = shared.model_copy(
        update={"plan_id": "charging_only", "symptom_codes": ["charging_failure"]}
    )
    return [power, charging, shared]


def ambiguous_state():
    state = old_answer_state()
    state["issues"]["issue"]["facts"] = []
    state.update(symptoms=[], symptom_codes=[], text="不能")
    return state


def test_intersecting_plan_sets_continue_with_only_the_shared_plan():
    result = decide_symptoms(ambiguous_state(), available_plans=plans())
    assert result.outcome == "continue"
    assert result.reason == "common_applicable_plans"
    assert [p["plan_id"] for p in result.allowed_plans] == ["rv_power_supply"]
    assert result.allowed_plans[0]["version"] == 1


def test_exhausted_or_wrong_product_plan_is_not_a_common_action():
    state = ambiguous_state()
    state["exhausted_plans"] = ["rv_power_supply"]
    assert decide_symptoms(state, available_plans=plans()).outcome == "clarify"
    different = plans()[-1].model_copy(
        update={
            "applies_to": plans()[-1].applies_to.model_copy(
                update={"scope": "sku", "sku_list": ["OTHER"]}
            )
        }
    )
    assert (
        decide_symptoms(ambiguous_state(), available_plans=[*plans()[:2], different]).outcome
        == "clarify"
    )


async def test_synthesis_cannot_reintroduce_candidate_specific_plans(monkeypatch):
    from app.sessions import graph
    from app.sessions.clarify import get_plans
    from app.sessions.graph import get_retrieval_config

    state = ambiguous_state()
    configured = plans()
    monkeypatch.setattr(get_plans(), "allowed_for", lambda **kwargs: configured)
    state.update(decide(state, abandoned_card=None).update)
    monkeypatch.setattr(graph.get_plan_library(), "allowed_for", lambda **kwargs: configured)
    monkeypatch.setattr(graph, "get_model_router", lambda: None)
    result = await graph._synthesize_step(state, {}, "domestic", get_retrieval_config())
    assert [p["plan_id"] for p in result["plans_ranked"]] == ["rv_power_supply"]


def test_handoff_preserves_candidates_and_unexecuted_step():
    state = ambiguous_state()
    state.update(decide(state, abandoned_card=None).update)
    state["pending_card"] = {
        "kind": "step_feedback",
        "payload": {
            "step": {"title": "检查基站供电", "plan_id": "rv_power_supply", "step_id": "s1"}
        },
    }
    summary = build_summary(state, reason="R3", lane="domestic")
    assert "不开机" in summary.hypotheses and "不充电" in summary.hypotheses
    assert any("未反馈" in item and "检查基站供电" in item for item in summary.observations)
    assert not summary.steps


def test_unparsed_answers_use_a_bound_budget_and_replay_is_idempotent():
    state = ambiguous_state()
    state.update(input_id="unparsed1", text="说不清怎么回事")
    meaning = TurnInterpretation(primary_intent="answer_pending", device_relation="current")
    state.update(reduce_turn(state, meaning))
    first = decide_symptoms(state, available_plans=[])
    assert first.progress["consecutive_no_progress"] == 1
    state["symptom_interview"] = first.interview
    state.update(input_id="unparsed2")
    state.update(reduce_turn(state, meaning))
    result = decide_symptoms(state, available_plans=[])
    assert result.outcome == "escalate" and result.reason == "no_progress"
    # The historical accepted answer is counted once too.
    assert result.progress["attempts"] == 3
    assert reduce_turn(state, meaning) == {}


def test_answer_records_actual_candidate_progress():
    interview = next_interview(None, "issue", "ask")
    updated, accepted = interview_answer(
        interview,
        SymptomAnswer(question_id=interview["question"]["question_id"], answer="no", quote="不能"),
        "不能",
        "reply",
    )
    assert accepted
    assert (
        updated["response_attempts"][0]["candidates_before"]
        != updated["response_attempts"][0]["candidates_after"]
    )
    assert updated["response_attempts"][0]["progressed"] is True


def test_empty_candidate_set_is_an_evidence_conflict_not_missing_coverage():
    state = ambiguous_state()
    state["symptom_interview"]["candidates"] = []
    result = decide_symptoms(state)
    assert result.reason == "evidence_conflict"


def test_taxonomy_change_does_not_reuse_old_answer_codes():
    state = ambiguous_state()
    state["symptom_interview"].update(taxonomy_version="obsolete", candidates=["不充电"])
    result = decide_symptoms(state)
    assert result.outcome == "clarify" and not result.codes


def test_progress_budget_does_not_count_explanation_or_reject_useful_answers():
    state = ambiguous_state()
    state.update(text="为什么要问这个", input_id="explain")
    state.update(reduce_turn(state, TurnInterpretation(primary_intent="explain")))
    assert decide_symptoms(state).progress["consecutive_no_progress"] == 0
    state.update(text="没有充电指示", input_id="answer")
    q = state["symptom_interview"]["question"]
    state.update(
        reduce_turn(
            state,
            TurnInterpretation(
                primary_intent="answer_pending",
                symptom_answer={
                    "question_id": q["question_id"],
                    "answer": "no",
                    "quote": "没有充电指示",
                },
            ),
        )
    )
    result = decide_symptoms(state)
    assert result.outcome == "continue" and result.progress["consecutive_no_progress"] == 0


def test_hard_budget_records_its_own_reason():
    from app.diagnose.decision import MAX_INTERVIEW_RESPONSES

    state = ambiguous_state()
    # Captured prior responses with progress, but still no supported next action.
    state["symptom_interview"]["response_attempts"] = [
        {
            "input_id": "second" if i == 0 else f"answer{i}",
            "outcome": "yes",
            "progressed": True,
        }
        for i in range(MAX_INTERVIEW_RESPONSES)
    ]
    result = decide_symptoms(state)
    assert result.outcome == "escalate" and result.reason == "clarification_budget_exhausted"
    state["diagnostic_decision"] = result.snapshot(state)
    summary = build_summary(state, reason="R7", lane="domestic")
    assert "轮次上限" in summary.reason.text
    assert any(item.startswith("待确认：") for item in summary.observations)


def test_constraint_cannot_reuse_a_new_plan_version_or_other_issue():
    from app.diagnose.decision import constrain_plans

    state = ambiguous_state()
    result = decide_symptoms(state, available_plans=plans())
    state["diagnostic_decision"] = result.snapshot(state)
    changed_plan = plans()[-1].model_copy(update={"version": 2})
    assert constrain_plans(state, [changed_plan]) == []
    state["active_issue_id"] = "other"
    assert constrain_plans(state, plans()) == []


def test_safety_restriction_precedes_any_shared_action():
    state = ambiguous_state()
    state["turn_decision"] = {"allowed_operations": False}
    result = decide_symptoms(state, available_plans=plans())
    assert result.outcome == "escalate" and result.reason == "safety_restriction"
    assert not result.allowed_plans


@pytest.mark.usefixtures("l3_runtime")
async def test_shared_plan_is_the_only_card_and_handoff_preserves_pending_step(monkeypatch):
    from httpx import ASGITransport, AsyncClient

    import app.conversation.interpret as semantic
    from app.main import app
    from app.sessions import graph
    from app.sessions.clarify import get_plans
    from tests.test_conversation_l3 import events, send

    configured = plans()
    monkeypatch.setattr(get_plans(), "allowed_for", lambda **kwargs: configured)
    monkeypatch.setattr(graph.get_plan_library(), "allowed_for", lambda **kwargs: configured)
    original = semantic.interpret_turn

    async def interpretation(router, state, **kwargs):
        if state.get("text") == "eufy X10 Pro Omni 坏了":
            return TurnInterpretation(
                primary_intent="report_problem", product_hints=["eufy X10 Pro Omni"]
            ), {"source": "test"}
        from app.conversation.l3_intents import symptom_question_answer

        answer = symptom_question_answer(state)
        if answer:
            return answer, {"source": "deterministic"}
        return await original(router, state, **kwargs)

    monkeypatch.setattr(semantic, "interpret_turn", interpretation)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await send(client, sid, "eufy X10 Pro Omni 坏了")
        rows = events(await send(client, sid, "不能"))
        cards = [e for e in rows if e["type"] == "step_card"]
        assert cards and {e["step"]["plan_id"] for e in cards} == {"rv_power_supply"}, rows
        rows = events(await send(client, sid, "我要人工客服"))
        summary = next(e["summary"] for e in rows if e["type"] == "escalation_summary")
        assert not summary["steps"]
        assert any("已提供但未反馈" in item for item in summary["observations"])


@pytest.mark.usefixtures("l3_runtime")
async def test_unparsed_replies_stop_in_the_actual_graph(monkeypatch):
    from httpx import ASGITransport, AsyncClient

    import app.conversation.interpret as semantic
    from app.main import app
    from tests.test_conversation_l3 import events, send

    async def interpretation(router, state, **kwargs):
        if state.get("symptom_interview"):
            return TurnInterpretation(primary_intent="unknown"), {"source": "test"}
        return TurnInterpretation(
            primary_intent="report_problem", product_hints=["eufy X10 Pro Omni"]
        ), {"source": "test"}

    monkeypatch.setattr(semantic, "interpret_turn", interpretation)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await send(client, sid, "eufy X10 Pro Omni 设备坏了")
        await send(client, sid, "说不清怎么回事")
        rows = events(await send(client, sid, "没法描述呢"))
        summary = next(e["summary"] for e in rows if e["type"] == "escalation_summary")
        assert summary["reason"]["rule_id"] == "R7"
        assert "连续回答" in summary["reason"]["text"]


async def test_operation_publisher_rejects_a_plan_outside_the_decision(monkeypatch):
    from app.guide.steps import prepare_step

    state = ambiguous_state()
    state["diagnostic_decision"] = decide_symptoms(state, available_plans=plans()).snapshot(state)
    state["plan_cursor"] = {"plan_id": "power_only", "version": 1, "step_id": "s1"}
    library = PlanLibrary.from_yaml(REPO_ROOT / "config/plans.yaml")
    monkeypatch.setattr(library, "get", lambda plan_id: plans()[0])
    result = await prepare_step(
        state=state, library=library, rules=None, router=None, lane="domestic", session_id="test"
    )
    assert result.outcome == "exhausted"
    assert result.dropped[0]["reason"] == "diagnostic_plan_constraint"


def test_fact_correction_invalidates_the_old_decision_snapshot():
    state = old_answer_state()
    state["diagnostic_decision"] = decide_symptoms(state, available_plans=plans()).snapshot(state)
    state.update(text="更正，是吸力下降", input_id="correction")
    result = reduce_turn(
        state,
        TurnInterpretation(
            primary_intent="correct",
            corrections=[{"fact_id": "power", "value": "吸力下降", "quote": "更正，是吸力下降"}],
        ),
    )
    assert result["diagnostic_decision"] is None
    assert "charging_failure" not in decide_symptoms({**state, **result}).codes
