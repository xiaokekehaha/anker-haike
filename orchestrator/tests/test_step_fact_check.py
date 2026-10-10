"""步骤先对事实（2026-10-10 多轮复现 P2 / P3）。

- T22：rv-0106 两步都是条件建议。用户说「平地持续报错、没卡在楼梯或家具」→ s1 条件否定、s2 条件成立，直接发 s2（重启）。
- T46 原评测：用户先在文字澄清里说了「continuous while the pump is running」，进 bp-0123 后不再问 s2「连续还是间歇」。
模型只给判定和引文；服务端校验引文逐字出自用户原话、选项逐字在卡上。模型与知识库均为假。
"""

from __future__ import annotations

import pytest

from app.guide.fact_check import StepCheck, _skips, _steps_text, accept, candidates
from app.knowledge.runtime import set_knowledge_adapter
from app.plans.qa import qa_plan_library, step_condition
from tests.conversation_runtime import conversation as base_conversation_fixture
from tests.fake_qa import QAHitAdapter
from tests.test_conversation_l3 import act
from tests.test_conversation_l3 import l3_runtime as l3_runtime_fixture

base_conversation = base_conversation_fixture
l3_runtime = l3_runtime_fixture
LIB = qa_plan_library()
FLAT = "This happens continuously on an open, flat floor. It has not been stuck at stairs or furniture."


@pytest.fixture
async def conversation(l3_runtime, base_conversation):
    yield base_conversation


@pytest.mark.parametrize(("text", "condition"), [
    ("If the robot is often stuck on the edge of stairs or furniture and triggers this warning, it is recommended to set a no-go zone.",
     "the robot is often stuck on the edge of stairs or furniture and triggers this warning"),
    ("If the robot continues to display errors on flat ground, please try restarting the robot.",
     "the robot continues to display errors on flat ground"),
    ("If the error persists after restarting, please try unplugging the base station.", None),
    ("If heating still fails, try placing the speaker covers crosswise.", None),
    ("Restart the robot and try again.", None),
])
def test_step_condition_keeps_scenarios_and_skips_follow_ups(text, condition):
    assert step_condition(text) == condition


def test_accept_requires_user_quote_and_card_option():
    plan = LIB.get("qa_bp_0123")
    steps = candidates(plan, {})
    corpus = ["The noise is continuous while the pump is running."]
    out = accept(steps, [
        StepCheck(step_id="s2", status="answered", option="continuous", quote="continuous while the pump is running"),
        StepCheck(step_id="s3", status="answered", option="Upon startup", quote="it starts when I turn it on"),  # 引文不在原话里
        StepCheck(step_id="s4", status="satisfied", quote="continuous"),  # 问句只能 answered
        StepCheck(step_id="s9", status="answered", text="x", quote="continuous"),  # 不是候选步骤
    ], corpus)
    assert out == {"s2": {"status": "answered", "option": "continuous", "text": None, "quote": "continuous while the pump is running"}}
    free = accept(steps, [StepCheck(step_id="s3", status="answered", option="while running", text="While pumping",
                                    quote="while the pump is running")], corpus)
    assert free["s3"] == {"status": "answered", "option": None, "text": "While pumping", "quote": "while the pump is running"}


BOTH = {"s1", "s2"}


def test_sibling_condition_satisfied_skips_the_earlier_unknown_one():
    plan = LIB.get("qa_rv_0106")
    assert _skips(plan, {"s2": {"status": "satisfied", "quote": "flat floor"}}, BOTH) == {
        "s1": {"status": "unknown", "skip": True}, "s2": {"status": "satisfied", "quote": "flat floor"}}
    assert _skips(plan, {"s1": {"status": "negated", "quote": "not been stuck"}}, BOTH)["s1"]["skip"] is True
    assert "s2" not in _skips(plan, {"s1": {"status": "negated", "quote": "not been stuck"}}, BOTH)
    assert _skips(plan, {"s1": {"status": "satisfied", "quote": "stuck on stairs"}}, BOTH) == {
        "s1": {"status": "satisfied", "quote": "stuck on stairs"}}


def test_negated_verdict_alone_cannot_exhaust_the_plan():
    """T22 复测 B06-r2：s1 已反馈，只剩 s2；模型把平地条件误判 negated。最后一个可发步骤照发，不因一次判定转人工。"""
    plan = LIB.get("qa_rv_0106")
    kept = _skips(plan, {"s2": {"status": "negated", "quote": "x"}}, {"s2"})
    assert kept["s2"]["skip"] is False
    both = _skips(plan, {"s1": {"status": "negated", "quote": "a"}, "s2": {"status": "negated", "quote": "b"}}, BOTH)
    assert both["s1"]["skip"] is True and both["s2"]["skip"] is False


def test_handled_sibling_conditions_are_shown_as_reference():
    """只剩一条条件时把已处理的兄弟条件作对照给模型，模型才分得清原话里的否定句针对哪个场景。"""
    plan = LIB.get("qa_rv_0106")
    state = {"step_attempts": [{"plan_id": "qa_rv_0106", "step_id": "s1", "instruction_src": "evidence:rv-0106#s1",
                                "kind": "action", "feedback": "not_solved"}]}
    steps = candidates(plan, state)
    assert [s.step_id for s in steps] == ["s2"]
    text = _steps_text(steps, LIB, [s for s in plan.steps if s.condition and s not in steps])
    assert "s1 [reference] the robot is often stuck on the edge of stairs" in text
    assert "s2 [action] [condition] the robot continues to display errors on flat ground" in text
    # 模型即便输出了对照步骤的判定，也不采纳
    assert accept(steps, [StepCheck(step_id="s1", status="negated", quote="has not been stuck")],
                  ["It has not been stuck at stairs or furniture."]) == {}


T22 = ("Productnaam: X10 Pro Omni\nProduct-PN: T2351\nProbleemtype: WARNING\nProbleemcode: 7002-De robot zweeft in de lucht.\n"
       "Probleempush: Wiel raakt de grond niet, verplaats de robot naar een nieuwe positie.\n"
       "Probleembeschrijving: Wiel raakt de grond niet.\n")


async def test_t22_flat_floor_goes_straight_to_the_restart_branch(conversation):
    """T22 首封就说平地持续报错：精确错误码命中 rv-0106 后不发楼梯 / 家具禁区卡，直接发 s2。"""
    set_knowledge_adapter(QAHitAdapter("rv-0106"))
    conversation.models["guide.step"].script = [{"steps": [
        {"step_id": "s1", "status": "negated", "quote": "It has not been stuck at stairs or furniture"},
        {"step_id": "s2", "status": "satisfied", "quote": "This happens continuously on an open, flat floor"},
    ]}]
    events = await conversation.send(T22 + FLAT, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
        "facts": [{"value": "Wiel raakt de grond niet", "quote": "Wiel raakt de grond niet"},
                  {"value": "Happens continuously on an open, flat floor", "quote": "This happens continuously on an open, flat floor"}],
    })
    card = next(e for e in events if e["type"] == "step_card")
    assert card["step"]["step_id"] == "s2"
    state = await conversation.state()
    assert state["step_checks"]["qa_rv_0106"]["steps"]["s1"]["skip"] is True
    assert any(t.get("event") == "fact_check" for t in state["guide_trace"])


async def test_t22_second_turn_feedback_and_condition_both_advance(conversation):
    """T22 两轮：首卡 s1；用户回「平地持续」→ 反馈记到 s1，下一张是 s2，不重发 s1。"""
    set_knowledge_adapter(QAHitAdapter("rv-0106"))
    conversation.models["guide.step"].script = [{"steps": []}]
    events = await conversation.send(T22, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
        "facts": [{"value": "Wiel raakt de grond niet", "quote": "Wiel raakt de grond niet"}],
    })
    assert next(e for e in events if e["type"] == "step_card")["step"]["step_id"] == "s1"
    events = await conversation.send(FLAT, {
        "primary_intent": "step_feedback", "device_relation": "current", "feedback": "not_solved", "feedback_quote": FLAT,
        "facts": [{"value": "Happens continuously on an open, flat floor", "quote": "This happens continuously on an open, flat floor"}],
    })
    assert next(e for e in events if e["type"] == "step_card")["step"]["step_id"] == "s2"


async def test_t46_question_already_answered_in_text_is_not_asked(conversation):
    """T46 原评测：首封就说了连续 + 泵运行时，进 bp-0123 后跳过 s2 / s3，直接到 s4。"""
    set_knowledge_adapter(QAHitAdapter("bp-0123"))
    text = "My S1 Pro breast pump motor is making abnormal noise. The noise is continuous, during breast pumping."
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_bp_0123", "confidence": 0.9, "evidence_ids": ["chunk-bp-0123"],
        "applicability": "supported", "supported_symptoms": ["motor making abnormal noise"],
    }]}]
    conversation.models["guide.step"].script = [{"steps": [
        {"step_id": "s2", "status": "answered", "option": "continuous", "quote": "The noise is continuous"},
        {"step_id": "s3", "status": "answered", "option": "During breast pumping", "quote": "during breast pumping"},
        {"step_id": "s4", "status": "answered", "text": "no", "quote": "suction is fine"},  # 原话里没有 → 不采纳
    ]}]
    events = await conversation.send(text, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["S1 Pro breast pump"],
        "facts": [{"value": "motor making abnormal noise", "quote": "motor is making abnormal noise", "subject": "motor"}],
    })
    card = next(e for e in events if e["type"] == "step_card")
    assert card["step"]["step_id"] == "s4"
    state = await conversation.state()
    recorded = [(a["step_id"], a["answer"]["option"], a["answer"]["source"]) for a in state["step_attempts"]]
    assert recorded == [("s2", "continuous", "fact"), ("s3", "During breast pumping", "fact")]
    assert state["counters"].get("executed", 0) == 0


async def test_fact_check_failure_falls_back_to_the_first_step(conversation):
    """判定不可用（脚本耗尽 = 模型失败）时照常从首步发卡，不阻塞排障。"""
    set_knowledge_adapter(QAHitAdapter("rv-0106"))
    conversation.models["guide.step"].script = []
    events = await conversation.send(T22 + FLAT, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
        "facts": [{"value": "Happens continuously on an open, flat floor", "quote": "This happens continuously on an open, flat floor"}],
    })
    assert next(e for e in events if e["type"] == "step_card")["step"]["step_id"] == "s1"


async def test_t22_feedback_then_misjudged_restart_condition_still_sends_restart(conversation):
    """T22 复测 B06-r2：第二轮模型同时给反馈（s1 记 not_solved），条件判定又把 s2 判 negated；仍发 s2，不进质保。"""
    set_knowledge_adapter(QAHitAdapter("rv-0106"))
    events = await conversation.send(T22, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
        "facts": [{"value": "Wiel raakt de grond niet", "quote": "Wiel raakt de grond niet"}],
    })
    assert next(e for e in events if e["type"] == "step_card")["step"]["step_id"] == "s1"
    conversation.models["guide.step"].script = [{"steps": [{"step_id": "s2", "status": "negated", "quote": FLAT}]}]
    events = await conversation.send(FLAT, {
        "primary_intent": "report_problem", "secondary_intents": ["step_feedback"], "device_relation": "current",
        "feedback": "not_solved", "feedback_quote": FLAT,
        "facts": [{"value": "Happens continuously on an open, flat floor", "quote": "This happens continuously on an open, flat floor"}],
    })
    assert next(e for e in events if e["type"] == "step_card")["step"]["step_id"] == "s2"
    state = await conversation.state()
    assert state["stage"] == "guide" and not state.get("escalate_reason")
    assert state["step_checks"]["qa_rv_0106"]["steps"]["s2"]["kept"] == "last_step"
    prompt = str(conversation.models["guide.step"].calls[-1])
    assert "s1 [reference]" in prompt


def test_app_report_with_error_code_is_never_a_product_question():
    """T22 复跑：带 7002 的 App 报错表单被判 product_question，走产品咨询不发卡。带码表单一律按故障。"""
    from app.conversation.interpret import TurnInterpretation, device_code_report

    meaning = TurnInterpretation(primary_intent="product_question", secondary_intents=["report_problem", "logistics_query"])
    fixed = device_code_report(meaning, T22)
    assert fixed.primary_intent == "report_problem" and fixed.secondary_intents == ["logistics_query"]
    question = TurnInterpretation(primary_intent="product_question")
    assert device_code_report(question, "How do I set a no-go zone on my X10 Pro Omni?").primary_intent == "product_question"
    # 接在模型输出与降级规则共用的纠正入口上
    from app.conversation.interpret import logistics_correction
    assert logistics_correction(meaning, T22).primary_intent == "report_problem"


async def test_error_code_from_an_earlier_turn_still_hits_the_official_guide(conversation):
    """首轮表单没进排障（意图被读成别的）；第二轮只报现象，错误码仍从本问题首轮原话取，精确命中 rv-0106。"""
    set_knowledge_adapter(QAHitAdapter("rv-0106"))
    conversation.models["guide.step"].script = [{"steps": [
        {"step_id": "s1", "status": "negated", "quote": "It has not been stuck at stairs or furniture"},
        {"step_id": "s2", "status": "satisfied", "quote": "This happens continuously on an open, flat floor"},
    ]}]
    await conversation.send(T22, {
        "primary_intent": "history_query", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
        "facts": [{"value": "Wiel raakt de grond niet", "quote": "Wiel raakt de grond niet"}],
    })
    conversation.models["diagnose.synthesize"].script = []
    events = await conversation.send(FLAT, {
        "primary_intent": "report_problem", "device_relation": "current",
        "facts": [{"value": "Happens continuously on an open, flat floor", "quote": "This happens continuously on an open, flat floor"}],
    })
    card = next(e for e in events if e["type"] == "step_card")
    assert (card["step"]["plan_id"], card["step"]["step_id"]) == ("qa_rv_0106", "s2")
    state = await conversation.state()
    assert state["error_codes"] == ["7002"] and state["plans_ranked"][0]["source"] == "exact_code"
    assert not conversation.models["diagnose.synthesize"].calls


# ---- 已做过的操作步骤（2026-10-10 官方 63 单复测 P1：T16 T27 T31 T37）----

T16 = ("Product Name: X10 Pro Omni\nProduct PN: T2351\nProduct SN:\nProblem Type: WARNING\n"
       "Problem Code: 2310-The dust box or filter is not in place.\nProblem Push: Please insert dustbin and filter.\n"
       "Problem Description: The dustbin or filter is not installed. It is fully installed and clean\nProblem Upload Images: []")


def test_done_action_requires_a_customer_quote_not_the_device_push():
    """「Please insert dustbin and filter」是设备推送，不能当成客户装过；「It is fully installed and clean」才是。"""
    plan = LIB.get("qa_rv_0056")
    steps = candidates(plan, {})
    assert [s.step_id for s in steps] == ["s1", "s2"]
    push = "Please insert dustbin and filter."
    assert accept(steps, [StepCheck(step_id="s1", status="done", quote="Please insert dustbin and filter")], [T16], push) == {}
    assert accept(steps, [StepCheck(step_id="s1", status="done", quote="It is fully installed and clean")], [T16], push) == {
        "s1": {"status": "done", "quote": "It is fully installed and clean"}}
    # 没有条件的操作步骤不接受条件判定
    assert accept(steps, [StepCheck(step_id="s1", status="negated", quote="It is fully installed and clean")], [T16], push) == {}


def test_done_action_can_exhaust_the_plan_unlike_a_negated_condition():
    """T37：唯一一步（空箱加水）客户已说水箱满；跳过后计划耗尽，按 SOP 进质保，不再让客户加水。"""
    plan = LIB.get("qa_rv_0021")
    assert _skips(plan, {"s1": {"status": "done", "quote": "tank is full"}}, {"s1"}) == {
        "s1": {"status": "done", "quote": "tank is full", "skip": True}}


async def test_t16_installed_filter_goes_straight_to_the_magnet_check(conversation):
    """T16：表单描述已写「It is fully installed and clean」，首卡不再问滤网装没装，直接查磁铁。"""
    set_knowledge_adapter(QAHitAdapter("rv-0056"))
    conversation.models["guide.step"].script = [{"steps": [
        {"step_id": "s1", "status": "done", "quote": "It is fully installed and clean"},
        {"step_id": "s2", "status": "satisfied", "quote": "It is fully installed and clean"},
    ]}]
    events = await conversation.send(T16, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
        "facts": [{"value": "dustbin or filter not installed warning while fully installed",
                   "quote": "The dustbin or filter is not installed. It is fully installed and clean"}],
    })
    card = next(e for e in events if e["type"] == "step_card")
    assert (card["step"]["plan_id"], card["step"]["step_id"]) == ("qa_rv_0056", "s2")
    # 跳过的那一步在下一张卡上说明，并引客户原话
    assert 'I\'ve skipped "' in card["step"]["context"] and "It is fully installed and clean" in card["step"]["context"]
    state = await conversation.state()
    assert state["step_checks"]["qa_rv_0056"]["steps"]["s1"] == {
        "status": "done", "quote": "It is fully installed and clean", "skip": True}
    assert state["counters"].get("executed", 0) == 0


async def test_form_with_only_the_device_push_does_not_call_the_check(conversation):
    """描述字段只是推送原文时没有客户自己的话，不调用核对，照常从首步发卡。"""
    set_knowledge_adapter(QAHitAdapter("rv-0056"))
    text = T16.replace("The dustbin or filter is not installed. It is fully installed and clean", "Please insert dustbin and filter.")
    events = await conversation.send(text, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
        "facts": [{"value": "insert dustbin and filter", "quote": "Please insert dustbin and filter."}],
    })
    assert next(e for e in events if e["type"] == "step_card")["step"]["step_id"] == "s1"
    assert not conversation.models["guide.step"].calls


T37 = ("Productnaam: Omni E28\nProduct-PN: T2352\nProbleemtype: issue\nProbleemomschrijving: Ik krijg steeds de melding in de app "
       "“voeg water toe” als de dweil wordt gewassen. Terwijl de schoonwater tank nog vol is. De robot gaat vervolgens over op alleen vegen.\n\n"
       "Slang in tank is in orde. Rubbers zijn in orde. Hoe op te lossen?\nGeüploade afbeeldingen van het probleem: []")


async def test_t37_full_tank_does_not_get_the_refill_card(conversation, l3_runtime):
    """T37：客户说水箱是满的，唯一一步「空了就加水」不再发；计划耗尽后不发卡，进入下一步决策（质保 / 人工）。"""
    set_knowledge_adapter(QAHitAdapter("rv-0021"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_rv_0021", "confidence": 0.8, "evidence_ids": ["chunk-rv-0021"],
        "applicability": "supported", "supported_symptoms": ["add water warning while clean water tank is full"],
    }]}]
    conversation.models["guide.step"].script = [{"steps": [
        {"step_id": "s1", "status": "done", "quote": "Terwijl de schoonwater tank nog vol is"}]}]
    events = await conversation.send(T37, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["Omni E28"],
        "facts": [{"value": "add water warning while clean water tank is full",
                   "quote": "Terwijl de schoonwater tank nog vol is"}],
    })
    assert not any(e["type"] == "step_card" for e in events)
    # 唯一一步被跳过、计划耗尽：没有下一张卡，跳过说明作为消息发出
    said = "".join(e.get("delta", "") for e in events if e["type"] == "message")
    assert 'I\'ve skipped "' in said and "Terwijl de schoonwater tank nog vol is" in said
    state = await conversation.state()
    assert state["step_checks"]["qa_rv_0021"]["steps"]["s1"]["skip"] is True
    assert "qa_rv_0021" in state["exhausted_plans"]


T36 = ("Productnaam: S1 Pro\nProduct-PN: T2080A\nProbleemtype: Probleem met het toestel\nProbleemomschrijving: Tijdens het "
       "stofzuigen maakt de stofzuiger enorm veel geluid. Alle filters en borstels zijn vervangen en alles is schoongemaakt maar "
       "het harde geluid blijft. Ik ben bang dat de stofzuigermotor kapot gaat.\nGeüploade afbeeldingen van het probleem: []")


async def test_t36_replaced_filters_skip_the_filter_clog_check(conversation, l3_runtime):
    """T36：客户已换全部滤网和刷子并清洁过。rv-0316 的滤网堵塞检查（s2）跳过并在下一张卡上说明；
    万向轮（没点名）、滚刷盖条与安装位（没换）仍然要查。"""
    set_knowledge_adapter(QAHitAdapter("rv-0316"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_rv_0316", "confidence": 0.8, "evidence_ids": ["chunk-rv-0316"],
        "applicability": "supported", "supported_symptoms": ["loud noise while vacuuming"],
    }]}]
    replaced = "Alle filters en borstels zijn vervangen en alles is schoongemaakt"
    conversation.models["guide.step"].script = [{"steps": [
        {"step_id": "s1", "status": "unknown"}, {"step_id": "s2", "status": "done", "quote": replaced},
        {"step_id": "s3", "status": "unknown"}, {"step_id": "s4", "status": "unknown"}]}]
    events = await conversation.send(T36, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["S1 Pro"],
        "facts": [{"value": "loud noise while vacuuming", "quote": "Tijdens het stofzuigen maakt de stofzuiger enorm veel geluid."},
                  {"kind": "action_taken", "value": "filters and brushes replaced, everything cleaned", "quote": replaced}],
    })
    assert next(e for e in events if e["type"] == "step_card")["step"]["step_id"] == "s1"
    events = conversation.check(await act(conversation.client, conversation.sid, "step_feedback", {"feedback": "not_solved"}))
    card = next(e for e in events if e["type"] == "step_card")["step"]
    assert card["step_id"] == "s3"
    assert "the high-performance filter are clogged" in card["context"] and replaced in card["context"]
