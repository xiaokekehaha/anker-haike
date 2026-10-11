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


def test_fact_quote_matches_across_whitespace_and_apostrophe_form():
    # T61 (round6 2026-10-09): the ticket reads "omni c20  isn’t" (double space, curly
    # apostrophe); the model cited "omni c20 isn't". Exact matching dropped the symptom
    # and the handoff summary said no symptom was recorded.
    text = "omni c20  isn’t following my schedule it’s going off 2 hours before and the cleans are not being recorded by your dumb app"
    state = turn(
        {}, "i1", text, primary_intent="report_problem", device_relation="other",
        product_hints=["omni c20"], device_category="robot_vacuum",
        facts=[{"value": "going off 2 hours before schedule", "quote": "omni c20 isn't following my schedule it's going off 2 hours before"},
               {"value": "cleans not recorded by app", "quote": "the cleans are not being recorded by your dumb app"},
               {"value": "invented", "quote": "the robot caught fire"}],
    )
    assert state["symptoms"] == ["going off 2 hours before schedule", "cleans not recorded by app"]


# ---- 事实来源与极性（2026-10-09 官方 63 单 I1 / I3：T11、T50、T31）----

T11_TEXT = (
    "Product Name: S1 Pro\nProduct PN: T2080A\nProblem Type: ERROR\n"
    "Problem Push: EB1L: The robot encountered an error while adding clean water. Task ended. Click to contact customer service for assistance.\n"
    "Problem Description: EB1L: The robot encountered an error while adding clean water. Task ended. Click to contact customer service for assistance.\n"
    "Problem Upload Images: []"
)


def test_device_message_contact_phrase_is_not_a_human_request():
    """T11：App 推送里的「Click to contact customer service」是设备文案，不是用户要人工。"""
    state = turn(
        {}, "i1", T11_TEXT, primary_intent="request_human", device_relation="current",
        human_request_quote="Click to contact customer service for assistance",
        facts=[{"value": "error while adding clean water", "quote": "The robot encountered an error while adding clean water"}],
    )
    assert state["turn_decision"]["primary_intent"] == "report_problem"
    assert state["turn_decision"]["escalation_trigger"] is None
    assert state["turn_decision"]["human_request_source"] is None
    fact = state["issues"][state["active_issue_id"]]["facts"][0]
    assert fact["source"] == "device_message"
    assert state["symptoms"] == ["error while adding clean water"]


def test_user_written_human_request_still_escalates():
    state = turn(
        {}, "i1", "The robot shows EB1L again and again. Please let me talk to a human.",
        primary_intent="request_human", device_relation="current",
        human_request_quote="Please let me talk to a human",
    )
    assert state["turn_decision"]["escalation_trigger"] == "R3"
    assert state["turn_decision"]["human_request_source"] == "user_statement"


def test_negated_and_uncertain_polarity_are_kept_but_handled():
    state = turn(
        {}, "i1", "I have a S1 pump, the left one does work, no smoke though",
        primary_intent="report_problem", device_relation="current", product_hints=["S1 pump"],
        facts=[
            {"value": "left side does work", "quote": "the left one does work", "subject": "left pump", "polarity": "uncertain"},
            {"value": "no smoke", "quote": "no smoke though", "polarity": "negated"},
        ],
    )
    facts = state["issues"][state["active_issue_id"]]["facts"]
    assert [(f["polarity"], f["subject"]) for f in facts] == [("uncertain", "left pump"), ("negated", None)]
    assert state["symptoms"] == ["left side does work"]


def test_action_taken_overrides_operation_update():
    """T31：「despite wiping clean the electrical connections」是已做过的排查，不是操作条件变更。"""
    state = turn(
        {}, "i1", "The robot won't charge despite wiping clean the electrical connections",
        primary_intent="report_problem", device_relation="current",
        facts=[
            {"value": "won't charge at base", "quote": "The robot won't charge", "timing": None},
            {"kind": "action_taken", "value": "wiped electrical connections", "quote": "wiping clean the electrical connections"},
        ],
        operation_update={"signal": "device_ready", "quote": "wiping clean the electrical connections"},
    )
    assert state["turn_decision"]["operation_changed"] is False
    kinds = [f["kind"] for f in state["issues"][state["active_issue_id"]]["facts"]]
    assert kinds == ["symptom", "action_taken"]
    assert state["symptoms"] == ["won't charge at base"]


def test_quote_tolerates_a_typo_on_one_edge_word():
    """T34 复跑：原文「siscovered i had lost the maps」，模型引文把首词纠成 discovered，整条症状因此丢失。
    引文 ≥ 4 词且去掉首词或末词后仍是逐字片段，仍算有依据；短引文不放宽。"""
    from app.conversation.quotes import quoted

    text = "i just now tried to use the robot and siscovered i had lost the maps. i cannot use them"
    assert quoted("discovered i had lost the maps", text)
    assert quoted("i had lost the maps.", text)
    assert not quoted("lost maps", text)
    assert not quoted("discovered i had", text)
    assert not quoted("discovered i had lost the chart", text)



# ---- intake 的英文现象描述只用于检索（search_query_en，2026-10-11） ----

T43 = "Nombre del producto: X10 Pro Omni\nNúmero de parte del producto: T2351\nDescripción del problema: El robot está desconectado."


def test_english_search_query_is_kept_for_retrieval_only():
    state = turn({}, "i1", T43, primary_intent="report_problem", device_relation="current", product_hints=["X10 Pro Omni"],
                 facts=[{"value": "desconectado", "quote": "El robot está desconectado."}],
                 search_query_en="robot is disconnected")
    assert state["search_query_en"] == "robot is disconnected"
    # 不是事实，不进症状 / 观察 / 标题
    issue = state["issues"][state["active_issue_id"]]
    assert all("disconnected" not in f["value"] for f in issue["facts"])
    assert "robot is disconnected" not in state["symptoms"] and "robot is disconnected" not in issue["title"]


def test_english_search_query_needs_a_symptom_and_no_invented_codes():
    # 没有现象的轮次不记（只有情绪 / 订单问题）
    none = turn({}, "i1", "Where is my order Anker001?", primary_intent="logistics_query", search_query_en="order not delivered")
    assert none.get("search_query_en") is None
    # 原文没有的型号 / 错误码不收（会把检索带偏）
    invented = turn({}, "i1", T43, primary_intent="report_problem", device_relation="current",
                    facts=[{"value": "desconectado", "quote": "El robot está desconectado."}],
                    search_query_en="robot offline error 5112")
    assert invented.get("search_query_en") is None
    kept = turn({}, "i1", T43, primary_intent="report_problem", device_relation="current",
                facts=[{"value": "desconectado", "quote": "El robot está desconectado."}],
                search_query_en="X10 Pro Omni T2351 robot is disconnected")
    assert kept["search_query_en"] == "X10 Pro Omni T2351 robot is disconnected"


def test_english_search_query_follows_the_issue_and_later_symptoms():
    """评审 §7：摘要绑定本轮事实；没有新现象的轮次沿用，新现象替换，切换到另一台设备的问题不带过去。"""
    state = turn({}, "i1", T43, primary_intent="report_problem", device_relation="current", product_hints=["X10 Pro Omni"],
                 facts=[{"value": "desconectado", "quote": "El robot está desconectado."}], search_query_en="robot is disconnected")
    follow = turn(state, "i2", "¿Y ahora?", primary_intent="unknown", device_relation="current")
    assert follow["search_query_en"] == "robot is disconnected"
    detail = turn(follow, "i3", "La app dice que el robot está sin conexión.", primary_intent="supplement", device_relation="current",
                  facts=[{"value": "app shows offline", "quote": "La app dice que el robot está sin conexión."}],
                  search_query_en="app shows robot offline")
    assert detail["search_query_en"] == "app shows robot offline"
    other = turn(detail, "i4", "Mis auriculares no suenan", primary_intent="report_problem", device_relation="other",
                 product_hints=["auriculares"], device_category="earbuds", facts=[{"value": "no suenan", "quote": "no suenan"}])
    assert other["active_issue_id"] != detail["active_issue_id"] and other.get("search_query_en") is None


def test_english_search_query_is_dropped_when_a_fact_is_corrected_without_a_new_symptom():
    """评审 §7：更正了事实、本轮没有新现象时，按更正前事实写的英文描述作废，不能继续参与检索。"""
    state = turn({}, "i1", T43, primary_intent="report_problem", device_relation="current", product_hints=["X10 Pro Omni"],
                 facts=[{"value": "desconectado", "quote": "El robot está desconectado."}], search_query_en="robot is disconnected")
    fact_id = state["issues"][state["active_issue_id"]]["facts"][0]["fact_id"]
    corrected = turn(state, "i2", "Perdón, no está desconectado, no carga.", primary_intent="correct", device_relation="current",
                     corrections=[{"fact_id": fact_id, "value": "no carga", "quote": "no carga"}])
    assert corrected.get("search_query_en") is None


def test_over_long_english_search_query_is_clipped_not_rejected():
    """只用于检索的字段超长时截断，不让整轮 intake 输出校验失败（意图 / 事实全部作废）。"""
    meaning = TurnInterpretation.model_validate({"primary_intent": "report_problem", "device_relation": "current",
                                                 "search_query_en": "robot is disconnected " * 20})
    assert len(meaning.search_query_en) == 160
