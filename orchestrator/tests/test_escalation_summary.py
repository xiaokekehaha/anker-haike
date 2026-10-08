"""票 16：安全词 → 安抚 → escalation_summary → done 全链路；summary 形状；模型不可用仍生成。"""

from __future__ import annotations

from haike_contracts.common import EscalationSummary
from haike_contracts.events import parse_event
from httpx import ASGITransport, AsyncClient

from app.escalation.summary import (
    build_summary,
    reassurance_text,
    summary_card_id,
    summary_to_text,
)
from app.main import app
from app.rules import RulesService, set_rules_service
from app.sessions import sse
from app.settings import REPO_ROOT
from tests.message_form import message_form

RULES = REPO_ROOT / "config" / "rules" / "safety_terms.yaml"


def test_build_summary_without_model_and_contract_shape():
    state = {
        "messages": [
            {"role": "user", "text": "扫地机冒烟了"},
            {"role": "user", "text": "现在还有焦味"},
        ],
        "active_issue_id": "i", "issues": {"i": {"facts": [{"kind": "symptom", "value": "扫地机冒烟了", "status": "active"}]}},
        "observations": ["现在还有焦味"],
        "safety_flags": [{"rule_id": "R4", "source": "text", "term": "冒烟", "ts": "t"}],
        "product_state": "category_only",
        "category": "robot_vacuum",
    }
    s = build_summary(state, reason="R4", lane="domestic")
    assert isinstance(s, EscalationSummary)
    assert s.receipt.status == "not_collected"
    assert s.reason.rule_id == "R4" and "冒烟" in s.reason.text
    assert s.product == "扫地机器人（型号未确认）" and s.problem == "扫地机冒烟了"
    assert s.observations == ["现在还有焦味"]
    polish = [t for t in s.model_trace if t.task == "escalate.summary_polish"]
    assert polish and polish[0].model_used == "skipped"
    text = summary_to_text(s)
    for key in ("【产品】", "【问题】", "【观察】", "【排查记录】", "【升级原因】"):
        assert key in text
    assert summary_card_id("s1", "R4") == summary_card_id("s1", "R4") != summary_card_id("s1", "R3")


def test_category_only_product_follows_catalog_category():
    """会话 c9e11（2026-09-17）：非扫地机 category_only 的摘要被写成「扫地机器人（型号未确认）」。"""
    base = {"messages": [{"role": "user", "text": "吸奶器吸力很弱"}], "product_state": "category_only"}
    assert build_summary({**base, "category": "breast_pump"}, reason="R2", lane="domestic").product == "吸奶器（型号未确认）"
    assert build_summary({**base, "category": "security_cam"}, reason="R2", lane="domestic").product == "家庭安防摄像头（型号未确认）"
    # 品类缺失时不猜品类
    assert build_summary(base, reason="R2", lane="domestic").product == "未确认"


def test_no_supported_followup_text_separates_skipped_steps():
    """会话 c9e11：两步反馈都是 cannot_do，结束文案却写「已完成」。"""
    state = {
        "active_issue_id": "i",
        "messages": [{"role": "user", "text": "充电宝充不了电"}],
        "product_state": "category_only",
        "category": "power_bank",
        "steps_executed": [
            {"step_id": "s1", "title": "清理充电宝输出接口", "feedback": "cannot_do"},
            {"step_id": "s2", "title": "更换数据线和被充设备测试", "feedback": "cannot_do"},
        ],
        "next_action": {"kind": "handoff_offer", "reason": "no_supported_followup", "compat_rule": "R2", "issue_id": "i"},
    }
    text = build_summary(state, reason="R2", lane="domestic").reason.text
    assert text.startswith("无法操作「清理充电宝输出接口」、「更换数据线和被充设备测试」，现有资料没有进一步")
    assert "已完成" not in text
    reply = reassurance_text("R2", state)
    assert "steps you tried" in reply
    assert not any(word in reply for word in ("已完成", "已试步骤", "已经做过"))
    copied = summary_to_text(build_summary(state, reason="R2", lane="domestic"))
    assert "【排查记录】清理充电宝输出接口（无法操作）" in copied
    assert "更换数据线和被充设备测试（无法操作）" in copied
    assert "【已执行步骤】" not in copied and "cannot_do" not in copied
    state["steps_executed"][0]["feedback"] = "not_solved"
    text = build_summary(state, reason="R2", lane="domestic").reason.text
    assert text.startswith("已操作但未解决「清理充电宝输出接口」，无法操作「更换数据线和被充设备测试」，")


def test_handoff_without_step_feedback_does_not_claim_attempts():
    state = {
        "next_action": {"kind": "handoff_offer", "reason": "no_supported_followup", "compat_rule": "R2"},
        "steps_executed": [],
    }
    summary = build_summary(state, reason="R2", lane="domestic")
    assert not summary.steps
    assert "尚无已执行的排查记录" in summary.reason.text
    assert "已尝试" not in reassurance_text("R2", state)


def test_build_summary_with_steps_and_product():
    state = {
        "messages": [{"role": "user", "text": "吸力小"}],
        "product_confirmed": {"sku": "EUFY-X9-PRO", "name": "eufy X9 Pro"},
        "plans_ranked": [
            {"plan_id": "rv_suction_hair_wrap", "fault": "滚刷毛发缠绕", "confidence": 0.8}
        ],
        "steps_executed": [{"step_id": "s1", "title": "清理滚刷", "feedback": "not_solved"}],
        "emotion": {"level": "angry", "strategy": "reassure_and_shorten"},
        "model_trace": [
            {
                "task": "intake",
                "model_used": "deepseek/deepseek-chat",
                "lane": "domestic",
                "attempts": 1,
            }
        ],
    }
    s = build_summary(state, reason="R3", lane="domestic")
    assert s.product == "eufy X9 Pro" and s.hypotheses == ["滚刷毛发缠绕"]
    assert s.steps[0].feedback == "not_solved" and s.emotion.level == "angry"
    assert "清理滚刷（已操作，仍有问题）" in summary_to_text(s)
    assert [t.task for t in s.model_trace] == ["intake", "escalate.summary_polish"]


async def test_safety_first_message_full_chain(mem_runtime):
    set_rules_service(RulesService(RULES, hot_reload=False))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            resp = await client.post(
                f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": "eufy X9 Pro 充电时冒烟了！"})
            )
            events = sse.parse(resp.text)
            snap = (await client.get(f"/sessions/{sid}")).json()
    finally:
        set_rules_service(None)
    types = [e["type"] for e in events if e["type"] not in {"input_received", "issue_changed", "summary_updated"}]
    assert types == [
        "run_started",
        "progress",
        "progress",
        "message_start",
        "message",
        "message_end",
        "escalation_summary",
        "done",
    ]
    for e in events:
        parse_event(e)
    assert [e["stage"] for e in events if e["type"] == "progress"] == ["intake", "escalate"]
    msg = next(e for e in events if e["type"] == "message")
    assert "stop using" in msg["delta"]
    summ = next(e for e in events if e["type"] == "escalation_summary")
    s = EscalationSummary.model_validate(summ["summary"])
    assert s.receipt.status == "not_collected" and s.reason.rule_id == "R4"
    assert s.problem == "（尚未记录具体故障现象）"  # 本测试的业务 fixture 不抽取事实；风险候选仍阻止操作
    assert any(
        t.task == "escalate.summary_polish" and t.model_used == "skipped" for t in s.model_trace
    )
    assert events[-1]["reason"] == "completed"
    # 快照 timeline 折叠出安抚消息与摘要卡
    kinds = [i["kind"] for i in snap["timeline"]]
    assert kinds[-2:] == ["assistant_message", "escalation_summary"]
    assert snap["timeline"][-1]["card_id"] == summ["card_id"] and snap["stage"] == "escalate"
