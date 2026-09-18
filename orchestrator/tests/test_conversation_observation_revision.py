"""会话 37cea3：旧症状分类、暂停和改选不能把已有观察路径锁死。"""

import pytest

from app.conversation.interpret import TurnInterpretation
from app.conversation.reduce import reduce_turn
from app.diagnose.decision import decide_next
from app.diagnose.observations import match_reply
from app.guide import prepare_step
from app.models.runtime import set_model_router
from app.rules import RulesService
from app.settings import REPO_ROOT
from tests import conversation_runtime
from tests.test_conversation_l3 import events, send
from tests.test_conversation_observation_deadlock import LIB, asked, power_bank_state, supplement
from tests.test_diagnostic_loop import messages_of

conversation = conversation_runtime.conversation


def input_charging_state():
    state = power_bank_state()
    state["symptom_codes"] = ["pb_no_input"]
    state["issues"]["issue"]["facts"][0].update(
        symptom_codes=["pb_no_input"], value="自身充电慢", quote="自身充电慢",
    )
    state["observation_requests"] = asked(state, decide_next(state, library=LIB))
    return state


def test_new_observation_unlocks_plan_across_the_previous_symptom_classification():
    state = supplement(input_charging_state(), "设备不在身边", "missing")
    assert state["observation_requests"][-1]["status"] == "unknown"
    assert state["operation_conditions"]["resources"]["device"] is False
    state = supplement(state, "连接笔记本时显示 UVP", "observation")
    assert decide_next(state, library=LIB).kind in {"ask", "pause"}
    state = supplement(state, "设备现在在身边", "ready")
    action = decide_next(state, library=LIB)
    assert action.kind == "step", action
    assert action.plan_cursor["plan_id"] == "pb_737_laptop_uvp"
    assert state["symptom_codes"] == ["pb_no_input"]
    assert not state["steps_executed"] and not state["exhausted_plans"]


@pytest.mark.parametrize("text", [
    "连接笔记本时显示 UVP／屏幕显示异常",
    "屏幕显示异常，还会连接笔记本时显示 UVP",
])
def test_two_separate_findings_need_clarification_instead_of_longest_match(text):
    obs = LIB.observation_definitions()["pb_737_display"]
    assert match_reply(text, obs) is None
    state = supplement(input_charging_state(), text, "ambiguous")
    assert not [f for f in state["issues"]["issue"]["facts"] if f.get("observation_id")]
    action = decide_next(state, library=LIB)
    assert action.kind == "ask"
    assert {o["option_id"] for o in action.question["options"]} == {"laptop_uvp", "abnormal"}
    assert "先" in action.question["question"]


def test_exact_reselection_supersedes_the_fact_and_invalidates_the_previous_card():
    state = supplement(input_charging_state(), "连接笔记本时显示 UVP", "uvp")
    original = next(f for f in state["issues"]["issue"]["facts"] if f.get("observation_id"))
    state.update(pending_card={"card_id": "old", "kind": "step_feedback"},
                 plan_cursor={"plan_id": "pb_737_laptop_uvp", "step_id": "s1"})
    state = supplement(state, "屏幕异常", "corrected")
    assert state["pending_card"] is None
    assert state["turn_decision"]["pending_changes"][0]["pending_id"] == "old"
    facts = state["issues"]["issue"]["facts"]
    assert next(f for f in facts if f["fact_id"] == original["fact_id"])["status"] == "superseded"
    active = next(f for f in facts if f.get("observation_id") and f["status"] == "active")
    assert active["option_id"] == "abnormal" and active["supersedes"] == original["fact_id"]
    assert decide_next(state, library=LIB).plan_cursor["plan_id"] == "pb_737_display_reset"
    assert not state["steps_executed"]


def test_reselection_preserves_history_but_unknown_cannot_reactivate_the_old_answer():
    state = supplement(input_charging_state(), "连接笔记本时显示 UVP", "uvp")
    facts = state["issues"]["issue"]["facts"]
    history = [{"plan_id": "other", "step_id": "s1", "feedback": "not_solved"}]
    state["steps_executed"] = history
    state = supplement(state, "重新选择现象", "reselect")
    assert decide_next(state, library=LIB).kind == "ask"
    assert state["issues"]["issue"]["facts"] == facts
    assert state["steps_executed"] == history
    state = supplement(state, "无法判断", "unknown")
    assert decide_next(state, library=LIB).kind != "step"
    state = supplement(state, "屏幕异常", "revised")
    assert decide_next(state, library=LIB).plan_cursor["plan_id"] == "pb_737_display_reset"
    assert state["steps_executed"] == history


def test_unrelated_resource_update_does_not_repeat_a_restored_observation_question():
    state = supplement(input_charging_state(), "设备不在身边", "missing")
    state = supplement(state, "设备现在在身边", "ready")
    assert decide_next(state, library=LIB).kind == "ask"
    state = supplement(state, "无法判断", "unknown")
    state = supplement(state, "有备用线了", "cable")
    assert state["observation_requests"][-1]["status"] == "unknown"
    assert decide_next(state, library=LIB).kind != "ask"


@pytest.mark.parametrize("ranked", [False, True])
async def test_existing_summary_can_publish_observation_plan_despite_old_interview_constraint(ranked):
    state = supplement(input_charging_state(), "连接笔记本时显示 UVP", "uvp")
    # 模拟旧会话摘要：旧问诊只允许屏幕/充电检查；无需重新回答，继续即可恢复。
    state["diagnostic_decision"] = {"constrain_plans": True, "allowed_plans": []}
    if ranked:
        state["plans_ranked"] = [{"plan_id": "pb_737_laptop_uvp", "confidence": 0.9}]
    action = decide_next(state, library=LIB)
    state["plan_cursor"] = action.plan_cursor
    prepared = await prepare_step(state=state, library=LIB, router=None, lane="domestic",
                                  session_id=state["session_id"],
                                  rules=RulesService(REPO_ROOT / "config/rules/safety_terms.yaml", hot_reload=False))
    assert prepared.outcome == "ready"
    state = supplement(state, "重新选择现象", "reselect")
    state["plan_cursor"] = action.plan_cursor  # 即使旧游标残留，也不能发布待更正观察的步骤。
    prepared = await prepare_step(state=state, library=LIB, router=None, lane="domestic",
                                  session_id=state["session_id"],
                                  rules=RulesService(REPO_ROOT / "config/rules/safety_terms.yaml", hot_reload=False))
    assert prepared.outcome == "blocked"


@pytest.mark.parametrize("intent", ["explain", "history_query", "order_query"])
def test_referencing_a_different_option_does_not_revise_an_answer(intent):
    state = supplement(input_charging_state(), "连接笔记本时显示 UVP", "uvp")
    state.update(input_id="reference", text="屏幕异常")
    update = reduce_turn(state, TurnInterpretation(primary_intent=intent))
    assert not update["turn_decision"]["observation_answered"]
    assert update["observation_requests"][0]["option_id"] == "laptop_uvp"


@pytest.mark.parametrize("boundary", ["risk", "wrong_sku", "exhausted", "executed"])
def test_new_observation_still_respects_action_boundaries(boundary):
    state = supplement(input_charging_state(), "连接笔记本时显示 UVP", "uvp")
    if boundary == "risk":
        state["turn_decision"]["allowed_operations"] = False
    elif boundary == "wrong_sku":
        state["product_confirmed"] = {"sku": "ANKER-A1647"}
    elif boundary == "exhausted":
        state["exhausted_plans"] = ["pb_737_laptop_uvp"]
    else:
        state["steps_executed"] = [{
            "plan_id": "pb_737_laptop_uvp", "step_id": "s1", "feedback": "not_solved",
            "instruction_src": LIB.get("pb_737_laptop_uvp").first_step().instruction_src,
        }]
    assert decide_next(state, library=LIB).kind != "step"


async def test_http_37cea3_can_clarify_resume_reselect_and_reject_the_stale_card(conversation):
    await conversation.send("Anker 737 A1289 给自身充电很慢", {
        "primary_intent": "report_problem", "device_relation": "other", "device_category": "power_bank",
        "product_hints": ["Anker 737", "A1289"],
        "facts": [{"value": "自身充电很慢", "quote": "自身充电很慢", "symptom_code": "pb_no_input"}],
    })
    rows = await conversation.send("设备不在身边", {
        "primary_intent": "answer_pending",
        "operation_update": {"signal": "device_missing", "quote": "设备不在身边"},
    })
    assert not any(e["type"] == "step_card" for e in rows)
    rows = await conversation.send("连接笔记本时显示 UVP／屏幕显示异常", {
        "primary_intent": "answer_pending", "device_relation": "current",
    })
    assert not any(e["type"] in {"step_card", "escalation_summary"} for e in rows)
    assert "先" in messages_of(rows) and "UVP" in messages_of(rows)
    await conversation.send("已在", {
        "primary_intent": "answer_pending",
        "operation_update": {"signal": "device_ready", "quote": "已在"},
    })
    set_model_router(None)
    client, sid = conversation.client, conversation.sid
    rows = events(await send(client, sid, "连接笔记本时显示 UVP"))
    assert any(e["type"] == "step_card" and e["step"]["plan_id"] == "pb_737_laptop_uvp" for e in rows)
    old = (await conversation.snapshot())["pending_input"]
    rows = events(await send(client, sid, "重新选择现象"))
    assert "重新选择" in messages_of(rows)
    assert (await conversation.snapshot())["pending_input"] is None
    rows = events(await send(client, sid, "屏幕异常"))
    assert any(e["type"] == "step_card" and e["step"]["plan_id"] == "pb_737_display_reset" for e in rows)
    snap = await conversation.snapshot()
    rejected = await client.post(f"/sessions/{sid}/actions", json={
        "action_id": "stale-before-reselection", "expected_version": snap["version"],
        "target_issue_id": snap["active_issue_id"], "card_id": old["card_id"],
        "input_token": old["input_token"], "kind": "step_feedback", "payload": {"feedback": "solved"},
    })
    assert rejected.status_code == 409
    assert not (await conversation.state())["steps_executed"]
