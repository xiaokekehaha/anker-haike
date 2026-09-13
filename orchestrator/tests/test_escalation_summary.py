"""票 16：安全词 → 安抚 → escalation_summary → done 全链路；summary 形状；模型不可用仍生成。"""

from __future__ import annotations

from tests.message_form import message_form

from haike_contracts.common import EscalationSummary
from haike_contracts.events import parse_event
from httpx import ASGITransport, AsyncClient

from app.escalation.summary import build_summary, summary_card_id, summary_to_text
from app.main import app
from app.rules import RulesService, set_rules_service
from app.sessions import sse
from app.settings import REPO_ROOT

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
    }
    s = build_summary(state, reason="R4", lane="domestic")
    assert isinstance(s, EscalationSummary)
    assert s.receipt.status == "not_collected"
    assert s.reason.rule_id == "R4" and "冒烟" in s.reason.text
    assert s.product.startswith("扫地机器人") and s.problem == "扫地机冒烟了"
    assert s.observations == ["现在还有焦味"]
    polish = [t for t in s.model_trace if t.task == "escalate.summary_polish"]
    assert polish and polish[0].model_used == "skipped"
    text = summary_to_text(s)
    for key in ("【产品】", "【问题】", "【观察】", "【已执行步骤】", "【升级原因】"):
        assert key in text
    assert summary_card_id("s1", "R4") == summary_card_id("s1", "R4") != summary_card_id("s1", "R3")


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
    assert "停止使用" in msg["delta"]
    summ = next(e for e in events if e["type"] == "escalation_summary")
    s = EscalationSummary.model_validate(summ["summary"])
    assert s.receipt.status == "not_collected" and s.reason.rule_id == "R4"
    assert s.problem == "（用户尚未描述问题）"  # 本测试的业务 fixture 不抽取事实；风险候选仍阻止操作
    assert any(
        t.task == "escalate.summary_polish" and t.model_used == "skipped" for t in s.model_trace
    )
    assert events[-1]["reason"] == "completed"
    # 快照 timeline 折叠出安抚消息与摘要卡
    kinds = [i["kind"] for i in snap["timeline"]]
    assert kinds[-2:] == ["assistant_message", "escalation_summary"]
    assert snap["timeline"][-1]["card_id"] == summ["card_id"] and snap["stage"] == "escalate"
