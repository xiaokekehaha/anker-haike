"""文字追问的回答由服务端绑定（docs/claude/spec_2026-10-12-1454_text-question-answer-binding.md）。

会话 44ba4626：前提追问「Is the door latch … fastened securely?」只发文字、不出卡；客户答「yes」，intake 两次标成
step_feedback（feedback=solved / not_solved）。commands.py 无卡就回「There's nothing waiting for an answer right now」，
路由只认 answer_pending / supplement，回答进了 dialogue；同一轮 precondition_answers 却记下了 yes。
现在以 clarification（最后一条助手消息就是该问题）为待答状态，回答与意图标签无关地回到诊断。
"""

from __future__ import annotations

import pytest

from app.sessions.clarify import awaiting_text_answer
from tests.conversation_runtime import REPORT, REPORT_TEXT
from tests.conversation_runtime import conversation as base_conversation_fixture
from tests.test_conversation_l3 import l3_runtime as l3_runtime_fixture

base_conversation = base_conversation_fixture
l3_runtime = l3_runtime_fixture

QUESTION = "Is the hair wrapped around the roller brush?"
NOTHING_WAITING = "nothing waiting for an answer"
CANDIDATE = {"hypotheses": [{
    "plan_id": "qa_rv_0272", "confidence": 0.8, "evidence_ids": ["c12"],
    "applicability": "needs_confirmation", "supported_symptoms": [], "clarification_question": QUESTION,
}]}


@pytest.fixture
async def conversation(l3_runtime, base_conversation):
    yield base_conversation


def said(events):
    return "".join(e.get("delta", "") for e in events)


async def ask(conversation, then=None):
    """首轮发出前提追问；then 是回答之后 synthesize 的下一次输出（默认判可执行，出步骤卡）。"""
    model = conversation.models["diagnose.synthesize"]
    supported = model.script[0]
    model.script = [CANDIDATE, then or supported]
    events = await conversation.send(REPORT_TEXT, REPORT)
    assert QUESTION in said(events) and not any(e["type"] == "step_card" for e in events)
    return model


@pytest.mark.parametrize("meaning", [
    # 44ba4626 原样：无卡却给了步骤反馈
    {"primary_intent": "step_feedback", "feedback": "solved", "feedback_quote": "yes"},
    {"primary_intent": "step_feedback", "feedback": "not_solved", "feedback_quote": "yes"},
    {"primary_intent": "report_problem", "device_relation": "current"},
    {"primary_intent": "answer_pending"},
    {"primary_intent": "unknown"},
    {"primary_intent": "supplement", "device_relation": "current"},
])
async def test_any_label_on_a_reply_returns_to_diagnosis(conversation, meaning):
    model = await ask(conversation)
    events = await conversation.send("yes", meaning)
    assert NOTHING_WAITING not in said(events)
    assert len(model.calls) == 2
    assert any(e["type"] == "step_card" for e in events)
    state = await conversation.state()
    assert [(a["question"], a["answer"]) for a in state["precondition_answers"]] == [(QUESTION, "yes")]
    assert state["clarification"] is None  # 出卡后待答状态清掉，不再关闭检索改写


async def test_reply_without_new_fact_still_reaches_synthesize(conversation):
    """回答「yes」不改事实修订号；不能按 reassess 短路，回答要作为 answered_preconditions 交给 synthesize。"""
    model = await ask(conversation)
    await conversation.send("yes", {"primary_intent": "answer_pending"})
    assert len(model.calls) == 2
    assert "answered_preconditions" in str(model.calls[-1]) and "A: yes" in str(model.calls[-1])


@pytest.mark.parametrize("meaning", [
    {"primary_intent": "history_query", "history_request": {"mode": "first"}},
    {"primary_intent": "explain", "device_relation": "current"},
])
async def test_asking_something_else_keeps_the_question_open(conversation, meaning):
    model = await ask(conversation)
    conversation.models["reply.stream"].script.append(["You first reported that it stopped suctioning."])
    await conversation.send("what did I say first?", meaning)
    assert len(model.calls) == 1
    state = await conversation.state()
    assert not state["precondition_answers"]
    assert (state["clarification"] or {}).get("question") == QUESTION


async def test_request_human_takes_precedence(conversation):
    model = await ask(conversation)
    events = await conversation.send("I want a human agent", {
        "primary_intent": "request_human", "human_request_quote": "I want a human agent"})
    assert len(model.calls) == 1
    assert NOTHING_WAITING not in said(events)
    assert (await conversation.state())["escalate_reason"] == "R3"


def test_a_later_assistant_message_closes_the_question():
    state = {"clarification": {"reason": "applicability", "question": QUESTION},
             "history": [{"role": "assistant", "kind": "message", "text": QUESTION},
                         {"role": "user", "kind": "message", "text": "where is my order?"},
                         {"role": "assistant", "kind": "message", "text": "Your order shipped yesterday."}]}
    assert awaiting_text_answer(state) is None
    state["history"] = state["history"][:1]
    assert awaiting_text_answer(state)["question"] == QUESTION
    # 安抚语 / 转人工提示附在问句前后（acknowledge_current_turn）仍算同一个问题
    state["history"] = [{"role": "assistant", "kind": "message", "text": f"I'm sorry about this. {QUESTION}"}]
    assert awaiting_text_answer(state)


@pytest.mark.parametrize("extra", [
    {"pending_card": {"kind": "step_feedback", "card_id": "c1"}},
    {"escalate_reason": "R5"},
    {"stage": "awaiting_human"},
    {"stage": "done"},
])
def test_cards_and_closed_sessions_are_not_text_questions(extra):
    state = {"clarification": {"reason": "applicability", "question": QUESTION},
             "history": [{"role": "assistant", "kind": "message", "text": QUESTION}], **extra}
    assert awaiting_text_answer(state) is None


def test_no_text_question_keeps_the_original_prompt():
    """不在等文字回答时，无卡的步骤反馈保持原提示。"""
    from app.conversation.commands import resolve_command
    from app.conversation.interpret import TurnInterpretation

    meaning = TurnInterpretation(primary_intent="step_feedback", feedback="solved", feedback_quote="yes")
    state = {"entry": "message", "text": "yes", "pending_card": None, "clarification": None,
             "history": [{"role": "assistant", "kind": "message", "text": "Glad it is working now."}]}
    assert NOTHING_WAITING in resolve_command(state, meaning)[1]
    state["clarification"] = {"reason": "applicability", "question": QUESTION}
    state["history"].append({"role": "assistant", "kind": "message", "text": QUESTION})
    assert resolve_command(state, meaning) == (None, None)


async def test_degraded_intake_shows_its_explanation(conversation, monkeypatch):
    """intake 理解失败（budget / 模型不可用）给出的说明文案要让用户看到，不当作回答。"""
    import app.conversation.interpret as semantic
    from app.conversation.interpret import TurnInterpretation

    model = await ask(conversation)
    note = "我暂时无法完成这次理解，已有信息仍会保留。请指出要查询的信息或要继续的步骤。"

    async def degraded(router, state, **kwargs):
        return TurnInterpretation(primary_intent="unknown", clarification=note), {"source": "degraded"}

    monkeypatch.setattr(semantic, "interpret_turn", degraded)
    response = await conversation.client.post(
        f"/sessions/{conversation.sid}/messages",
        data={"input_id": "degraded-1", "expected_version": (await conversation.snapshot())["version"], "text": "yes"},
    )
    events = conversation.check(response)
    assert note in said(events)
    assert len(model.calls) == 1
