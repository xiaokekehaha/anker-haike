import copy

from app.conversation.interpret import TurnInterpretation
from app.conversation.reduce import persist_issue, reduce_turn


def turn(state, iid, text, **meaning):
    state = {
        **state,
        "session_id": "s",
        "input_id": iid,
        "input_seq": int(iid[1:]) * 10,
        "at": "2026-09-13T01:00:00Z",
        "text": text,
        "entry": "message",
    }
    update = reduce_turn(state, TurnInterpretation(**meaning), precheck_risk="冒烟" in text)
    return {**state, **update}


def earbuds():
    return turn(
        {},
        "i1",
        "耳机没有声音",
        primary_intent="report_problem",
        device_relation="other",
        product_hints=["耳机"],
        device_category="earbuds",
        facts=[{"value": "没有声音", "quote": "没有声音"}],
    )


def test_control_turns_preserve_facts_and_do_not_repeat_escalation():
    state = earbuds()
    state["escalate_reason"] = "R3"
    after = turn(
        state, "i2", "我之前问了什么问题", primary_intent="history_query", device_relation="current"
    )
    assert after["symptoms"] == ["没有声音"]
    assert after["escalate_reason"] is None
    corrected = turn(after, "i3", "刚说错了", primary_intent="correct", device_relation="current")
    assert corrected["symptoms"] == ["没有声音"]
    assert corrected["turn_decision"]["clarification"]


def test_symptom_rule_code_is_persisted_and_overrides_model_disagreement():
    state = turn({}, "i1", "吸力变弱", primary_intent="report_problem", device_relation="current", facts=[{"value": "吸力变弱", "quote": "吸力变弱", "symptom_code": "power_failure"}])
    assert state["symptom_codes"] == ["suction_low"]
    issue = state["issues"][state["active_issue_id"]]
    assert issue["facts"][0]["symptom_code"] == "suction_low"
    assert state["turn_decision"]["normalization_disagreements"]


def test_human_handoff_requires_current_request_source():
    state = earbuds()
    card = {"card_id": "pending", "kind": "step_feedback", "payload": {}}
    state["pending_card"] = card
    complaint = turn(state, "i2", "再不解决我就去平台投诉", primary_intent="request_human", emotion_level="complaint_risk")
    assert complaint["turn_decision"]["primary_intent"] == "complaint"
    assert complaint["turn_decision"]["escalation_trigger"] is None
    assert complaint["pending_card"] == card
    handoff = turn(complaint, "i3", "请转人工客服", primary_intent="request_human", human_request_quote="请转人工客服")
    assert handoff["turn_decision"]["escalation_trigger"] == "R3"
    assert handoff["pending_card"] is None


def test_other_device_risk_does_not_relabel_earbud():
    state = earbuds()
    earbud_id = state["active_issue_id"]
    state = turn(
        state,
        "i2",
        "我机器人冒烟了",
        primary_intent="report_problem",
        device_relation="other",
        product_hints=["机器人"],
        device_category="robot_vacuum",
        facts=[{"value": "冒烟", "quote": "冒烟"}],
        device_safety_assertion="reported",
        device_safety_quote="冒烟",
    )
    assert state["active_issue_id"] != earbud_id
    assert state["issues"][earbud_id]["symptoms"] == ["没有声音"]
    assert state["symptoms"] == ["冒烟"]
    assert state["turn_decision"]["escalation_trigger"] == "R4"
    state = turn(state, "i3", "新问题", primary_intent="new_issue")
    assert not state["turn_decision"]["allowed_operations"]
    assert state["turn_decision"]["escalation_trigger"] is None


def test_pending_explanation_preserves_token_and_does_not_count_execution():
    state = earbuds()
    state.update(
        pending_card={
            "kind": "step_feedback",
            "card_id": "c1",
            "input_token": "token",
            "payload": {},
        },
        counters={"executed": 2},
        steps_executed=[{"step_id": "s1"}],
    )
    after = turn(state, "i2", "为什么要这样做", primary_intent="explain", device_relation="current")
    assert after["pending_card"] == state["pending_card"]
    assert after["counters"] == {"executed": 2}
    assert after["steps_executed"] == [{"step_id": "s1"}]


def test_correction_sources_and_incremental_add():
    state = earbuds()
    fid = state["issues"][state["active_issue_id"]]["facts"][0]["fact_id"]
    bad = turn(
        state,
        "i2",
        "其实是音量小",
        primary_intent="correct",
        device_relation="current",
        corrections=[{"fact_id": "invented", "value": "音量小", "quote": "音量小"}],
    )
    assert bad["symptoms"] == ["没有声音"]
    fixed = turn(
        state,
        "i3",
        "其实是音量小",
        primary_intent="correct",
        device_relation="current",
        corrections=[{"fact_id": fid, "value": "音量小", "quote": "其实是音量小"}],
    )
    assert fixed["symptoms"] == ["音量小"]
    facts = fixed["issues"][fixed["active_issue_id"]]["facts"]
    assert facts[0]["status"] == "superseded" and facts[1]["supersedes"] == fid
    assert reduce_turn(fixed, TurnInterpretation(primary_intent="correct")) == {}
    supplement = turn(
        fixed,
        "i4",
        "还有杂音",
        primary_intent="supplement",
        device_relation="current",
        facts=[{"value": "杂音", "quote": "杂音"}],
    )
    assert supplement["symptoms"] == ["音量小", "杂音"]


def test_negated_smoke_does_not_create_risk_but_retraction_does_not_clear_one():
    state = turn(
        {},
        "i1",
        "机器人没有冒烟",
        primary_intent="report_problem",
        device_relation="other",
        product_hints=["机器人"],
        device_safety_assertion="negated",
        device_safety_quote="没有冒烟",
    )
    assert state["risk_cases"] == []
    reported = turn(
        state,
        "i2",
        "确实冒烟了",
        primary_intent="supplement",
        device_relation="current",
        facts=[{"value": "冒烟", "quote": "冒烟"}],
        device_safety_assertion="reported",
        device_safety_quote="冒烟",
    )
    denied = turn(
        reported,
        "i3",
        "没有冒烟，是说错了",
        primary_intent="correct",
        device_relation="current",
        device_safety_assertion="negated",
        device_safety_quote="没有冒烟",
    )
    assert denied["risk_cases"][0]["status"] == "disputed"
    assert not denied["turn_decision"]["allowed_operations"]


def test_diagnostic_projection_does_not_overwrite_other_issue_or_memory():
    state = earbuds()
    original = copy.deepcopy(state["issues"])
    state["stage"] = "guide"
    result = persist_issue(state)
    iid = state["active_issue_id"]
    assert result["issues"][iid]["facts"] == original[iid]["facts"]
    assert result["issues"][iid]["stage"] == "guide"


def test_draft_suspends_old_card_and_resume_replaces_token_without_reset():
    state = earbuds()
    original_issue = state["active_issue_id"]
    state.update(
        pending_card={
            "kind": "step_feedback",
            "card_id": "c1",
            "input_token": "token",
            "payload": {},
        },
        counters={"executed": 2},
        steps_executed=[{"step_id": "s1"}],
    )
    draft = turn(state, "i2", "新问题", primary_intent="new_issue")
    assert draft["active_issue_id"] != original_issue
    assert draft["issues"][draft["active_issue_id"]]["status"] == "draft"
    assert draft["pending_card"] is None
    assert draft["issues"][original_issue]["pending_card"]["status"] == "suspended"
    resumed = turn(
        draft, "i3", "继续耳机的问题", primary_intent="resume_issue", target_issue_id=original_issue
    )
    assert resumed["pending_card"]["card_id"] != "c1"
    assert resumed["pending_card"]["input_token"] != "token"
    assert resumed["counters"] == {"executed": 2}
    assert resumed["steps_executed"] == [{"step_id": "s1"}]


def test_invalid_device_safety_quote_cannot_suppress_precheck():
    for assertion in ("negated", "reported"):
        state = turn(
            {},
            "i1",
            "机器人冒烟",
            primary_intent="report_problem",
            device_relation="other",
            product_hints=["机器人"],
            device_safety_assertion=assertion,
            device_safety_quote="不存在的原话",
        )
        assert state["risk_cases"]
        assert not state["turn_decision"]["allowed_operations"]
