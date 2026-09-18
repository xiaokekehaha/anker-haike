"""排障闭环第一阶段（docs/planning/2026-09-16_diagnostic-loop-design）：

步骤观察进入事实 → 计划耗尽后 decide_next 依据事实决定下一动作 → 真实结束原因；f30 两步未解决路径可解释。
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.diagnose.decision import decide_next
from app.diagnose.observations import known_observations, match_reply, record_observations
from app.escalation.summary import build_summary, reassurance_text
from app.main import app
from app.plans.library import PlanLibrary, PlansError
from app.plans.runtime import set_plan_library
from app.sessions import cards
from app.settings import REPO_ROOT
from tests.test_conversation_l3 import act, events, l3_runtime, send  # noqa: F401

LIB = PlanLibrary.from_yaml(REPO_ROOT / "config" / "plans.yaml")
POWER = LIB.get("rv_power_supply")
ISSUE = "issue"

# 观察解锁的第三条路径（测试专用；真实配置里没有这条，缺乏来源的分支保持人工出口）
THIRD_PLAN = """
  - plan_id: rv_power_no_indication
    symptom_codes: [power_failure, charging_failure]
    version: 1
    fault: 无充电提示时的适配器与插座检查（测试）
    applies_to: {scope: category_generic, category: robot_vacuum}
    requires_observations:
      - {observation_id: charging_indication, option_ids: [none]}
    excluded_by_observations:
      - {observation_id: dock_power_light, option_ids: [light_off]}
    steps:
      - {step_id: s1, title: 更换插座后重试, instruction_src: evidence:test_power#p1, expected_result: 记录是否出现充电提示,
         next_on: {solved: DONE, not_solved: EXHAUSTED, cannot_do: EXHAUSTED}}
"""
THIRD_EVIDENCE = "  test_power#p1: {source: kb_manual, doc_version: test, snippet: 把基站电源换到另一个确认可用的插座后重试。}\n"


def library_with_third_plan(tmp_path) -> PlanLibrary:
    base = (REPO_ROOT / "config" / "plans.yaml").read_text(encoding="utf-8")
    text = base.replace("evidence:\n", f"evidence:\n{THIRD_EVIDENCE}", 1) + THIRD_PLAN
    path = tmp_path / "plans.yaml"
    path.write_text(text, encoding="utf-8")
    return PlanLibrary.from_yaml(path)


def base_state(**over):
    issue = {
        "issue_id": ISSUE,
        "facts": [
            {"fact_id": "f-power", "kind": "symptom", "value": "启动不了", "quote": "启动不了",
             "status": "active", "symptom_codes": ["power_failure"], "source_entry_ids": ["i1"], "revision": 1},
        ],
        "device_ref": {"device_ref_id": "dev"},
        "issue_revision": 1,
    }
    state = {
        "session_id": "s", "input_id": "i9", "at": "2026-09-16T08:00:00+00:00",
        "active_issue_id": ISSUE, "issues": {ISSUE: issue},
        "category": "robot_vacuum", "product_state": "confirmed_sku",
        "product_confirmed": {"sku": "EUFY-X10-PRO-OMNI", "name": "eufy X10 Pro Omni", "category": "robot_vacuum", "in_scope": True},
        "turn_decision": {"allowed_operations": True},
        "plans_ranked": [{"plan_id": "rv_power_supply", "version": 2, "confidence": 0.6, "source": "standard_flow"}],
        "steps_executed": [], "exhausted_plans": [], "observation_requests": [],
    }
    state.update(over)
    return state


def executed_both(observations_s1=(), observations_s2=()):
    return [
        {"plan_id": "rv_power_supply", "step_id": "s1", "card_id": "c1", "title": "检查基站供电与触点",
         "instruction_src": "evidence:troubleshooting_rv#e1", "feedback": "not_solved", "observations": list(observations_s1)},
        {"plan_id": "rv_power_supply", "step_id": "s2", "card_id": "c2", "title": "放回基站观察充电",
         "instruction_src": "evidence:troubleshooting_rv#e2", "feedback": "not_solved", "observations": list(observations_s2)},
    ]


def with_observation(state, observation_id, option_id, input_id="i5"):
    issue, patches = record_observations(
        state["issues"][ISSUE], [{"observation_id": observation_id, "option_id": option_id}],
        definitions=LIB.observation_definitions(), input_id=input_id, at=state["at"],
        source_kind="step_feedback", binding={"card_id": "c2", "plan_id": "rv_power_supply", "step_id": "s2"},
    )
    assert patches
    state["issues"][ISSUE] = issue
    return state


# ---------------- 计划模型：观察定义与条件 ----------------


def test_plan_config_declares_power_observations_with_unknown_option():
    ids = {o.observation_id: o for o in POWER.observations()}
    assert set(ids) == {"dock_power_light", "dock_contacts", "charging_indication"}
    charging = ids["charging_indication"]
    assert [o.kind for o in charging.options] == ["finding", "finding", "unknown"]
    assert charging.interview_links[0].answers == {"yes": "indicated", "no": "none"}
    assert POWER.version == 2


def test_observation_conditions_must_reference_declared_observations(tmp_path):
    base = (REPO_ROOT / "config" / "plans.yaml").read_text(encoding="utf-8")
    bad = base.replace("evidence:\n", f"evidence:\n{THIRD_EVIDENCE}", 1) + THIRD_PLAN.replace(
        "observation_id: charging_indication, option_ids: [none]",
        "observation_id: charging_indication, option_ids: [maybe]",
    )
    path = tmp_path / "bad.yaml"
    path.write_text(bad, encoding="utf-8")
    with pytest.raises(PlansError) as exc:
        PlanLibrary.from_yaml(path)
    assert "has no option ['maybe']" in str(exc.value)


def test_observation_gate_treats_unknown_as_missing_not_negative(tmp_path):
    third = library_with_third_plan(tmp_path).get("rv_power_no_indication")
    assert third.observation_gate({}) == ("missing", ["charging_indication"])
    assert third.observation_gate({"charging_indication": "none"}) == ("ok", [])
    assert third.observation_gate({"charging_indication": "indicated"}) == ("excluded", [])
    assert third.observation_gate({"charging_indication": "none", "dock_power_light": "light_off"}) == ("excluded", [])


# ---------------- 事实写入：绑定、去重、unknown、更正 ----------------


def test_record_observations_dedupes_supersedes_and_ignores_unknown():
    state = base_state()
    definitions = LIB.observation_definitions()
    issue, patches = record_observations(
        state["issues"][ISSUE],
        [
            {"observation_id": "charging_indication", "option_id": "unknown"},
            {"observation_id": "dock_power_light", "option_id": "light_on"},
            {"observation_id": "dock_power_light", "option_id": "bogus"},
            {"observation_id": "not_declared", "option_id": "x"},
        ],
        definitions=definitions, input_id="i2", at=state["at"], source_kind="step_feedback",
        binding={"card_id": "c1", "plan_id": "rv_power_supply", "plan_version": 2, "step_id": "s1"},
    )
    facts = [f for f in issue["facts"] if f["kind"] == "observation"]
    assert [p["op"] for p in patches] == ["add"] and len(facts) == 1
    assert facts[0]["option_id"] == "light_on" and facts[0]["binding"]["card_id"] == "c1"
    assert facts[0]["value"] == "基站电源灯亮吗？电源灯亮" and facts[0]["source_kind"] == "step_feedback"
    # 相同结果不重复写
    again, patches = record_observations(
        issue, [{"observation_id": "dock_power_light", "option_id": "light_on"}],
        definitions=definitions, input_id="i3", at=state["at"], source_kind="step_feedback", binding={},
    )
    assert patches == [] and again["issue_revision"] == issue["issue_revision"]
    # 不同结果：旧事实 superseded，新事实 revision+1
    corrected, patches = record_observations(
        issue, [{"observation_id": "dock_power_light", "option_id": "light_off"}],
        definitions=definitions, input_id="i4", at=state["at"], source_kind="user_report", binding={},
    )
    active = [f for f in corrected["facts"] if f["kind"] == "observation" and f["status"] == "active"]
    assert [p["op"] for p in patches] == ["replace"] and len(active) == 1
    assert active[0]["option_id"] == "light_off" and active[0]["revision"] == 2
    assert active[0]["supersedes"] == facts[0]["fact_id"]
    known = known_observations(corrected, None, LIB)
    assert known["dock_power_light"]["option_id"] == "light_off"


def test_interview_answer_is_reused_as_observation_without_new_fact():
    interview = {"answers": [{"question": "放回基站后，设备有正常的充电指示或充电语音吗？", "answer": "no", "quote": "没有", "input_id": "q1"}]}
    known = known_observations({"facts": []}, interview, LIB)
    assert known["charging_indication"] == {"option_id": "none", "source": "interview", "source_id": "q1", "quote": "没有"}
    # 事实优先于问诊折算
    state = with_observation(base_state(), "charging_indication", "indicated")
    assert known_observations(state["issues"][ISSUE], interview, LIB)["charging_indication"]["option_id"] == "indicated"


@pytest.mark.parametrize(
    ("text", "expected"),
    [("没有充电提示", "none"), ("有充电提示但还是开不了", "indicated"), ("不知道", "unknown"), ("还是不行", None), ("没有提示", "none")],
)
def test_free_text_reply_matches_a_single_option_or_stays_unknown(text, expected):
    assert match_reply(text, LIB.observation_definitions()["charging_indication"]) == expected


# ---------------- decide_next：选择顺序 ----------------


def test_ranked_switch_keeps_confidence_threshold_and_skips_executed_steps():
    state = base_state(
        plans_ranked=[
            {"plan_id": "rv_suction_hair_wrap", "confidence": 0.85, "source": "synthesize"},
            {"plan_id": "rv_suction_filter_clog", "confidence": 0.4, "source": "synthesize"},
        ],
        exhausted_plans=["rv_suction_hair_wrap"],
        steps_executed=[{"plan_id": "rv_suction_hair_wrap", "step_id": "s2", "card_id": "c", "feedback": "not_solved",
                         "instruction_src": "evidence:manual_rv_v1#c15", "title": "取出并清洁滤网"}],
    )
    action = decide_next(state, library=LIB)
    assert action.kind == "step" and action.reason == "ranked_plan"
    assert action.plan_cursor == {"plan_id": "rv_suction_filter_clog", "version": 1, "step_id": "s2", "source": "synthesize"}
    assert action.trace["confidence"] == 0.4
    assert action.trace["skipped_steps"] == [{"plan_id": "rv_suction_filter_clog", "step_id": "s1", "reason": "duplicate_instruction_src"}]
    state["plans_ranked"][1]["confidence"] = 0.2
    low = decide_next(state, library=LIB)
    assert low.kind == "handoff_offer" and low.reason == "no_supported_followup" and low.compat_rule == "R2"


def test_f30_two_unresolved_steps_end_with_explicit_coverage_boundary():
    state = base_state(exhausted_plans=["rv_power_supply"], steps_executed=executed_both())
    action = decide_next(state, library=LIB)
    assert action.kind == "handoff_offer" and action.reason == "no_supported_followup"
    state["next_action"] = action.snapshot(state)
    summary = build_summary(state, reason="R2", lane="domestic")
    assert summary.reason.rule_id == "R2" and summary.reason.cause == "no_supported_followup"
    assert "「检查基站供电与触点」、「放回基站观察充电」" in summary.reason.text
    assert "现有资料没有进一步可执行的排查操作" in summary.reason.text
    text = reassurance_text("R2", state)
    assert "尚未接入真实转接" in text and "条件变化后" in text
    # 没有配置不同处理时，不同观察不能编造出差异
    observed = with_observation(base_state(exhausted_plans=["rv_power_supply"], steps_executed=executed_both()), "charging_indication", "none")
    assert decide_next(observed, library=LIB).reason == "no_supported_followup"


def test_same_not_solved_with_different_observations_yields_different_paths(tmp_path):
    lib = library_with_third_plan(tmp_path)
    exhausted = {"exhausted_plans": ["rv_power_supply"], "steps_executed": executed_both()}
    none_seen = with_observation(base_state(**exhausted), "charging_indication", "none")
    action = decide_next(none_seen, library=lib)
    assert action.kind == "step" and action.reason == "observation_unlocked_plan"
    assert action.plan_cursor["plan_id"] == "rv_power_no_indication" and action.plan_cursor["source"] == "observation"
    indicated = with_observation(base_state(**exhausted), "charging_indication", "indicated")
    skipped = decide_next(indicated, library=lib)
    assert skipped.kind == "handoff_offer" and skipped.reason == "no_supported_followup"
    assert {"plan_id": "rv_power_no_indication", "reason": "excluded_by_observation"} in skipped.trace["skipped"]
    # 排除条件命中（电源灯不亮）时即使充电提示为 none 也不复发该计划
    dark = with_observation(with_observation(base_state(**exhausted), "charging_indication", "none"), "dock_power_light", "light_off", input_id="i6")
    assert decide_next(dark, library=lib).kind == "handoff_offer"
    # 已执行过该路径的步骤不再复发
    done = dict(none_seen)
    done["steps_executed"] = [*executed_both(), {"plan_id": "rv_power_no_indication", "step_id": "s1", "card_id": "c3",
                                                  "feedback": "not_solved", "instruction_src": "evidence:test_power#p1", "title": "更换插座后重试"}]
    done["exhausted_plans"] = ["rv_power_supply", "rv_power_no_indication"]
    assert decide_next(done, library=lib).reason == "no_supported_followup"


def test_missing_observation_is_asked_once_per_attempt_then_declared_unavailable(tmp_path):
    lib = library_with_third_plan(tmp_path)
    state = base_state(exhausted_plans=["rv_power_supply"], steps_executed=executed_both())
    first = decide_next(state, library=lib)
    assert first.kind == "ask" and first.reason == "observation_changes_next_action"
    assert first.question["observation_id"] == "charging_indication" and first.question["attempt"] == 1
    assert [o["option_id"] for o in first.question["options"]] == ["indicated", "none", "unknown"]
    state["observation_requests"] = [{"observation_id": "charging_indication", "issue_id": ISSUE, "status": "unparsed", "input_id": "a1"}]
    second = decide_next(state, library=lib)
    assert second.kind == "ask" and second.question["attempt"] == 2
    state["observation_requests"].append({"observation_id": "charging_indication", "issue_id": ISSUE, "status": "unparsed", "input_id": "a2"})
    stop = decide_next(state, library=lib)
    assert stop.kind == "handoff_offer" and stop.reason == "observation_unavailable"
    assert stop.trace["unavailable"] == ["charging_indication"]
    state["next_action"] = stop.snapshot(state)
    assert "放回基站后有充电提示" in build_summary(state, reason="R2", lane="domestic").reason.text
    # 用户明确说无法判断：不再追问
    unknown = base_state(exhausted_plans=["rv_power_supply"], steps_executed=executed_both(),
                         observation_requests=[{"observation_id": "charging_indication", "issue_id": ISSUE, "status": "unknown", "input_id": "a1"}])
    assert decide_next(unknown, library=lib).reason == "observation_unavailable"
    # 问诊阶段已回答过充电指示 → 不追问，直接进入相符路径
    answered = base_state(exhausted_plans=["rv_power_supply"], steps_executed=executed_both(),
                          symptom_interview={"taxonomy_version": None, "candidates": ["不充电"], "answers": [
                              {"question": "放回基站后，设备有正常的充电指示或充电语音吗？", "answer": "no", "quote": "没有", "input_id": "q1"}]})
    reuse = decide_next(answered, library=lib)
    assert reuse.kind == "step" and reuse.plan_cursor["plan_id"] == "rv_power_no_indication"
    assert "q1" in reuse.basis


def test_risk_human_and_resolution_take_precedence_over_steps(tmp_path):
    lib = library_with_third_plan(tmp_path)
    ready = with_observation(base_state(exhausted_plans=["rv_power_supply"], steps_executed=executed_both()), "charging_indication", "none")
    assert decide_next(ready, library=lib).kind == "step"
    risk = dict(ready, turn_decision={"allowed_operations": False})
    assert decide_next(risk, library=lib) == decide_next(dict(ready, escalate_reason="R4"), library=lib)
    assert decide_next(risk, library=lib).kind == "safety_stop" and decide_next(risk, library=lib).compat_rule == "R4"
    human = dict(ready, turn_decision={"allowed_operations": True, "escalation_trigger": "R3"})
    action = decide_next(human, library=lib)
    assert action.kind == "handoff_offer" and action.reason == "user_requested_human" and action.compat_rule == "R3"
    solved = dict(ready, steps_executed=[*executed_both()[:1], {**executed_both()[1], "feedback": "solved"}])
    assert decide_next(solved, library=lib).kind == "resolved"


# ---------------- 真实事件入口：f30 路径与观察解锁路径 ----------------


def summary_of(rows):
    return next(e for e in rows if e["type"] == "escalation_summary")


def messages_of(rows):
    return "".join(e.get("delta", "") for e in rows if e["type"] == "message")


async def graph_state(sid):
    return (await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})).values


@pytest.mark.usefixtures("l3_runtime")
async def test_f30_replay_records_observations_and_explains_the_end():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        first = events(await send(client, sid, "eufy X10 Pro Omni 启动不了"))
        card = next(e for e in first if e["type"] == "step_card")
        assert card["step"]["plan_id"] == "rv_power_supply" and card["step"]["plan_version"] == 2
        assert [o["observation_id"] for o in card["step"]["observations"]] == ["dock_power_light", "dock_contacts"]
        assert "检查正常不等于整机已恢复" in card["step"]["expected_result"]
        rows = events(await act(client, sid, "step_feedback", {
            "feedback": "not_solved",
            "observations": [{"observation_id": "dock_power_light", "option_id": "light_on"},
                             {"observation_id": "dock_contacts", "option_id": "unknown"},
                             {"observation_id": "charging_indication", "option_id": "none"}],  # 不属于本步骤 → 忽略
        }))
        second = next(e for e in rows if e["type"] == "step_card")
        assert second["step"]["step_id"] == "s2"
        assert [o["observation_id"] for o in second["step"]["observations"]] == ["charging_indication"]
        state = await graph_state(sid)
        issue = state["issues"][state["active_issue_id"]]
        observed = [f for f in issue["facts"] if f["kind"] == "observation" and f["status"] == "active"]
        assert [(f["observation_id"], f["option_id"]) for f in observed] == [("dock_power_light", "light_on")]
        assert observed[0]["binding"]["step_id"] == "s1" and observed[0]["binding"]["card_id"] == card["card_id"]
        rows = events(await act(client, sid, "step_feedback", {
            "feedback": "not_solved", "observations": [{"observation_id": "charging_indication", "option_id": "none"}],
        }))
        summary = summary_of(rows)
        assert summary["handoff_status"] == "prepared"
        reason = summary["summary"]["reason"]
        assert reason["rule_id"] == "R2" and reason["cause"] == "no_supported_followup"
        assert "「检查基站供电与触点」、「放回基站观察充电」" in reason["text"]
        assert [s["observed"] for s in summary["summary"]["steps"]] == [["电源灯亮"], ["没有充电提示"]]
        assert any("没有充电提示" in o for o in summary["summary"]["observations"])
        assert "现有资料没有进一步可执行的排查操作" in messages_of(rows) and "尚未接入真实转接" in messages_of(rows)
        state = await graph_state(sid)
        assert state["escalate_reason"] == "R2" and state["plan_cursor"] is None
        assert state["next_action"]["kind"] == "handoff_offer" and state["next_action"]["reason"] == "no_supported_followup"
        assert [t["event"] for t in state["guide_trace"] if t["event"] in {"verify", "reassess"}][-2:] == ["verify", "reassess"]
        snap = (await client.get(f"/sessions/{sid}")).json()
        answered = next(t for t in snap["timeline"] if t["kind"] == "step_card" and t["step"]["step_id"] == "s2")
        assert answered["observation_answers"] == [{"observation_id": "charging_indication", "option_id": "none"}]
        rows = events(await send(client, sid, "还有其他的方案吗"))
        assert not any(e["type"] == "step_card" for e in rows)


@pytest.fixture
def third_plan_library(tmp_path):
    lib = library_with_third_plan(tmp_path)
    set_plan_library(lib)
    cards.set_plans(lib)
    try:
        yield lib
    finally:
        set_plan_library(None)
        cards.set_plans(None)


async def run_power_steps(client, sid, charging_option):
    first = events(await send(client, sid, "eufy X10 Pro Omni 启动不了"))
    assert next(e for e in first if e["type"] == "step_card")["step"]["step_id"] == "s1"
    rows = events(await act(client, sid, "step_feedback", {
        "feedback": "not_solved", "observations": [{"observation_id": "dock_power_light", "option_id": "light_on"}],
    }))
    assert next(e for e in rows if e["type"] == "step_card")["step"]["step_id"] == "s2"
    payload = {"feedback": "not_solved"}
    if charging_option:
        payload["observations"] = [{"observation_id": "charging_indication", "option_id": charging_option}]
    return events(await act(client, sid, "step_feedback", payload))


@pytest.mark.usefixtures("l3_runtime", "third_plan_library")
async def test_observation_unlocks_a_verified_path_without_restarting_the_plan():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = await run_power_steps(client, sid, "none")
        card = next(e for e in rows if e["type"] == "step_card")
        assert (card["step"]["plan_id"], card["step"]["step_id"]) == ("rv_power_no_indication", "s1")
        assert not any(e["type"] == "escalation_summary" for e in rows)
        state = await graph_state(sid)
        assert state["exhausted_plans"] == ["rv_power_supply"]
        assert state["plan_cursor"]["plan_id"] == "rv_power_no_indication"
        # 标准流程会把符合症状码的计划都排进 plans_ranked，因此这里可能经排序候选进入；观察门槛同样生效
        assert state["next_action"]["reason"] in {"ranked_plan", "observation_unlocked_plan"}
        # 相反观察：没有可用路径，如实说明并提供人工选项
        sid2 = (await client.post("/sessions")).json()["session_id"]
        rows = await run_power_steps(client, sid2, "indicated")
        assert summary_of(rows)["summary"]["reason"]["cause"] == "no_supported_followup"
        assert not any(e["type"] == "step_card" for e in rows)


@pytest.mark.usefixtures("l3_runtime", "third_plan_library")
async def test_missing_observation_is_asked_and_free_text_answer_reenters_the_loop():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = await run_power_steps(client, sid, None)
        assert not any(e["type"] in {"step_card", "escalation_summary"} for e in rows)
        asked = messages_of(rows)
        # 正文只留问题；选项在卡片上，不再在一句话里用 ／ 罗列
        assert "放回基站后有充电提示" in asked and "没有充电提示" not in asked
        card = next(e for e in rows if e["type"] == "observation_card")
        assert card["observation"]["observation_id"] == "charging_indication"
        assert "没有充电提示" in [o["label"] for o in card["observation"]["options"]]
        state = await graph_state(sid)
        assert state["observation_requests"][-1]["status"] == "asked"
        assert state["pending_card"]["kind"] == "answer_observation"
        # 只说「不行」不会被写成阴性；系统换一种表达再问一次
        rows = events(await send(client, sid, "还是不行"))
        assert "再确认一下" in messages_of(rows) and not any(e["type"] == "step_card" for e in rows)
        state = await graph_state(sid)
        assert [r["status"] for r in state["observation_requests"]] == ["unparsed", "asked"]
        assert not [f for f in state["issues"][state["active_issue_id"]]["facts"] if f.get("observation_id") == "charging_indication"]
        rows = events(await send(client, sid, "没有充电提示"))
        card = next(e for e in rows if e["type"] == "step_card")
        assert card["step"]["plan_id"] == "rv_power_no_indication"
        # 改用文本答同一个问题：卡片收掉，不留一个已经答过的问题挂在界面上
        assert any(e["type"] == "pending_changed" and e["reason"] == "answered_in_text" for e in rows)
        state = await graph_state(sid)
        facts = [f for f in state["issues"][state["active_issue_id"]]["facts"] if f["kind"] == "observation" and f["status"] == "active"]
        assert [(f["observation_id"], f["option_id"], f["source_kind"]) for f in facts] == [
            ("dock_power_light", "light_on", "step_feedback"), ("charging_indication", "none", "user_report"),
        ]
        assert state["observation_requests"][-1]["status"] == "answered"


@pytest.mark.usefixtures("l3_runtime", "third_plan_library")
async def test_user_unable_to_observe_ends_with_observation_unavailable():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await run_power_steps(client, sid, None)
        rows = events(await send(client, sid, "不知道，没法判断"))
        summary = summary_of(rows)
        assert summary["summary"]["reason"]["cause"] == "observation_unavailable"
        assert "放回基站后有充电提示" in summary["summary"]["reason"]["text"]
        assert not any(e["type"] == "step_card" for e in rows)
        state = await graph_state(sid)
        assert state["observation_requests"][-1]["status"] == "unknown"
        assert not [f for f in state["issues"][state["active_issue_id"]]["facts"] if f.get("observation_id") == "charging_indication"]


@pytest.mark.usefixtures("l3_runtime", "third_plan_library")
async def test_observation_card_selection_records_the_fact_and_advances():
    """点选走 option_id 直达事实写入，不经过只认唯一字面命中的 match_reply。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await run_power_steps(client, sid, None)
        snap = (await client.get(f"/sessions/{sid}")).json()
        assert snap["pending_input"]["kind"] == "answer_observation"
        item = next(t for t in snap["timeline"] if t["kind"] == "observation_card")
        assert item["chosen_option_id"] is None and item["plan_id"] == "rv_power_no_indication"
        rows = events(await act(client, sid, "answer_observation", {"observation_id": "charging_indication", "option_id": "none"}))
        card = next(e for e in rows if e["type"] == "step_card")
        assert card["step"]["plan_id"] == "rv_power_no_indication"
        state = await graph_state(sid)
        facts = [f for f in state["issues"][state["active_issue_id"]]["facts"] if f["kind"] == "observation" and f["status"] == "active"]
        assert ("charging_indication", "none", "observation_card") in [(f["observation_id"], f["option_id"], f["source_kind"]) for f in facts]
        assert state["observation_requests"][-1]["status"] == "answered"
        snap = (await client.get(f"/sessions/{sid}")).json()
        item = next(t for t in snap["timeline"] if t["kind"] == "observation_card")
        assert item["chosen_option_id"] == "none"


@pytest.mark.usefixtures("l3_runtime", "third_plan_library")
async def test_observation_card_unknown_option_stops_asking_without_a_negative_fact():
    """「答不上来」是一个明确选项，不是一种现象：不写事实，也不再追问同一题。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await run_power_steps(client, sid, None)
        rows = events(await act(client, sid, "answer_observation", {"observation_id": "charging_indication", "option_id": "unknown"}))
        assert summary_of(rows)["summary"]["reason"]["cause"] == "observation_unavailable"
        assert not any(e["type"] == "step_card" for e in rows)
        state = await graph_state(sid)
        assert state["observation_requests"][-1]["status"] == "unknown"
        assert not [f for f in state["issues"][state["active_issue_id"]]["facts"] if f.get("observation_id") == "charging_indication"]


@pytest.mark.usefixtures("l3_runtime", "third_plan_library")
async def test_observation_card_rejects_an_option_it_never_offered():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await run_power_steps(client, sid, None)
        response = await act(client, sid, "answer_observation", {"observation_id": "charging_indication", "option_id": "light_off"})
        assert response.status_code == 409 and response.json()["code"] == "invalid_selection"
        response = await act(client, sid, "answer_observation", {"observation_id": "dock_power_light", "option_id": "light_on"})
        assert response.status_code == 409 and response.json()["code"] == "invalid_selection"
