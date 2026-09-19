"""会话 37cea3ff86574d05a162adf53bca34d3 的回归：范围冲突先澄清，回充慢有自己的路径。

用户主诉「给充电宝本身充电很慢」被归入 pb_no_input；判别题答「连接笔记本时显示 UVP」后码内候选全被排除、
码外计划 pb_737_laptop_uvp 被解锁，原实现报 knowledge_coverage_missing 转人工。
分析见 docs/planning/2026-09-18-20_session-reversibility-review/，实施见 docs/planning/2026-09-19-0056_scope-conflict-and-recharge-path/。
"""

import pytest

from app.conversation.taxonomy import next_interview, normalize
from app.diagnose.decision import decide_next
from app.diagnose.observations import record_observations
from app.models.runtime import set_model_router
from app.plans.library import PlanLibrary
from app.plans.runtime import set_plan_library
from app.sessions import cards
from app.sessions.graph import _after_product
from app.settings import REPO_ROOT
from tests import conversation_runtime
from tests.test_conversation_l3 import act, events, send
from tests.test_diagnostic_loop import base_state, messages_of, scope_answered

LIB = PlanLibrary.from_yaml(REPO_ROOT / "config/plans.yaml")
conversation = conversation_runtime.conversation
ISSUE = "issue"


def session_37cea3_final_state():
    """离线复原该会话最终 checkpoint 的决策相关字段：codes=[pb_no_input]、观察 laptop_uvp、设备已在身边。"""
    state = base_state(
        category="power_bank", product_confirmed={"sku": "ANKER-A1289", "category": "power_bank"},
        plans_ranked=[{"plan_id": "pb_737_output_check", "version": 1, "confidence": 0.62, "source": "synthesize"},
                      {"plan_id": "pb_737_display_reset", "version": 1, "confidence": 0.3, "source": "synthesize"}],
        symptom_codes=["pb_no_input"], operation_conditions={"resources": {"device": True}},
        observation_requests=[{"observation_id": "pb_737_display", "plan_id": "pb_737_output_check", "issue_id": ISSUE,
                               "input_id": "i3", "status": "answered", "option_id": "laptop_uvp"}],
    )
    fact = state["issues"][ISSUE]["facts"][0]
    fact.update(value="充电很慢", quote="很慢", symptom_codes=["pb_no_input"])
    issue, patches = record_observations(
        state["issues"][ISSUE], [{"observation_id": "pb_737_display", "option_id": "laptop_uvp"}],
        definitions=LIB.observation_definitions(), input_id="i5", at=state["at"],
        source_kind="user_report", binding={"plan_id": "pb_737_output_check", "asked_input_id": "i3"},
    )
    assert patches
    state["issues"][ISSUE] = issue
    return state


def test_37cea3_final_state_asks_about_scope_instead_of_handing_off():
    """原会话在这个状态报「资料没有适用路径」；UVP 计划其实存在，只是处理的是另一类现象。"""
    state = session_37cea3_final_state()
    action = decide_next(state, library=LIB)
    assert action.kind == "ask" and action.reason == "scope_conflict"
    question = action.question
    assert question["plan_id"] == "pb_737_laptop_uvp"
    assert (question["observation_id"], question["option_id"]) == ("pb_737_display", "laptop_uvp")
    assert "「给充电宝本身充电时充不进 / 充不满」" in question["question"]
    assert "「连接笔记本时显示 UVP」" in question["question"] and "都有" in question["question"]
    assert [o["value"] for o in question["interview"]["question"]["options"]] == ["充电宝自身充不进电", "无法给设备充电"]
    assert [s["reason"] for s in action.trace["skipped"]] == ["excluded_by_observation", "excluded_by_observation"]


def test_37cea3_scope_answer_decides_the_path():
    state = session_37cea3_final_state()
    question = decide_next(state, library=LIB).question
    both = decide_next(scope_answered(state, question, ["充电宝自身充不进电", "无法给设备充电"]), library=LIB)
    assert both.kind == "step" and both.reason == "observation_unlocked_plan"
    assert (both.plan_cursor["plan_id"], both.plan_cursor["step_id"]) == ("pb_737_laptop_uvp", "s1")
    # 只确认原范围：UVP 计划不再复发；这份 plans_ranked 里没有别的码内计划，如实说明没有路径
    kept = decide_next(scope_answered(state, question, ["充电宝自身充不进电"]), library=LIB)
    assert kept.kind == "handoff_offer" and kept.reason == "knowledge_coverage_missing"
    assert {"plan_id": "pb_737_laptop_uvp", "reason": "outside_confirmed_scope"} in kept.trace["skipped"]


def test_in_scope_ready_step_precedes_the_scope_question():
    """码内还有可执行步骤时先做它（回充计划就是对主诉的回答）；范围问题等码内路径走完再问。"""
    state = session_37cea3_final_state()
    state["plans_ranked"].append({"plan_id": "pb_737_recharge_slow", "version": 1, "confidence": 0.3, "source": "standard_flow"})
    action = decide_next(state, library=LIB)
    assert action.kind == "step" and action.plan_cursor["plan_id"] == "pb_737_recharge_slow"
    state["exhausted_plans"] = ["pb_737_recharge_slow"]
    assert decide_next(state, library=LIB).reason == "scope_conflict"


# ---------------- 内容：词表槽位与 A1289 回充路径 ----------------


def test_slow_recharge_has_its_own_family_and_plan():
    assert [s["symptom_code"] for s in normalize("回充很慢", "power_bank")] == ["pb_slow_input"]
    assert [s["symptom_code"] for s in normalize("给充电宝充电很慢", "power_bank")] == ["pb_slow_input"]
    # 裸「很慢」不猜方向：给手机充电慢不是回充慢，交给模型按问诊上下文判断
    assert normalize("给手机充电很慢", "power_bank") == []
    plan = LIB.get("pb_737_recharge_slow")
    assert plan.applies(category="power_bank", sku="ANKER-A1289") and not plan.applies(category="power_bank", sku="ANKER-A1647")
    assert set(plan.symptom_codes) == {"pb_slow_input", "pb_no_input"} and not plan.requires_observations
    assert [s.evidence_key for s in plan.steps] == ["official_anker737_ports#c1", "official_anker737_ports#c2"]
    assert "USB-C1" in LIB.evidence_snippet(plan.steps[0].instruction_src)
    generic = LIB.get("pb_input_check")
    assert "pb_slow_input" in generic.symptom_codes and "ANKER-A1289" in generic.applies_to.excluded_skus


def test_interview_offers_slow_recharge_after_confirming_self_charging():
    interview = next_interview(None, ISSUE, "i1", category="power_bank")
    assert interview["question"]["question"] == "问题出现在给充电宝本身充电的时候吗？"
    narrowed = {**interview, "candidates": ["充电宝自身充不进电", "自身回充慢", "指示灯异常"],
                "answers": [{"key": interview["question"]["key"], "question": interview["question"]["question"],
                             "answer": "yes", "quote": "是的", "input_id": "i2"}]}
    selection = next_interview(narrowed, ISSUE, "i2", category="power_bank")["question"]
    assert selection["kind"] == "symptom_selection"
    assert "给充电宝本身充电很慢" in [o["label"] for o in selection["options"]]


# ---------------- 事实没变不重新检索 ----------------


@pytest.fixture
def plan_library():
    set_plan_library(LIB)
    cards.set_plans(LIB)
    try:
        yield LIB
    finally:
        set_plan_library(None)
        cards.set_plans(None)


def test_unchanged_facts_reassess_instead_of_retrieving(plan_library):
    state = base_state(plans_ranked=[{"plan_id": "rv_power_supply", "confidence": 0.3}], turn_decision={})
    state["issues"][ISSUE]["issue_revision"] = 4
    state["retrieval_basis"] = {"issue_revision": 4, "plans_version": LIB.version}
    assert _after_product(state) == "reassess"
    # 事实修订号变了、计划库版本变了、还没有候选：都要重新检索
    assert _after_product({**state, "retrieval_basis": {"issue_revision": 3, "plans_version": LIB.version}}) == "retrieve"
    assert _after_product({**state, "retrieval_basis": {"issue_revision": 4, "plans_version": "older"}}) == "retrieve"
    assert _after_product({**state, "plans_ranked": []}) == "retrieve"
    assert _after_product({**state, "retrieval_basis": None}) == "retrieve"


# ---------------- 真实事件入口 ----------------


async def open_737_session(conversation):
    rows = await conversation.send("Anker 737 充电宝型号 A1289，怎么这么难用", {
        "primary_intent": "report_problem", "device_relation": "other", "device_category": "power_bank",
        "product_hints": ["Anker 737", "A1289"], "facts": [{"value": "难用", "quote": "难用"}],
    })
    set_model_router(None)
    assert "给充电宝本身充电的时候吗" in messages_of(rows)
    rows = events(await send(conversation.client, conversation.sid, "是的"))
    assert "给充电宝本身充电很慢" in messages_of(rows)
    return conversation.client, conversation.sid


async def test_http_37cea3_path_clarifies_scope_before_switching_problem(conversation):
    """37cea3 的轨迹：充不进 → 判别卡答 UVP → 先走码内的回充路径 → 走完后问范围 → 「都有」→ UVP 步骤。全程不转人工。"""
    client, sid = await open_737_session(conversation)
    rows = events(await send(client, sid, "1"))
    card = next(e for e in rows if e["type"] == "observation_card")
    assert card["observation"]["observation_id"] == "pb_737_display"
    calls_after_first_retrieval = len(conversation.knowledge.calls)

    rows = events(await act(client, sid, "answer_observation", {"observation_id": "pb_737_display", "option_id": "laptop_uvp"}))
    step = next(e for e in rows if e["type"] == "step_card")["step"]
    assert (step["plan_id"], step["step_id"]) == ("pb_737_recharge_slow", "s1") and "USB-C1" in step["instruction"]
    rows = events(await act(client, sid, "step_feedback", {"feedback": "not_solved"}))
    assert next(e for e in rows if e["type"] == "step_card")["step"]["step_id"] == "s2"

    rows = events(await act(client, sid, "step_feedback", {"feedback": "not_solved"}))
    assert not any(e["type"] in {"step_card", "escalation_summary"} for e in rows)
    asked = messages_of(rows)
    assert "「连接笔记本时显示 UVP」" in asked and "都有" in asked
    state = await conversation.state()
    assert state["next_action"]["reason"] == "scope_conflict"
    assert state["symptom_interview"]["question"]["kind"] == "symptom_selection"
    assert len(conversation.knowledge.calls) == calls_after_first_retrieval, "观察与步骤反馈不重新检索"

    rows = events(await send(client, sid, "都有"))
    step = next(e for e in rows if e["type"] == "step_card")["step"]
    assert (step["plan_id"], step["step_id"]) == ("pb_737_laptop_uvp", "s1")
    state = await conversation.state()
    assert {"pb_no_input", "pb_no_output"} <= set(state["symptom_codes"])
    assert len(conversation.knowledge.calls) > calls_after_first_retrieval, "范围扩展是事实变化，重新检索"
    assert not any(e["type"] == "escalation_summary" for out in conversation.outputs for e in out)


async def test_http_slow_recharge_gets_the_recharge_step_without_screen_question(conversation):
    """主诉按「自身回充慢」归类时直接得到回充步骤：不再借输出侧计划的判别题。"""
    client, sid = await open_737_session(conversation)
    rows = events(await send(client, sid, "2"))
    assert not any(e["type"] in {"observation_card", "escalation_summary"} for e in rows)
    step = next(e for e in rows if e["type"] == "step_card")["step"]
    assert (step["plan_id"], step["step_id"]) == ("pb_737_recharge_slow", "s1")
    assert "屏幕" not in messages_of(rows)
    state = await conversation.state()
    assert state["symptom_codes"] == ["pb_slow_input"]
    assert state["retrieval_basis"]["issue_revision"] == state["issues"][state["active_issue_id"]]["issue_revision"]
