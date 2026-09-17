"""会话 c9e11：品类已知、型号未知、两步无法操作时，摘要与结束回复必须保真。"""

from haike_contracts.common import EscalationSummary

from app.escalation.summary import summary_to_text
from app.knowledge.runtime import set_knowledge_adapter
from app.models.runtime import set_model_router
from tests import conversation_runtime

conversation = conversation_runtime.conversation


async def test_power_bank_skipped_steps_keep_product_and_feedback(
    conversation: conversation_runtime.Conversation,
):
    set_knowledge_adapter(None)
    first = await conversation.send(
        "我的移动电源出问题了：",
        {
            "primary_intent": "report_problem",
            "device_relation": "other",
            "device_category": "power_bank",
            "product_hints": ["移动电源"],
            "facts": [{"value": "出问题了", "quote": "出问题了"}],
        },
    )
    assert "充电宝有输出反应吗" in "".join(e.get("delta", "") for e in first)
    # 后续使用既有问答解析与预写计划，不依赖模型润色或外部知识库。
    set_model_router(None)
    before = await conversation.snapshot()
    response = await conversation.client.post(
        f"/sessions/{conversation.sid}/messages",
        data={"input_id": "no-output", "expected_version": before["version"], "text": "没有"},
    )
    rows = conversation.check(response)
    for step_id in ("s1", "s2"):
        card = next(e for e in rows if e["type"] == "step_card")
        assert card["step"]["plan_id"] == "pb_port_debris"
        assert card["step"]["step_id"] == step_id
        state = await conversation.state()
        assert state["category"] == "power_bank" and state["product_state"] == "category_only"
        before = await conversation.snapshot()
        pending = before["pending_input"]
        response = await conversation.client.post(
            f"/sessions/{conversation.sid}/actions",
            json={
                "action_id": f"cannot-{step_id}",
                "expected_version": before["version"],
                "target_issue_id": before["active_issue_id"],
                "card_id": pending["card_id"],
                "input_token": pending["input_token"],
                "kind": "step_feedback",
                "payload": {"feedback": "cannot_do"},
            },
        )
        rows = conversation.check(response)

    event = next(e for e in rows if e["type"] == "escalation_summary")
    summary = EscalationSummary.model_validate(event["summary"])
    assert summary.product == "移动电源（型号未确认）"
    assert [step.feedback for step in summary.steps] == ["cannot_do", "cannot_do"]
    assert summary.reason.rule_id == "R2" and summary.reason.cause == "no_supported_followup"
    assert summary.reason.text.startswith("无法操作「清理充电宝输出接口」、「更换数据线和被充设备测试」")
    assert any("用户回答：没有" in observation for observation in summary.observations)
    reply = "".join(e.get("delta", "") for e in rows)
    assert "排查记录" in reply
    copied = summary_to_text(summary)
    assert "【排查记录】清理充电宝输出接口（无法操作）" in copied
    assert not any(word in reply + copied for word in ("扫地机器人", "已完成", "已试步骤", "已经做过", "cannot_do"))
    assert not any(e["type"] == "product_card" for output in conversation.outputs for e in output)
    snapshot = await conversation.snapshot()
    assert snapshot["stage"] == "escalate"
    assert snapshot["timeline"][-1]["summary"] == event["summary"]
