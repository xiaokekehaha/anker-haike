"""会话 c9e11：无法操作后不自动烧计划；用户要求人工时，摘要保留真实反馈。

2026-10-08 起改用主办方 App 报错格式（S1 Pro T2080 + E3 边刷缠绕 → 官方 Q&A rv-0426）：
PN 直接锁定型号，错误码精确命中官方步骤，不再出型号卡、不依赖外部知识库。
"""

from haike_contracts.common import EscalationSummary

from app.escalation.summary import summary_to_text
from app.knowledge.runtime import set_knowledge_adapter
from app.models.runtime import get_model_router, set_model_router
from tests import conversation_runtime

conversation = conversation_runtime.conversation

APP_REPORT = """Product Name: S1 Pro
Product PN: T2080A
Product SN: 12345678A
Problem Type: ERROR
Problem Code: 21037332-
Problem Push: E3: Side brush tangled, please clean.
Problem Description: E3: Side brush tangled, please clean."""


async def test_skipped_steps_keep_product_and_feedback(
    conversation: conversation_runtime.Conversation,
):
    set_knowledge_adapter(None)
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_rv_0426", "confidence": 0.9, "evidence_ids": ["qa:rv-0426"],
        "applicability": "supported", "supported_symptoms": ["边刷缠绕"],
    }]}]
    rows = await conversation.send(
        APP_REPORT,
        {
            "primary_intent": "report_problem",
            "device_relation": "other",
            "device_category": "robot_vacuum",
            "product_hints": ["S1 Pro"],
            "facts": [{"value": "边刷缠绕", "quote": "Side brush tangled"}],
        },
    )
    # PN 锁定型号：「S1 Pro」虽同名（扫地机 / 吸奶器），也不出产品卡
    assert not any(e["type"] == "product_card" for e in rows)
    card = next(e for e in rows if e["type"] == "step_card")
    assert card["step"]["plan_id"] == "qa_rv_0426" and card["step"]["step_id"] == "s1"
    state = await conversation.state()
    assert state["product_confirmed"]["sku"] == "T2080" and state["product_state"] == "confirmed_sku"
    # 后续使用预写计划，不依赖模型润色或外部知识库。
    router = get_model_router()
    set_model_router(None)
    before = await conversation.snapshot()
    pending = before["pending_input"]
    rows = conversation.check(await conversation.client.post(
        f"/sessions/{conversation.sid}/actions",
        json={
            "action_id": "cannot-s1", "expected_version": before["version"],
            "target_issue_id": before["active_issue_id"], "card_id": pending["card_id"],
            "input_token": pending["input_token"], "kind": "step_feedback", "payload": {"feedback": "cannot_do"},
        },
    ))

    assert not any(e["type"] in {"step_card", "escalation_summary"} for e in rows)
    state = await conversation.state()
    assert not state["steps_executed"] and not state["exhausted_plans"]
    set_model_router(router)
    rows = await conversation.send("我要人工客服", {"primary_intent": "request_human", "human_request_quote": "我要人工客服"})
    event = next(e for e in rows if e["type"] == "escalation_summary")
    summary = EscalationSummary.model_validate(event["summary"])
    assert "S1 Pro" in summary.product and "型号未确认" not in summary.product
    assert [step.feedback for step in summary.steps] == ["cannot_do"]
    assert summary.reason.rule_id == "R3"
    reply = "".join(e.get("delta", "") for e in rows)
    assert "support team" in reply
    copied = summary_to_text(summary)
    assert "（无法操作）" in copied
    assert not any(word in reply + copied for word in ("吸奶器", "已完成", "已试步骤", "已经做过", "cannot_do"))
    assert not any(e["type"] == "product_card" for output in conversation.outputs for e in output)
    snapshot = await conversation.snapshot()
    assert snapshot["stage"] == "escalate"
    assert snapshot["timeline"][-1]["summary"] == event["summary"]
