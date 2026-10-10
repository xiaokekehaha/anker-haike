"""回答承接（2026-10-10 多轮复现 P1）：用户对当前问题 / 步骤的回答先绑定到那张卡，再判断新事实要不要撤卡；同一澄清答过不再问。

- T46 文字补测：问题卡「continuous or intermittent」用文字回答，新增症状先撤卡，命令解析看不到卡，回「There's nothing waiting」。
- T22：操作卡下文字回答「平地持续报错」，模型同时给反馈与新症状，卡被撤掉，反馈没进 step_attempts，再发同一张禁区卡。
- T52：充电对象冲突的模板追问，用户回答后原样再问。
模型与知识库均为假。
"""

from __future__ import annotations

import pytest

from app.conversation.commands import resolve_command
from app.conversation.interpret import TurnInterpretation
from app.knowledge.runtime import set_knowledge_adapter
from app.sessions.graph import _diagnose_outcome
from tests.conversation_runtime import conversation as base_conversation_fixture
from tests.fake_qa import QAHitAdapter
from tests.test_conversation_l3 import l3_runtime as l3_runtime_fixture

base_conversation = base_conversation_fixture
l3_runtime = l3_runtime_fixture

NOISE = "My S1 Pro breast pump motor is making abnormal noise"
NOISE_MEANING = {
    "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["S1 Pro breast pump"],
    "facts": [{"value": "motor making abnormal noise", "quote": "motor is making abnormal noise", "subject": "motor"}],
}
CONTINUOUS = "The noise is continuous while the pump is running."


@pytest.fixture
async def conversation(l3_runtime, base_conversation):
    yield base_conversation


async def _question_card(conversation):
    set_knowledge_adapter(QAHitAdapter("bp-0123"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_bp_0123", "confidence": 0.9, "evidence_ids": ["chunk-bp-0123"],
        "applicability": "supported", "supported_symptoms": ["motor making abnormal noise"],
    }]}]
    events = await conversation.send(NOISE, NOISE_MEANING)
    card = next(e for e in events if e["type"] == "step_card")
    assert card["step"]["step_id"] == "s2"


async def test_t46_text_answer_to_question_card_advances_like_a_card_answer(conversation):
    """T46 文字补测：同一句回答走文字入口，也要消费问题卡、写 step_attempts、推进到 s3。"""
    await _question_card(conversation)
    events = await conversation.send(CONTINUOUS, {
        "primary_intent": "answer_pending", "device_relation": "current",
        "pending_answer": {"kind": "step_answer", "payload": {"option": "continuous"}, "quote": "continuous"},
        "facts": [{"value": "Noise is continuous while the pump is running", "quote": CONTINUOUS.rstrip(".")}],
    })
    assert not any("nothing waiting" in (e.get("delta") or "") for e in events)
    nxt = next(e for e in events if e["type"] == "step_card")
    assert nxt["step"]["step_id"] == "s3"
    state = await conversation.state()
    attempt = state["step_attempts"][-1]
    assert attempt["step_id"] == "s2" and attempt["answer"]["option"] == "continuous"
    assert any(f["value"] == "Noise is continuous while the pump is running" for f in state["issues"][state["active_issue_id"]]["facts"])


async def test_feedback_shaped_reply_to_question_card_is_recorded_as_text_answer(conversation):
    """问句没有「解决 / 没解决」语义：模型给了 feedback 时按原话当文字回答，不报「不匹配」。"""
    await _question_card(conversation)
    events = await conversation.send(CONTINUOUS, {
        "primary_intent": "step_feedback", "device_relation": "current",
        "feedback": "not_solved", "feedback_quote": CONTINUOUS,
        "facts": [{"value": "Noise is continuous while the pump is running", "quote": CONTINUOUS.rstrip(".")}],
    })
    nxt = next(e for e in events if e["type"] == "step_card")
    assert nxt["step"]["step_id"] == "s3"
    state = await conversation.state()
    assert state["step_attempts"][-1]["answer"]["text"] == CONTINUOUS
    assert state["counters"].get("executed", 0) == 0


def _state(text, *, kind="action", options=(), patches=()):
    step = {"step_id": "s2", "kind": kind, "options": list(options)}
    return {
        "entry": "message", "input_id": "i2", "base_version": 1, "active_issue_id": "issue", "text": text,
        "pending_card": {"kind": "step_feedback", "card_id": "c1", "input_token": "token", "payload": {"step": step}},
        "turn_decision": {"allowed_operations": True, "patches": list(patches)},
    }


def test_new_fact_alongside_feedback_does_not_block_the_command():
    """T22：反馈与新增现象同句出现，新增现象（add）不是纠正，反馈照常提交。"""
    meaning = TurnInterpretation(primary_intent="step_feedback", feedback="not_solved",
                                 feedback_quote="This happens continuously on an open, flat floor.")
    command, error = resolve_command(
        _state("This happens continuously on an open, flat floor.", patches=[{"op": "add"}]), meaning)
    assert error is None and command["payload"]["feedback"] == "not_solved"
    corrected = _state("This happens continuously on an open, flat floor.", patches=[{"op": "replace"}])
    assert resolve_command(corrected, meaning)[0] is None


def test_step_answer_option_must_be_on_the_card():
    meaning = TurnInterpretation(primary_intent="answer_pending", pending_answer={
        "kind": "step_answer", "payload": {"option": "sometimes"}, "quote": "sometimes"})
    command, error = resolve_command(_state("sometimes", kind="question", options=["continuous", "intermittent"]), meaning)
    assert command is None and error


def test_step_answer_on_action_card_is_rejected():
    meaning = TurnInterpretation(primary_intent="answer_pending", pending_answer={
        "kind": "step_answer", "payload": {"text": "continuous"}, "quote": "continuous"})
    command, error = resolve_command(_state("continuous"), meaning)
    assert command is None and error


async def test_t22_feedback_with_new_symptom_keeps_the_card_and_records_feedback(conversation):
    """T22：错误码精确命中 rv-0106，用户说平地持续报错，反馈要落到 s1，不再重发 s1。"""
    set_knowledge_adapter(QAHitAdapter("rv-0106"))
    text = ("Productnaam: X10 Pro Omni\nProduct-PN: T2351\nProbleemtype: WARNING\nProbleemcode: 7002-De robot zweeft in de lucht.\n"
            "Probleempush: Wiel raakt de grond niet, verplaats de robot naar een nieuwe positie.\n"
            "Probleembeschrijving: Wiel raakt de grond niet.\n")
    events = await conversation.send(text, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
        "facts": [{"value": "Wiel raakt de grond niet", "quote": "Wiel raakt de grond niet"}],
    })
    first = next(e for e in events if e["type"] == "step_card")
    assert first["step"]["step_id"] == "s1"
    reply = "This happens continuously on an open, flat floor. It has not been stuck at stairs or furniture."
    events = await conversation.send(reply, {
        "primary_intent": "step_feedback", "device_relation": "current",
        "feedback": "not_solved", "feedback_quote": reply,
        "facts": [{"value": "Happens continuously on an open, flat floor", "quote": "This happens continuously on an open, flat floor"}],
    })
    assert not any("nothing waiting" in (e.get("delta") or "") for e in events)
    state = await conversation.state()
    assert [(a["step_id"], a["feedback"]) for a in state["step_attempts"]] == [("s1", "not_solved")]
    nxt = next(e for e in events if e["type"] == "step_card")
    assert nxt["step"]["step_id"] == "s2"


CHARGING_Q = "When the charging case itself is connected to power, what does its charging indicator show?"


def test_t52_same_clarification_answered_once_is_not_asked_again():
    """T52：对象冲突的模板追问已经问过、用户也答了，同类冲突不再追问（换对象也不问）；没有其他候选时交接。"""
    clar = [{"plan_id": "qa_bp_0039", "question": CHARGING_Q, "evidence_ids": ["e1"], "confidence": 0.55,
             "reason": "charging_recipient_mismatch"}]
    first = _diagnose_outcome([], knowledge_status="ok", exact_hits=[], clarifications=clar, previous_outcome=None, state={})
    assert first["diagnose_outcome"]["mode"] == "clarify" and first["diagnose_outcome"]["question"] == CHARGING_Q
    second = _diagnose_outcome([], knowledge_status="ok", exact_hits=[], clarifications=clar,
                               previous_outcome=first["diagnose_outcome"], state={})
    assert second["diagnose_outcome"]["mode"] != "clarify"
    # 真实复跑：候选换成 bp-0127 后改问「泵自身接电时指示灯」——同一类冲突，不再问
    pump = [{**clar[0], "plan_id": "qa_bp_0127",
             "question": "When the pump itself is connected to power, what does its charging indicator show?"}]
    assert _diagnose_outcome([], knowledge_status="ok", exact_hits=[], clarifications=pump,
                             previous_outcome=first["diagnose_outcome"], state={})["diagnose_outcome"]["mode"] != "clarify"
    timing = [{**clar[0], "question": "You said it happened 2 hours before. Is that right?", "reason": "timing_mismatch"}]
    third = _diagnose_outcome([], knowledge_status="ok", exact_hits=[], clarifications=[*clar, *timing],
                              previous_outcome=first["diagnose_outcome"], state={})
    assert third["diagnose_outcome"]["question"] == timing[0]["question"]
