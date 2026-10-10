"""R4 安全主张的语义门（2026-10-10 第 1 项）。

T23 第十轮：设备推送「E41: Battery abnormal, task ended」被模型标为 reported，原话确实在文本里，
reduce 就直接建 R4、禁止操作、入人工。词表预检并没有命中。
修法与 R3 同一模式：来源 + 词表。
- 引文在设备推送 / 描述字段里且词表未命中 → 不是用户报告的危险，不建风险；
- 引文是用户自己写的但词表未命中 → 模型的语义判断单独不足以升级：先问一句封闭式安全确认，期间暂停动作；
- 词表命中（无论模型怎么说）→ 立即 R4，保护不降。
"""

from __future__ import annotations

from app.conversation.interpret import TurnInterpretation
from app.conversation.reduce import SAFETY_CONFIRM_QUESTION, reduce_turn
from app.rules import RulesService
from app.settings import REPO_ROOT
from tests.conversation_runtime import conversation as conversation_fixture
from tests.test_conversation_l3 import l3_runtime as l3_runtime  # noqa: PLC0414

conversation = conversation_fixture

RULES = RulesService(REPO_ROOT / "config/rules/safety_terms.yaml", hot_reload=False)

T23 = (
    "Product Name: S1 Pro\nProduct PN: T2080A\nProduct SN: AK7RCN1E15600379\nProblem Type: ERROR\n"
    "Problem Code: 20972545-\n"
    "Problem Push: E41: Battery abnormal, task ended. Please try restarting or contact customer service for assistance.\n"
    "Problem Description: E41: Battery abnormal, task ended. Please try restarting or contact customer service for assistance.\n"
    "Problem Upload Images: []"
)


def turn(state, iid, text, **meaning):
    state = {
        **state, "session_id": "s", "input_id": iid, "input_seq": int(iid[1:]) * 10,
        "at": "2026-10-10T01:00:00Z", "text": text, "entry": "message",
    }
    precheck = any(h.rule_id == "R4" for h in RULES.check_in(text=text).hits)
    return {**state, **reduce_turn(state, TurnInterpretation(**meaning), precheck_risk=precheck)}


def test_device_push_error_code_is_not_a_safety_claim():
    state = turn(
        {}, "i1", T23, primary_intent="report_problem", device_relation="current",
        facts=[{"value": "Battery abnormal", "quote": "E41: Battery abnormal, task ended."}],
        device_safety_assertion="reported", device_safety_quote="E41: Battery abnormal, task ended.",
    )
    assert state["risk_cases"] == []
    assert state["turn_decision"]["allowed_operations"]
    assert state["turn_decision"]["escalation_trigger"] is None
    assert state["turn_decision"]["clarification"] is None
    assert state["symptoms"] == ["Battery abnormal"]


def test_user_statement_without_lexicon_support_asks_before_escalating():
    state = turn(
        {}, "i1", "My pump shows battery abnormal and the battery is bulging a bit",
        primary_intent="report_problem", device_relation="current",
        facts=[{"value": "battery is bulging", "quote": "the battery is bulging"}],
        device_safety_assertion="reported", device_safety_quote="the battery is bulging",
    )
    assert [r["status"] for r in state["risk_cases"]] == ["unconfirmed"]
    assert not state["turn_decision"]["allowed_operations"]
    assert state["turn_decision"]["escalation_trigger"] is None
    assert state["turn_decision"]["clarification"] == SAFETY_CONFIRM_QUESTION
    assert state["turn_decision"]["reply_mode"] == "clarify"
    # 确认 → 升级
    confirmed = turn(
        state, "i2", "Yes, it is swollen and warm", primary_intent="supplement", device_relation="current",
        device_safety_assertion="reported", device_safety_quote="it is swollen and warm",
    )
    assert [r["status"] for r in confirmed["risk_cases"]] == ["reported"]
    assert confirmed["turn_decision"]["escalation_trigger"] == "R4"
    assert not confirmed["turn_decision"]["allowed_operations"]


def test_user_denies_unconfirmed_claim_and_operations_resume():
    state = turn(
        {}, "i1", "My pump shows battery abnormal and the battery is bulging a bit",
        primary_intent="report_problem", device_relation="current",
        device_safety_assertion="reported", device_safety_quote="the battery is bulging",
    )
    denied = turn(
        state, "i2", "No, nothing like that, it is just the error code", primary_intent="supplement",
        device_relation="current", device_safety_assertion="negated", device_safety_quote="No, nothing like that",
    )
    assert [r["status"] for r in denied["risk_cases"]] == ["cleared"]
    assert denied["turn_decision"]["allowed_operations"]
    assert denied["turn_decision"]["escalation_trigger"] is None
    assert denied["turn_decision"]["clarification"] is None


def test_lexicon_hit_in_user_statement_still_escalates_at_once():
    state = turn(
        {}, "i1", "My X10 Pro Omni is smoking", primary_intent="report_problem", device_relation="current",
        facts=[{"value": "smoking", "quote": "is smoking"}],
        device_safety_assertion="reported", device_safety_quote="is smoking",
    )
    assert [r["status"] for r in state["risk_cases"]] == ["reported"]
    assert state["turn_decision"]["escalation_trigger"] == "R4"


def test_lexicon_hit_in_device_push_keeps_the_floor_even_if_model_says_none():
    push = T23.replace("Battery abnormal", "Battery overheating")
    state = turn(
        {}, "i1", push, primary_intent="report_problem", device_relation="current",
        device_safety_assertion="none",
    )
    assert [r["status"] for r in state["risk_cases"]] == ["reported"]
    assert state["turn_decision"]["escalation_trigger"] == "R4"


def test_confirmed_risk_is_disputed_not_cleared_on_later_denial():
    state = turn(
        {}, "i1", "My X10 Pro Omni is smoking", primary_intent="report_problem", device_relation="current",
        device_safety_assertion="reported", device_safety_quote="is smoking",
    )
    denied = turn(
        state, "i2", "No smoke at all, I was wrong", primary_intent="correct", device_relation="current",
        device_safety_assertion="negated", device_safety_quote="No smoke at all",
    )
    assert [r["status"] for r in denied["risk_cases"]] == ["disputed"]
    assert not denied["turn_decision"]["allowed_operations"]


async def test_http_unconfirmed_claim_asks_then_escalates_on_yes(conversation, l3_runtime):
    text = "My pump shows battery abnormal and the battery is bulging a bit"
    events = await conversation.send(text, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["S1 Pro"],
        "facts": [{"value": "battery is bulging", "quote": "the battery is bulging"}],
        "device_safety_assertion": "reported", "device_safety_quote": "the battery is bulging",
    })
    said = "".join(e["delta"] for e in events if e["type"] == "message")
    assert SAFETY_CONFIRM_QUESTION in said
    assert not [e for e in events if e["type"] == "step_card"]
    state = await conversation.state()
    assert state["stage"] != "awaiting_human" and not state.get("case_id")
    events = await conversation.send("Yes it is swollen", {
        "primary_intent": "supplement", "device_relation": "current",
        "device_safety_assertion": "reported", "device_safety_quote": "it is swollen",
    })
    state = await conversation.state()
    assert state["stage"] == "awaiting_human" and state["escalate_reason"] == "R4"
    assert "stop using the device" in "".join(e["delta"] for e in events if e["type"] == "message")
