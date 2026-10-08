"""Regression for session 7a0077: unavailable operations remain reversible, never executed."""

from dataclasses import asdict

import pytest
from httpx import ASGITransport, AsyncClient

from app.conversation.interpret import TurnInterpretation
from app.conversation.operation_conditions import (
    OperationUpdate,
    conditions_for,
    execution_history,
    explicit_operation_reply,
    step_unavailable,
    update_conditions,
)
from app.conversation.reduce import persist_issue, reduce_turn
from app.conversation.reply import fallback_reply
from app.diagnose.decision import decide_next
from app.diagnose.observations import record_observations
from app.emotion.policy import evaluate_emotion
from app.escalation.summary import build_summary
from app.guide.steps import prepare_step
from app.guide.verify import apply_feedback
from app.main import app
from app.models.runtime import get_model_router, set_model_router
from app.plans.library import PlanLibrary
from app.rules import RulesService
from app.settings import REPO_ROOT
from tests import conversation_runtime, test_conversation_l3
from tests.test_conversation_l3 import act, events, send
from tests.test_diagnostic_loop import base_state, graph_state, messages_of

LIB = PlanLibrary.from_yaml(REPO_ROOT / "config/plans.yaml")
l3_runtime = test_conversation_l3.l3_runtime
conversation = conversation_runtime.conversation


def blocked_state(note=None):
    state = base_state(plan_cursor={"plan_id": "rv_power_supply", "step_id": "s1"})
    out = apply_feedback(state=state, feedback="cannot_do", note=note, card_id="c1", library=LIB)
    state.update({key: value for key, value in asdict(out).items() if key in {
        "steps_executed", "step_attempts", "operation_conditions", "exhausted_plans", "counters",
    }})
    return state, out


def test_cannot_do_records_constraint_without_execution_or_plan_consumption():
    state, out = blocked_state()
    assert out.outcome == "reassess" and out.escalate_reason is None
    assert state["steps_executed"] == [] and state["exhausted_plans"] == []
    assert state["step_attempts"][0]["feedback"] == "cannot_do"
    assert state["counters"]["executed"] == 0 and state["counters"]["skipped"] == 1
    action = decide_next(state, library=LIB)
    assert action.kind == "ask" and action.question["kind"] == "operation_blocker"
    conditions = conditions_for(state)
    conditions.blockers[0].asked = True
    state["operation_conditions"] = conditions.model_dump()
    assert decide_next(state, library=LIB).kind == "pause"
    summary = build_summary(state, reason="R3", lane="domestic")
    assert summary.steps[0].feedback == "cannot_do"
    assert any("操作限制" in item for item in summary.observations)


def test_damage_report_in_unexecuted_step_is_not_recorded_as_executed():
    state, _ = blocked_state("设备摔坏了，无法操作")
    assert not execution_history(state)
    assert any("摔坏" in (b.quote or "") for b in conditions_for(state).blockers)


def test_device_unavailable_blocks_observation_and_operations_until_it_returns():
    state, _ = blocked_state("设备不在身边")
    assert decide_next(state, library=LIB).kind == "pause"
    conditions, changed = update_conditions(state, explicit_operation_reply("设备现在在身边"), text="设备现在在身边", input_id="back")
    assert changed
    state.update(operation_conditions=conditions, input_id="back")
    action = decide_next(state, library=LIB)
    assert action.kind == "step" and action.plan_cursor["step_id"] == "s1"
    assert not execution_history(state)


def test_constraint_scope_and_quotes_are_not_device_observations():
    state, _ = blocked_state()
    state["category"] = "power_bank"
    state["product_confirmed"] = {"sku": "ANKER-A1647"}
    conditions, changed = update_conditions(state, explicit_operation_reply("没有刷子"), text="没有刷子", input_id="brush")
    assert changed and conditions["resources"] == {"cleaning_tool": False}
    state["operation_conditions"] = conditions
    plan = LIB.get("pb_port_debris")
    assert step_unavailable(state, plan.plan_id, plan.steps[0]) == "resource_unavailable"
    assert step_unavailable(state, plan.plan_id, plan.steps[1]) is None
    wrong = OperationUpdate(signal="device_ready", quote="设备已拿到")
    assert update_conditions(state, wrong, text="产品太烂了", input_id="wrong") == (conditions, False)


def test_historical_three_skips_are_not_permanent_execution_or_exhaustion():
    plan = LIB.get("pb_port_debris")
    state = base_state(category="power_bank", product_confirmed={"sku": "ANKER-A1647"},
                       plans_ranked=[{"plan_id": plan.plan_id, "confidence": .62}],
                       exhausted_plans=[plan.plan_id], counters={"skipped": 3})
    state["steps_executed"] = [
        {"plan_id": plan.plan_id, "step_id": s.step_id, "instruction_src": s.instruction_src,
         "card_id": s.step_id, "feedback": "cannot_do"} for s in plan.steps
    ]
    assert execution_history(state) == []
    action = decide_next(state, library=LIB)
    assert action.kind == "ask"
    conditions = conditions_for(state)
    for blocker in conditions.blockers:
        blocker.asked = True
    state["operation_conditions"] = conditions.model_dump()
    assert decide_next(state, library=LIB).kind == "pause"
    updated, _ = update_conditions(state, explicit_operation_reply("现在可以做了"), text="现在可以做了", input_id="ready")
    state.update(operation_conditions=updated, input_id="ready")
    # The latest blocker is explicitly cleared; other steps are not silently retried.
    assert conditions_for(state).blockers[-1].cleared
    assert not conditions_for(state).blockers[0].cleared
    action = decide_next(state, library=LIB)
    assert action.kind == "step" and action.plan_cursor["step_id"] == "s3"


def test_emotion_without_new_evidence_does_not_recover_and_real_evidence_does():
    prior = [{"input_id": "angry", "level": "angry"}]
    for level in (None, "calm"):
        out = evaluate_emotion(level, "没有", prior, "answer", cues=[])
        assert out["emotion"]["level"] == "angry" and out["emotion_trend"] == "stable"
        assert out["emotion_track"] == prior
    out = evaluate_emotion("calm", "现在不生气了", prior, "calm", cues=["现在不生气了"])
    assert out["emotion_trend"] == "falling"
    assert evaluate_emotion(None, "A1289", [], "sku", cues=[])["emotion"]["level"] is None


def test_conditions_and_emotion_are_issue_local_and_survive_reduction():
    state, _ = blocked_state("设备不在身边")
    state.update(emotion={"level": "angry", "strategy": "direct_resolution"}, input_id="other", text="另一个问题")
    state.update(persist_issue(state))
    old = state["active_issue_id"]
    state.update(reduce_turn(state, TurnInterpretation(primary_intent="new_issue")))
    assert not state["operation_conditions"].get("resources") and state["emotion"]["level"] is None
    state.update(input_id="resume", text="回到刚才的问题")
    state.update(reduce_turn(state, TurnInterpretation(primary_intent="resume_issue", target_issue_id=old)))
    assert state["operation_conditions"]["resources"]["device"] is False
    assert state["emotion"]["level"] == "angry"


def power_bank_state():
    state = base_state(category="power_bank", product_confirmed={"sku": "ANKER-A1289"},
                       plans_ranked=[{"plan_id": "pb_737_output_check", "confidence": .62}], symptom_codes=["pb_no_output"])
    state["issues"]["issue"]["facts"][0]["symptom_codes"] = ["pb_no_output"]
    return state


@pytest.mark.parametrize("answer,plan", [("normal", "pb_737_output_check"), ("abnormal", "pb_737_display_reset"), ("laptop_uvp", "pb_737_laptop_uvp")])
def test_single_ranked_plan_still_asks_and_answers_choose_distinct_paths(answer, plan):
    state = power_bank_state()
    action = decide_next(state, library=LIB)
    assert action.kind == "ask" and action.question["observation_id"] == "pb_737_display"
    issue, _ = record_observations(state["issues"]["issue"], [{"observation_id": "pb_737_display", "option_id": answer}],
                                   definitions=LIB.observation_definitions(), input_id="display", at=state["at"], source_kind="user_report", binding={})
    state["issues"]["issue"] = issue
    action = decide_next(state, library=LIB)
    assert action.kind == "step" and action.plan_cursor["plan_id"] == plan
    state["operation_conditions"] = {"resources": {"device": False}}
    assert decide_next(state, library=LIB).kind == "pause"


async def test_publisher_rechecks_model_and_blockers():
    state, _ = blocked_state()
    state["plan_cursor"] = {"plan_id": "rv_power_supply", "step_id": "s1"}
    args = {"library": LIB, "rules": RulesService(REPO_ROOT / "config/rules/safety_terms.yaml", hot_reload=False), "router": None, "lane": "domestic", "session_id": "test"}
    assert (await prepare_step(state=state, **args)).outcome == "blocked"
    state = power_bank_state()
    state["plan_cursor"] = {"plan_id": "pb_port_debris", "step_id": "s3"}
    assert (await prepare_step(state=state, **args)).dropped[0]["reason"] == "plan_model_mismatch"


@pytest.mark.usefixtures("l3_runtime")
async def test_http_no_device_pause_resume_and_new_card_token():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        first = events(await send(client, sid, "eufy X10 Pro Omni 启动不了"))
        old = next(e for e in first if e["type"] == "step_card")
        rows = events(await act(client, sid, "step_feedback", {"feedback": "cannot_do"}))
        assert "设备不在身边" in messages_of(rows)
        assert not any(e["type"] in {"step_card", "escalation_summary", "error"} for e in rows)
        rows = events(await send(client, sid, "设备不在身边"))
        assert "先不安排读屏" in messages_of(rows), rows
        rows = events(await send(client, sid, "设备现在在身边"))
        card = next(e for e in rows if e["type"] == "step_card")
        assert card["step"]["step_id"] == old["step"]["step_id"]
        assert card["card_id"] != old["card_id"]
        state = await graph_state(sid)
        assert state["steps_executed"] == [] and len(state["step_attempts"]) == 1
        assert state["counters"]["skipped"] == 1 and not state["exhausted_plans"]


async def test_http_737_screen_answer_changes_action_without_generic_reset(conversation):
    rows = await conversation.send("Anker 737 A1289 难用", {
        "primary_intent": "report_problem", "device_relation": "other", "device_category": "power_bank",
        "product_hints": ["Anker 737", "A1289"], "facts": [{"value": "难用", "quote": "难用"}],
        "emotion_level": "dissatisfied", "emotion_cues": ["难用"],
    })
    set_model_router(None)
    client, sid = conversation.client, conversation.sid
    # 词表加入「自身回充慢」后，先问充电方向（给充电宝本身充电吗）再问有没有输出反应
    assert "给充电宝本身充电的时候吗" in messages_of(rows)
    assert "抱歉" in messages_of(rows) and len([e for e in rows if e["type"] == "message_start"]) == 1
    rows = events(await send(client, sid, "没有"))
    assert "有输出反应吗" in messages_of(rows)
    rows = events(await send(client, sid, "没有"))
    state = await graph_state(sid)
    assert "屏幕" in messages_of(rows), {key: state.get(key) for key in ("symptom_interview", "diagnostic_decision", "turn_decision", "category", "product_confirmed")}
    assert not any(e["type"] == "step_card" for e in rows)
    rows = events(await send(client, sid, "屏幕异常"))
    card = next(e for e in rows if e["type"] == "step_card")
    assert card["step"]["plan_id"] == "pb_737_display_reset"
    assert "长按电源键" not in card["step"]["instruction"]
    rows = events(await act(client, sid, "step_feedback", {"feedback": "cannot_do", "note": "设备不在身边"}))
    assert not any(e["type"] in {"step_card", "escalation_summary", "error"} for e in rows)
    assert "先不安排读屏" in messages_of(rows)
    rows = events(await send(client, sid, "我很不开心，产品太烂了"))
    assert len([e for e in rows if e["type"] == "message_start"]) == 1
    assert "当前尚未" not in messages_of(rows) and "补偿" not in messages_of(rows)
    assert (await graph_state(sid))["emotion"]["level"] == "angry"


def test_explicit_continue_overrides_emotional_burden_but_not_missing_resources():
    state = power_bank_state()
    state.update(emotion_actions=["prefer_proposal_over_more_steps"], turn_decision={"primary_intent": "complaint"})
    assert decide_next(state, library=LIB).kind == "pause"
    state["turn_decision"]["diagnostic_request"] = True
    assert decide_next(state, library=LIB).kind == "ask"
    state["operation_conditions"] = {"resources": {"device": False}}
    assert decide_next(state, library=LIB).kind == "pause"


def test_explanation_is_grounded_and_does_not_execute_or_clear_the_blocker():
    state, _ = blocked_state("不会操作")
    state.update(input_id="explain", turn_decision={"primary_intent": "supplement", "allowed_operations": True})
    action = decide_next(state, library=LIB)
    state["next_action"] = {**asdict(action), "input_id": "explain"}
    text = fallback_reply(state)
    assert "尚未执行" in text and "预期结果" in text
    assert not execution_history(state) and not conditions_for(state).blockers[0].cleared


@pytest.mark.usefixtures("l3_runtime")
async def test_complaint_preserves_pending_pause_invalidates_token_and_continue_issues_new_card():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await send(client, sid, "eufy X10 Pro Omni 启动不了")
        before = (await client.get(f"/sessions/{sid}")).json()
        pending = before["pending_input"]
        rows = events(await send(client, sid, "我要投诉，太烂了"))
        assert len([e for e in rows if e["type"] == "message_start"]) == 1
        assert not any(e["type"] in {"case_changed", "escalation_summary"} for e in rows)
        assert (await client.get(f"/sessions/{sid}")).json()["pending_input"]["card_id"] == pending["card_id"]
        rows = events(await send(client, sid, "暂停排查"))
        assert "暂停" in messages_of(rows) and not any(e["type"] == "step_card" for e in rows)
        assert (await client.get(f"/sessions/{sid}")).json()["pending_input"] is None
        rows = events(await send(client, sid, "继续排查"))
        new = next(e for e in rows if e["type"] == "step_card")
        assert new["card_id"] != pending["card_id"]
        snap = (await client.get(f"/sessions/{sid}")).json()
        rejected = await client.post(f"/sessions/{sid}/actions", json={
            "action_id": "old-token", "expected_version": snap["version"], "target_issue_id": snap["active_issue_id"],
            "card_id": pending["card_id"], "input_token": pending["input_token"], "kind": "step_feedback", "payload": {"feedback": "solved"},
        })
        assert rejected.status_code == 409, rejected.text
        assert not (await graph_state(sid))["steps_executed"]


async def test_summary_can_resume_when_new_screen_observation_arrives(conversation):
    await conversation.send("Anker 737 A1289 无法输出", {
        "primary_intent": "report_problem", "device_relation": "other", "device_category": "power_bank",
        "product_hints": ["Anker 737", "A1289"], "facts": [{"value": "无法输出", "quote": "无法输出", "symptom_code": "pb_no_output"}],
    })
    router = get_model_router()
    rows = await conversation.send("我要人工客服", {"primary_intent": "request_human", "human_request_quote": "我要人工客服"})
    assert any(e["type"] == "escalation_summary" for e in rows)
    set_model_router(None)
    rows = events(await send(conversation.client, conversation.sid, "屏幕异常"))
    assert any(e["type"] == "step_card" and e["step"]["plan_id"] == "pb_737_display_reset" for e in rows), rows
    assert len([e for e in rows if e["type"] == "message_start"]) <= 1
    assert (await conversation.state())["escalate_reason"] is None
    # A later understanding outage must not mark the earlier anger as recovered.
    set_model_router(router)
    await conversation.send("现在不想折腾了", {
        "primary_intent": "complaint", "emotion_level": "angry", "emotion_cues": ["不想折腾"],
        "operation_update": {"signal": "pause", "quote": "不想折腾"},
    })
    set_model_router(None)
    rows = events(await send(conversation.client, conversation.sid, "A1289"))
    state = await conversation.state()
    assert state["emotion"]["level"] == "angry" and state["emotion_trend"] != "falling"
    assert not any(e["type"] == "step_card" for e in rows)
