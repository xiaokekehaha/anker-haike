"""Regression for session 0f8809b0: an observation answer must never be lost.

用户把判别题选项答成「设备不在身边」后，会话连续五轮重复同一句暂停文案：观察请求被记成
unparsed 就再也不受理回答，而资源缺失让这道题永远不会再问。
"""

import pytest

from app.conversation.interpret import TurnInterpretation, interpret_turn
from app.conversation.operation_conditions import (
    OperationConditions,
    conditions_for,
    explicit_operation_reply,
    has_operation_context,
    update_conditions,
)
from app.conversation.reduce import reduce_turn
from app.diagnose.decision import decide_next
from app.models.runtime import get_model_router, set_model_router
from app.plans.library import PlanLibrary
from app.sessions.graph import route_entry
from app.settings import REPO_ROOT
from tests import conversation_runtime
from tests.test_conversation_l3 import events, send
from tests.test_diagnostic_loop import base_state, messages_of

LIB = PlanLibrary.from_yaml(REPO_ROOT / "config/plans.yaml")
conversation = conversation_runtime.conversation


def power_bank_state():
    state = base_state(category="power_bank", product_confirmed={"sku": "ANKER-A1289"},
                       plans_ranked=[{"plan_id": "pb_737_output_check", "confidence": .62}],
                       symptom_codes=["pb_no_output"], entry="message")
    state["issues"]["issue"]["facts"][0]["symptom_codes"] = ["pb_no_output"]
    return state


def asked(state, action):
    return [{
        "observation_id": action.question["observation_id"], "plan_id": action.question["plan_id"],
        "issue_id": state["active_issue_id"], "input_id": state["input_id"],
        "asked_at": state["at"], "status": "asked", "attempt": 1,
    }]


def supplement(state, text, input_id):
    state.update(input_id=input_id, text=text)
    state.update(reduce_turn(state, TurnInterpretation(primary_intent="supplement", device_relation="current")))
    return state


def test_default_conditions_are_not_an_operation_context():
    """issue 每轮都写回完整 dump，所以字典非空不能当作「正在操作」。"""
    assert not has_operation_context({"operation_conditions": OperationConditions().model_dump()})
    assert has_operation_context({"operation_conditions": {"resources": {"device": False}}})
    assert has_operation_context({"operation_conditions": {}, "plan_cursor": {"plan_id": "p"}})
    assert has_operation_context({"steps_executed": [{"plan_id": "p", "step_id": "s1"}]})


def test_unavailable_observation_reply_is_reopened_by_a_later_option_label():
    state = power_bank_state()
    action = decide_next(state, library=LIB)
    assert action.kind == "ask" and action.question["observation_id"] == "pb_737_display"
    state["observation_requests"] = asked(state, action)

    state = supplement(state, "设备不在身边", "miss")
    assert state["observation_requests"][0]["status"] == "unknown"
    assert conditions_for(state).resources == {"device": False}

    # 隔一轮逐字给出选项标签：请求还开着，答案接得住（原会话在这里把回答整条丢掉）
    state = supplement(state, "拿到了，连接笔记本时显示 UVP", "answer")
    assert state["observation_requests"][0]["status"] == "answered"
    assert state["observation_requests"][0]["option_id"] == "laptop_uvp"
    # 所有步骤默认需要设备，所以此时只差设备回到手上，而不是重复那段暂停文案
    action = decide_next(state, library=LIB)
    assert action.kind == "ask" and action.question["resource"] == "device"

    state = supplement(state, "拿到了", "back")
    action = decide_next(state, library=LIB)
    assert action.kind == "step" and action.plan_cursor["plan_id"] == "pb_737_laptop_uvp"


def test_unrelated_turns_do_not_overwrite_the_pending_observation_record():
    state = power_bank_state()
    state["observation_requests"] = asked(state, decide_next(state, library=LIB))
    state = supplement(state, "设备不在身边", "miss")
    state = supplement(state, "这产品太差了", "rant")
    assert state["observation_requests"][0]["quote"] == "设备不在身边"
    assert state["observation_requests"][0]["status"] == "unknown"


async def test_http_answer_after_missing_device_never_repeats_the_same_pause(conversation):
    """会话 0f8809 的用户可见序列：第 4 轮之后不再逐字重复同一句暂停文案。"""
    await conversation.send("Anker 737 充电宝型号 A1289，怎么这么难用", {
        "primary_intent": "report_problem", "device_relation": "other", "device_category": "power_bank",
        "product_hints": ["Anker 737", "A1289"], "facts": [{"value": "难用", "quote": "难用"}],
    })
    set_model_router(None)
    client, sid = conversation.client, conversation.sid
    rows = events(await send(client, sid, "没有"))
    assert "屏幕" in messages_of(rows)

    pause = messages_of(events(await send(client, sid, "设备不在身边")))
    assert "先不安排读屏" in pause

    rows = events(await send(client, sid, "连接笔记本时显示 UVP"))
    assert messages_of(rows) != pause, "收到判别题答案后不能原样重复暂停文案"
    assert "设备现在在身边" in messages_of(rows)

    rows = events(await send(client, sid, "设备现在在身边"))
    card = next(e for e in rows if e["type"] == "step_card")
    assert card["step"]["plan_id"] == "pb_737_laptop_uvp"


def test_missing_device_pause_asks_again_and_a_natural_reply_releases_it():
    state = power_bank_state()
    conditions, changed = update_conditions(state, explicit_operation_reply("设备不在身边"),
                                            text="设备不在身边", input_id="miss")
    assert changed and conditions["resources"] == {"device": False}
    state.update(operation_conditions=conditions, input_id="miss")
    # 声明当轮先如实答复
    assert decide_next(state, library=LIB).kind == "pause"

    state["input_id"] = "later"
    action = decide_next(state, library=LIB)
    assert action.kind == "ask" and action.question["resource"] == "device"
    assert "设备现在在身边" in action.question["question"]

    conditions = conditions_for(state)
    conditions.resource_asks["device"] = "later"
    state["operation_conditions"] = conditions.model_dump()
    assert decide_next(state, library=LIB).kind == "pause"  # 同一次缺失只追问一次

    state = supplement(state, "拿到了", "back")
    assert state["turn_decision"]["operation_changed"]
    assert state["operation_conditions"]["resources"]["device"] is True
    assert not state["operation_conditions"]["resource_asks"]
    action = decide_next(state, library=LIB)
    assert action.kind == "ask" and action.question["observation_id"] == "pb_737_display"


@pytest.mark.parametrize("status", ["asked", "unparsed", "unknown"])
@pytest.mark.parametrize("intent,text", [
    ("explain", "之前你问的‘连接笔记本时显示 UVP’是什么意思？"),
    ("history_query", "我之前说过‘连接笔记本时显示 UVP’吗？"),
    ("order_query", "你提到‘连接笔记本时显示 UVP’，那笔订单什么时候买的？"),
    ("unknown", "之前你问的‘连接笔记本时显示 UVP’是什么意思？"),
])
def test_mentioning_an_option_does_not_answer_an_observation(status, intent, text):
    """会话 0f8809 的补答回归：保留待答问题，解释/引用不产生设备事实。"""
    state = power_bank_state()
    state["observation_requests"] = asked(state, decide_next(state, library=LIB))
    state["observation_requests"][0]["status"] = status
    state.update(input_id="mention", text=text)
    state.update(reduce_turn(state, TurnInterpretation(primary_intent=intent)))
    assert not state["turn_decision"]["observation_answered"]
    assert not state["turn_decision"]["observation_attempted"]
    assert state["observation_requests"][0]["status"] == status
    assert not [f for f in state["issues"]["issue"]["facts"] if f.get("observation_id")]
    assert route_entry(state) != "reassess"

    # 之后真正补答仍有效，不能为了避免误判关掉补答入口。
    state = supplement(state, "连接笔记本时显示 UVP", "actual-answer")
    assert state["turn_decision"]["observation_answered"]
    assert state["observation_requests"][0]["option_id"] == "laptop_uvp"


@pytest.mark.parametrize("resource", ["cleaning_tool", "spare_cable", "spare_device", "charger"])
@pytest.mark.parametrize("text", ["拿到了", "已经拿到了"])
async def test_short_ready_reply_updates_the_resource_being_asked_about(resource, text):
    state = power_bank_state()
    state.update(input_id="ready", text=text, operation_conditions={
        "resources": {"device": False, resource: False},
        "resource_sources": {"device": "missing-device", resource: "missing-resource"},
        "resource_asks": {"device": "asked-device", resource: "asked-resource"},
    }, next_action={"kind": "ask", "question": {"kind": "operation_blocker", "resource": resource}})
    meaning, _ = await interpret_turn(None, state, lane="domestic")
    state.update(reduce_turn(state, meaning))
    assert state["operation_conditions"]["resources"] == {"device": False, resource: True}
    assert state["operation_conditions"]["resource_asks"] == {"device": "asked-device"}


@pytest.mark.parametrize("resource", ["device", "cleaning_tool", "spare_cable", "spare_device", "charger"])
async def test_short_ready_reply_uses_a_single_missing_resource(resource):
    state = power_bank_state()
    state.update(input_id="ready", text="已经拿到了", operation_conditions={"resources": {resource: False}})
    meaning, _ = await interpret_turn(None, state, lane="domestic")
    state.update(reduce_turn(state, meaning))
    assert state["operation_conditions"]["resources"] == {resource: True}


async def test_short_ready_reply_clarifies_when_multiple_resources_are_missing():
    state = power_bank_state()
    state.update(input_id="ambiguous", text="拿到了", operation_conditions={
        "resources": {"device": False, "cleaning_tool": False},
    })
    meaning, _ = await interpret_turn(None, state, lane="domestic")
    state.update(reduce_turn(state, meaning))
    assert state["operation_conditions"]["resources"] == {"device": False, "cleaning_tool": False}
    assert not state["turn_decision"]["operation_changed"]
    assert state["turn_decision"]["clarification"]
    assert route_entry(state) == "dialogue"


async def test_explicit_resource_name_takes_precedence_over_the_recheck_target():
    state = power_bank_state()
    state.update(input_id="ready", text="设备拿到了", operation_conditions={
        "resources": {"device": False, "cleaning_tool": False},
    }, next_action={"kind": "ask", "question": {"kind": "operation_blocker", "resource": "cleaning_tool"}})
    meaning, _ = await interpret_turn(None, state, lane="domestic")
    state.update(reduce_turn(state, meaning))
    assert state["operation_conditions"]["resources"] == {"device": True, "cleaning_tool": False}


@pytest.mark.parametrize("model_available", [True, False])
async def test_http_explaining_a_deferred_option_preserves_the_question(conversation, model_available):
    await conversation.send("Anker 737 A1289 无法输出", {
        "primary_intent": "report_problem", "device_relation": "other", "device_category": "power_bank",
        "product_hints": ["Anker 737", "A1289"],
        "facts": [{"value": "无法输出", "quote": "无法输出", "symptom_code": "pb_no_output"}],
    })
    router = get_model_router()
    set_model_router(None)
    client, sid = conversation.client, conversation.sid
    await send(client, sid, "设备不在身边")
    before = await conversation.state()
    text = "之前你问的‘连接笔记本时显示 UVP’是什么意思？"
    if model_available:
        set_model_router(router)
        rows = await conversation.send(text, {"primary_intent": "explain", "device_relation": "current"})
    else:
        rows = events(await send(client, sid, text))
    state = await conversation.state()
    assert state["observation_requests"] == before["observation_requests"]
    assert state["turn_decision"]["reply_mode"] in {"dialogue", "clarify"}
    assert not state["turn_decision"]["observation_answered"]
    assert not any(e["type"] == "step_card" for e in rows)
    issue = state["issues"][state["active_issue_id"]]
    assert not [f for f in issue["facts"] if f.get("observation_id")]

    set_model_router(None)
    rows = events(await send(client, sid, "已经拿到了"))
    assert not any(e["type"] == "step_card" for e in rows)
    assert "屏幕" in messages_of(rows)
    rows = events(await send(client, sid, "连接笔记本时显示 UVP"))
    assert any(e["type"] == "step_card" and e["step"]["plan_id"] == "pb_737_laptop_uvp" for e in rows)


def test_resource_clarification_cannot_be_bypassed_by_a_model_proposal():
    state = power_bank_state()
    state["observation_requests"] = asked(state, decide_next(state, library=LIB))
    state.update(input_id="ambiguous", text="拿到了", operation_conditions={
        "resources": {"device": False, "cleaning_tool": False},
    })
    state.update(reduce_turn(state, TurnInterpretation.model_validate({
        "primary_intent": "supplement", "operation_update": {"signal": "device_ready", "quote": "拿到了"},
    })))
    assert state["operation_conditions"]["resources"] == {"device": False, "cleaning_tool": False}
    assert state["observation_requests"][0]["status"] == "asked"
    assert state["turn_decision"]["clarification"]
    assert route_entry(state) == "dialogue"
