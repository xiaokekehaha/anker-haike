"""信息不足不是知识缺失（2026-10-10 T60）。

真实模型对 T60「This app is shit. I just want my hoover to clean with out all this bullshit」会抽出一条泛化现象
「hoover not cleaning properly」，品类 robot_vacuum、型号未知、情绪 angry。原先：category 检索落空 → 直接 R5 交接；
交接后客户补具体现象只得到对话回复；摘要原因写成「没有可用的排障计划」。
模型与知识库均为假，模拟输出按真实复跑构造。
"""

from __future__ import annotations

import pytest

from app.knowledge.adapter import ToolResult
from app.knowledge.runtime import set_knowledge_adapter
from tests.conversation_runtime import conversation as base_conversation_fixture
from tests.fake_qa import QAHitAdapter
from tests.test_conversation_l3 import l3_runtime as l3_runtime_fixture

base_conversation = base_conversation_fixture
l3_runtime = l3_runtime_fixture

T60 = "This app is shit . I just want my hoover to clean with out all this bullshit"
T60_MEANING = {
    "primary_intent": "report_problem", "secondary_intents": ["complaint"], "device_relation": "current",
    "device_category": "hoover", "emotion_level": "angry", "emotion_cues": ["shit", "bullshit"],
    "diagnostic_request_quote": "I just want my hoover to clean with out all this bullshit",
    "facts": [{"value": "hoover not cleaning properly", "quote": "I just want my hoover to clean with out all this bullshit"}],
}
STOPS = "It stops halfway through cleaning and goes back to the base without finishing the rooms."
STOPS_FACT = {"value": "stops halfway through cleaning and returns to base", "quote": "It stops halfway through cleaning"}


class NoMatch:
    def __init__(self):
        self.calls = []

    async def hybrid_search(self, kb, query, top_k, allow):
        self.calls.append((kb, query, allow))
        return ToolResult("no_match", [], kb=kb, query=query)


@pytest.fixture
async def conversation(l3_runtime, base_conversation):
    yield base_conversation


def said(events):
    return "".join(e.get("delta", "") for e in events if e["type"] == "message")


async def test_t60_unknown_model_no_match_asks_for_the_model_instead_of_handing_off(conversation):
    """型号未知的 category 检索落空是信息不足：先问型号（即使客户发火、型号卡原本可跳过），不转人工。"""
    set_knowledge_adapter(NoMatch())
    events = await conversation.send(T60, T60_MEANING)
    assert not any(e["type"] == "escalation_summary" for e in events)
    card = next((e for e in events if e["type"] == "product_card"), None)
    assert card is not None, said(events)
    assert {c["sku"] for c in card["candidates"]} >= {"T2280", "T2351"}
    state = await conversation.state()
    assert not state.get("escalate_reason") and not state.get("case_id")
    assert "taken so much of your time" not in said(events)


async def test_t60_model_known_but_vague_still_asks_for_the_symptom_then_hands_off_as_insufficient(conversation):
    """型号确定、现象只是泛称时检索仍落空：问一次具体现象；问满仍落空才交接，原因标为信息不足。"""
    set_knowledge_adapter(NoMatch())
    first = await conversation.send(T60.replace("hoover", "Omni C20"), {**T60_MEANING, "product_hints": ["Omni C20"],
                                    "facts": [{"value": "C20 not cleaning properly", "quote": "I just want my Omni C20 to clean"}]})
    assert not any(e["type"] == "escalation_summary" for e in first)
    assert "describe what the device is doing" in said(first)
    second = await conversation.send("it just doesn't work", {"primary_intent": "answer_pending", "device_relation": "current"})
    assert not any(e["type"] == "escalation_summary" for e in second)
    third = await conversation.send("I told you, it doesn't work", {"primary_intent": "answer_pending", "device_relation": "current"})
    summary = next(e for e in third if e["type"] == "escalation_summary")["summary"]
    assert summary["reason"]["rule_id"] == "R5"
    assert summary["reason"]["cause"] == "insufficient_information"
    assert "symptoms" in summary["business"]["missing"]


async def test_model_known_and_concrete_symptom_no_match_is_a_knowledge_gap(conversation):
    """型号确定、现象具体仍落空：真正的知识缺失，直接交接，原因写明资料没有覆盖。"""
    set_knowledge_adapter(NoMatch())
    events = await conversation.send("My Omni C20 keeps spinning in circles and never docks", {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["Omni C20"],
        "facts": [{"value": "spins in circles and never docks", "quote": "keeps spinning in circles and never docks"}],
    })
    summary = next(e for e in events if e["type"] == "escalation_summary")["summary"]
    assert summary["reason"]["cause"] == "knowledge_gap"
    assert "symptoms" not in summary["business"]["missing"]
    assert summary["problem"] == "spins in circles and never docks"


async def test_summary_problem_uses_the_customer_words_not_the_model_paraphrase(conversation):
    """问满交接时，摘要问题栏用客户原话，模型改写的泛化现象只进观察记录。"""
    set_knowledge_adapter(NoMatch())
    meaning = {**T60_MEANING, "product_hints": ["Omni C20"],
               "facts": [{"value": "C20 not cleaning properly", "quote": "I just want my Omni C20 to clean"}]}
    await conversation.send(T60.replace("hoover", "Omni C20"), meaning)
    await conversation.send("no idea", {"primary_intent": "answer_pending", "device_relation": "current"})
    events = await conversation.send("whatever", {"primary_intent": "answer_pending", "device_relation": "current"})
    summary = next(e for e in events if e["type"] == "escalation_summary")["summary"]
    assert "I just want my Omni C20 to clean" in summary["problem"]


async def _handed_off(conversation):
    """型号确定、现象具体仍落空 → 以知识缺失交人工，案件进入等待审核。"""
    set_knowledge_adapter(NoMatch())
    events = await conversation.send("My Omni C20 keeps spinning in circles and never docks", {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["Omni C20"],
        "facts": [{"value": "spins in circles and never docks", "quote": "keeps spinning in circles and never docks"}],
    })
    assert any(e["type"] == "escalation_summary" for e in events)
    state = await conversation.state()
    assert state["stage"] == "awaiting_human" and state["case_status"] == "awaiting_approval"
    return state


async def test_new_symptom_after_no_match_handoff_retries_troubleshooting(conversation):
    """转人工后客户补了新的具体现象：重新检索；命中则案件撤回排障、发步骤卡（方案 A）。"""
    await _handed_off(conversation)
    set_knowledge_adapter(QAHitAdapter("rv-0536"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_rv_0536", "confidence": 0.9, "evidence_ids": ["chunk-rv-0536"],
        "applicability": "supported", "supported_symptoms": [STOPS_FACT["value"]],
    }]}]
    events = await conversation.send(STOPS, {"primary_intent": "report_problem", "device_relation": "current", "facts": [STOPS_FACT]})
    assert any(e["type"] == "step_card" for e in events), said(events)
    state = await conversation.state()
    assert state["stage"] == "guide" and state["case_status"] == "diagnosing"
    assert "check the official guidance" not in said(events)


async def test_new_symptom_still_no_match_only_updates_the_ticket(conversation):
    """补了现象仍然查不到：只更新交接记录，回复如实说明已记入工单，不再承诺去查。"""
    await _handed_off(conversation)
    events = await conversation.send(STOPS, {"primary_intent": "report_problem", "device_relation": "current", "facts": [STOPS_FACT]})
    assert not any(e["type"] == "step_card" for e in events)
    text = said(events)
    assert "check the official guidance" not in text
    assert "added" in text.lower()
    state = await conversation.state()
    assert state["case_status"] == "awaiting_approval"


async def test_no_retry_when_the_customer_asked_for_a_human(conversation):
    """客户明确要求人工（R3）后补充信息：不撤回人工队列。"""
    set_knowledge_adapter(NoMatch())
    await conversation.send("My Omni C20 keeps spinning. Transfer me to a human please", {
        "primary_intent": "request_human", "device_relation": "current", "product_hints": ["Omni C20"],
        "human_request_quote": "Transfer me to a human please",
        "facts": [{"value": "keeps spinning", "quote": "keeps spinning"}],
    })
    set_knowledge_adapter(QAHitAdapter("rv-0536"))
    events = await conversation.send(STOPS, {"primary_intent": "report_problem", "device_relation": "current", "facts": [STOPS_FACT]})
    assert not any(e["type"] == "step_card" for e in events)


async def test_wish_copied_verbatim_as_a_symptom_is_not_concrete(conversation):
    """T60 复跑第 3 次：模型把愿望原样抄成现象（值 = 引文），选完型号后检索有命中但没有适用方案。仍是信息不足，先问现象。"""
    set_knowledge_adapter(QAHitAdapter("rv-0536"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_rv_0536", "confidence": 0.4, "evidence_ids": ["chunk-rv-0536"], "applicability": "not_applicable",
        "supported_symptoms": [],
    }]}]
    events = await conversation.send(T60.replace("hoover", "Omni C20"), {**T60_MEANING, "product_hints": ["Omni C20"],
        "facts": [{"value": "Omni C20 to clean with out all this bullshit", "quote": "I just want my Omni C20 to clean with out all this bullshit"}]})
    assert not any(e["type"] == "escalation_summary" for e in events)
    assert "describe what the device is doing" in said(events)


def test_concrete_symptoms_from_real_tickets_are_not_flagged():
    """真实工单里的具体现象不被当成愿望或改写（防误伤）。"""
    from app.diagnose.decision import concrete

    for value, quote in [
        ("spins in circles and never docks", "keeps spinning in circles and never docks"),
        ("motor making abnormal noise", "motor is making abnormal noise"),
        ("Wiel raakt de grond niet", "Probleembeschrijving: Wiel raakt de grond niet."),
        ("charging case will not charge", "My charging case will not charge"),
    ]:
        assert concrete({"value": value, "quote": quote}), value
    assert not concrete({"value": "hoover not cleaning properly", "quote": "I just want my hoover to clean"})


def test_evaluation_without_device_behaviour_is_not_a_symptom():
    """T58「You're fucking cameras suck」被抽成现象 poor quality（subject=cameras），据此选了画质指南。
    引文去掉情绪词（与情绪分级同一份词表）后只剩指代整机的词，就是评价，不是设备在做什么；
    情绪词修饰具体部件或现象时仍是现象。"""
    from app.diagnose.decision import concrete

    for quote, subject in [("cameras suck", "cameras"), ("You’re fucking cameras suck", "cameras"), ("这个机器太烂了", None)]:
        assert not concrete({"value": "poor quality", "quote": quote, "subject": subject}), quote
    for quote in ["the suction is terrible", "camera keeps going offline, so frustrating",
                  "the app is useless, it never connects", "吸力太烂了"]:
        assert concrete({"value": quote, "quote": quote}), quote


async def test_error_code_missing_from_official_qa_is_a_knowledge_gap(conversation):
    """T13：带错误码、官方未收录 —— 型号和现象都明确，摘要原因写知识缺失，而不是笼统的「没有可用计划」。"""
    text = ("Productnaam: X10 Pro Omni\nProduct-PN: T2351\nProbleemtype: WARNING\nProbleemcode: 5116-Communicatiefout.\n"
            "Probleembeschrijving: Er is een communicatiefout tussen de robot en het station.\n")
    events = await conversation.send(text, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
        "facts": [{"value": "communicatiefout robot en station", "quote": "Er is een communicatiefout tussen de robot en het station"}],
    })
    summary = next(e for e in events if e["type"] == "escalation_summary")["summary"]
    assert summary["reason"]["cause"] == "knowledge_gap"
    assert "官方资料没有覆盖" in summary["reason"]["text"]


async def test_t60_wish_only_candidate_is_not_executed_after_the_model_is_chosen(conversation):
    """21:03 续测 T60：补完型号 C20 后，synthesize 把 rv-0527「C20 清洁效果差」判 supported，supported_symptoms 只有那句
    愿望（「I just want my hoover to clean」）→ 发说明后整条结束。愿望句不是可判定的现象：不出方案，先问具体现象。"""
    set_knowledge_adapter(QAHitAdapter("rv-0527"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_rv_0527", "confidence": 0.72, "evidence_ids": ["chunk-rv-0527"],
        "applicability": "supported", "supported_symptoms": ["C20 not cleaning properly"],
    }]}]
    events = await conversation.send(T60.replace("hoover", "Omni C20"), {**T60_MEANING, "product_hints": ["Omni C20"],
                                     "facts": [{"value": "C20 not cleaning properly", "quote": "I just want my Omni C20 to clean"}]})
    assert not any(e["type"] == "step_card" for e in events)
    assert "describe what the device is doing" in said(events)
    state = await conversation.state()
    assert state["stage"] != "done"
    assert any("not_concrete:qa_rv_0527" in str(t.get("dropped")) for t in state["retrieval_trace"] if t.get("event") == "synthesize")


def test_rv_0527_recommendation_is_an_action_not_an_explanation():
    """T60：rv-0527「We recommend cleaning the dust box filter… then starting a new task… so that we can provide…」
    第二句的 can 曾让整段被判成说明，指南走「已解释」直接结束、客户没有反馈入口。"""
    from app.official.qa_index import classify_step, get_qa_index

    assert get_qa_index().guides["rv-0527"].steps[0].kind == "action"
    assert classify_step("The robot can detect carpets automatically.") == "statement"
