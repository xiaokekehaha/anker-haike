"""步骤先对事实（2026-10-10 多轮复现 P2 / P3）。

- T22：rv-0106 两步都是条件建议。用户说「平地持续报错、没卡在楼梯或家具」→ s1 条件否定、s2 条件成立，直接发 s2（重启）。
- T46 原评测：用户先在文字澄清里说了「continuous while the pump is running」，进 bp-0123 后不再问 s2「连续还是间歇」。
模型只给判定和引文；服务端校验引文逐字出自用户原话、选项逐字在卡上。模型与知识库均为假。
"""

from __future__ import annotations

import pytest

from app.guide.fact_check import StepCheck, _skips, accept, candidates
from app.knowledge.runtime import set_knowledge_adapter
from app.plans.qa import qa_plan_library, step_condition
from tests.conversation_runtime import conversation as base_conversation_fixture
from tests.fake_qa import QAHitAdapter
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


def test_sibling_condition_satisfied_skips_the_earlier_unknown_one():
    plan = LIB.get("qa_rv_0106")
    assert _skips(plan, {"s2": {"status": "satisfied", "quote": "flat floor"}}) == {
        "s1": {"status": "unknown", "skip": True}, "s2": {"status": "satisfied", "quote": "flat floor"}}
    assert _skips(plan, {"s1": {"status": "negated", "quote": "not been stuck"}})["s1"]["skip"] is True
    assert "s2" not in _skips(plan, {"s1": {"status": "negated", "quote": "not been stuck"}})
    assert _skips(plan, {"s1": {"status": "satisfied", "quote": "stuck on stairs"}}) == {"s1": {"status": "satisfied", "quote": "stuck on stairs"}}


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
