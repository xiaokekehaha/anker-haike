"""票 24：product_state 三分、澄清（product / symptom / conflict）与追问上限 R7。

默认 HAIKE_LLM=off：intake 抽取降级（symptoms 为空 → 回退原文判断），追问用固定文案；
需要模型输出的用例用 tests.test_intake.fake_router 注入假 ModelRouter。
"""

from __future__ import annotations

import json

from haike_contracts.snapshot import SessionSnapshot
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.fake import FakeChatModel
from app.models.runtime import set_model_router
from app.sessions import sse
from app.sessions.clarify import (
    FIXED_QUESTIONS,
    MAX_CLARIFICATIONS,
    fixed_question,
    make_question,
)
from tests.message_form import action_body, message_form, model_task_text
from tests.test_intake import fake_router


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _send(client, sid: str, text: str) -> list[dict]:
    resp = await client.post(f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": text}))
    assert resp.status_code == 200, resp.text
    return sse.parse(resp.text)


def _stages(events):
    return [e["stage"] for e in events if e["type"] == "progress"]


def _message_text(events) -> str:
    return "".join(e["delta"] for e in events if e["type"] == "message")


async def _state(sid: str) -> dict:
    return (await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})).values


async def test_unknown_category_two_clarifications_then_r7(mem_runtime):
    """「机器不吸了」→ 追问 → 回答仍不明 → 第二次追问 → 第二次回答仍不明 → R7 升级摘要（验收项 1、6）。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        ev1 = await _send(client, sid, "机器不吸了")
        assert _stages(ev1) == ["intake", "disambiguate"]  # 不进入 diagnose、不检索、不发卡
        assert any(e["type"] == "input_received" for e in ev1)
        assert [e["type"] for e in ev1 if e["type"] not in {"progress", "input_received", "issue_changed"}] == [
            "run_started",
            "message_start",
            "message",
            "message_end",
            "done",
        ]
        assert _message_text(ev1) == FIXED_QUESTIONS["product"]
        assert ev1[-1]["reason"] == "completed"  # 只结束本 run，会话未 solved
        s1 = await _state(sid)
        assert s1["product_state"] == "unknown" and s1["pending_card"] is None
        assert s1["clarification"] == {
            "reason": "product",
            "attempts": 1,
            "asked_run_id": ev1[0]["run_id"],
        }
        # 仅等待用户，不升级：快照 idle、无 pending
        snap = SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())
        assert snap.active_run is None and snap.pending_input is None
        assert [i.kind for i in snap.timeline] == ["user_message", "assistant_message"]

        ev2 = await _send(client, sid, "就是那个机器啊")  # 第一次回答仍不明 → 第二次追问
        assert _message_text(ev2) == FIXED_QUESTIONS["product"]
        s2 = await _state(sid)
        assert s2["clarification"]["attempts"] == 2  # 跨 run 保留并累加
        assert "escalation_summary" not in [e["type"] for e in ev2]

        ev3 = await _send(client, sid, "不知道啊")  # 第二次回答仍不明 → R7
        types = [e["type"] for e in ev3]
        assert "escalation_summary" in types and _stages(ev3)[-1] == "escalate"
        summary = next(e for e in ev3 if e["type"] == "escalation_summary")["summary"]
    assert summary["reason"]["rule_id"] == "R7"
    assert summary["product"] == "未确认"  # product_state=unknown 出现在摘要
    assert any("R7" in o and "2 次澄清" in o for o in summary["observations"])
    s3 = await _state(sid)
    assert s3["escalate_reason"] == "R7" and s3["product_state"] == "unknown"
    assert s3["clarification"]["attempts"] == MAX_CLARIFICATIONS


async def test_category_word_without_model_goes_category_only(mem_runtime):
    """「扫地机不吸了，不知道型号」→ category_only → 进入 diagnose（验收项 2、7）。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events = await _send(client, sid, "扫地机不吸了，不知道型号")
    types = [e["type"] for e in events]
    assert "product_card" not in types and "message_start" not in types  # 不追问、不出卡
    assert _stages(events)[:3] == ["intake", "disambiguate", "diagnose"]
    state = await _state(sid)
    assert state["product_state"] == "category_only" and state["category"] == "robot_vacuum"
    assert state["product_confirmed"] is None and state["clarification"] is None
    assert events[-1]["reason"] == "awaiting_input"  # 票 34：品类通用计划的步骤卡


async def test_three_product_states_written_and_in_summary(mem_runtime):
    async with _client() as client:
        # confirmed_sku：单命中直接确认
        a = (await client.post("/sessions")).json()["session_id"]
        await _send(client, a, "扫地机 X10 不吸了")
        sa = await _state(a)
        assert sa["product_state"] == "confirmed_sku" and sa["product_confirmed"]["sku"] == (
            "EUFY-X10-PRO-OMNI"
        )
        # category_only
        b = (await client.post("/sessions")).json()["session_id"]
        await _send(client, b, "扫地机器人不回充")
        assert (await _state(b))["product_state"] == "category_only"
        # unknown → 两次追问后 R7，摘要 product 带线索为空 → 「未确认」
        c = (await client.post("/sessions")).json()["session_id"]
        await _send(client, c, "它坏了")
        await _send(client, c, "就是坏了")
        ev = await _send(client, c, "不清楚")
        summary = next(e for e in ev if e["type"] == "escalation_summary")["summary"]
    assert (await _state(c))["product_state"] == "unknown"
    assert summary["product"] == "未确认" and summary["reason"]["rule_id"] == "R7"


async def test_clarify_text_from_model_task_and_fixed_fallback(mem_runtime, tmp_path):
    """追问文案由 disambiguate.clarify 生成；失败用固定文案（验收项 4）。"""
    intake_out = {
        "emotion_level": "calm",
        "product_hints": [],
        "symptoms": ["不吸了"],
        "wants_human": False,
    }
    router, fake = fake_router(tmp_path, [intake_out, {"question": "请问是哪一款设备不吸了？"}])
    set_model_router(router)
    try:
        async with _client() as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            events = await _send(client, sid, "机器不吸了")
        assert _message_text(events) == "请问是哪一款设备不吸了？"
        call = fake.calls[-1]
        assert call["metadata"]["task"] == "disambiguate.clarify" and "internal" in call["tags"]
        assert '本轮原话' in model_task_text(call)
        state = await _state(sid)
        assert any(t["task"] == "disambiguate.clarify" for t in state["model_trace"])
    finally:
        set_model_router(None)

    # 模型失败 → 固定文案
    router2, _ = fake_router(tmp_path, [RuntimeError("boom")] * 6)
    out = await make_question(
        router2,
        "symptom",
        "这个又不行了",
        strategy="normal",
        summary=None,
        detail={},
        session_id="s",
        lane="domestic",
    )
    assert out.text == "设备按电源后能正常启动吗？" and out.model_used == "fixed"
    assert fixed_question("conflict", {"confirmed": "A", "mentioned": "B"}) == (
        "您之前确认的是 A，这次提到的是 B，请问需要排查的是哪一台？"
    )


async def test_deictic_without_context_asks_but_with_context_continues(mem_runtime):
    """「这个又不行了」无上下文 → 问一个具体问题；明确上文（已确认产品与故障）→ 承接，不再追问（验收项 5）。"""
    async with _client() as client:
        a = (await client.post("/sessions")).json()["session_id"]
        ev = await _send(client, a, "这个又不行了")
        assert _message_text(ev) == FIXED_QUESTIONS["product"]
        assert (await _state(a))["clarification"]["reason"] == "product"

        b = (await client.post("/sessions")).json()["session_id"]
        await _send(client, b, "扫地机 X9 吸力变小了")
        ev2 = await _send(client, b, "这个又不行了")
    assert "message_start" not in [e["type"] for e in ev2] or _message_text(ev2) not in (
        FIXED_QUESTIONS.values()
    )
    assert "diagnose" in _stages(ev2)
    sb = await _state(b)
    assert sb["product_confirmed"]["sku"] == "EUFY-X9-PRO" and sb["clarification"] is None


async def test_symptom_clarification_when_product_known_but_no_symptom(mem_runtime, tmp_path):
    """品类 / 产品已知但症状不明 → symptom 澄清；补充症状后继续并清零（验收项 7、6）。"""
    router, _ = fake_router(
        tmp_path,
        [
            {
                "emotion_level": "calm",
                "product_hints": ["X10"],
                "symptoms": [],
                "wants_human": False,
            },
            {"question": "请问 X10 是吸力变弱、无法启动，还是有异响？"},
        ],
    )
    set_model_router(router)
    try:
        async with _client() as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            ev1 = await _send(client, sid, "X10 这个又不行了")
            # The model's different question cannot change the stored yes/no split.
            assert _message_text(ev1) == "设备按电源后能正常启动吗？"
            s1 = await _state(sid)
            assert s1["product_state"] == "confirmed_sku"  # 产品已定，只问症状
            assert s1["clarification"] == {
                "reason": "symptom",
                "attempts": 1,
                "asked_run_id": ev1[0]["run_id"],
            }
            set_model_router(None)  # 第二轮不再需要模型
            ev2 = await _send(client, sid, "吸力变弱了")
        assert "diagnose" in _stages(ev2)
        s2 = await _state(sid)
        assert s2["clarification"] is None and s2["product_confirmed"]["sku"] == "EUFY-X10-PRO-OMNI"
    finally:
        set_model_router(None)


async def test_uncertain_text_preserves_product_card_until_valid_selection(mem_runtime, monkeypatch):
    """A conversational detour cannot consume a product choice or fabricate failed actions."""
    import app.conversation.interpret as semantic

    original = semantic.interpret_turn

    async def uncertain_turn(router, state, **kwargs):
        if state.get("entry") == "message" and state.get("active_issue_id"):
            return semantic.TurnInterpretation(
                primary_intent="unknown", clarification="请查看设备标签，确认设备品类。"
            ), {"source": "uncertain-input-fixture"}
        return await original(router, state, **kwargs)

    monkeypatch.setattr(semantic, "interpret_turn", uncertain_turn)
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        first = await _send(client, sid, "我的 S1 Pro 不吸了")
        pending = next(e for e in first if e["type"] == "awaiting_input")
        before = await _state(sid)
        for text in ("不知道是哪个", "还是不知道"):
            events = await _send(client, sid, text)
            snap = SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())
            assert snap.pending_input.card_id == pending["card_id"]
            assert snap.pending_input.input_token == pending["input_token"]
            assert not any(e["type"] == "escalation_summary" for e in events)
            state = await _state(sid)
            assert state["clarification"]["attempts"] == before["clarification"]["attempts"]
        response = await client.post(
            f"/sessions/{sid}/actions",
            json=await action_body(client, f"/sessions/{sid}/actions", {
                "action_id": "selected-after-detour",
                "input_token": pending["input_token"],
                "card_id": pending["card_id"],
                "expected_version": snap.version,
                "kind": "select_product",
                "payload": {"sku": "EUFY-S1-PRO"},
            }),
        )
        assert response.status_code == 200
        assert (await _state(sid))["product_confirmed"]["sku"] == "EUFY-S1-PRO"


async def test_product_correction_and_category_conflict(mem_runtime):
    """已确认 X10 后：单命中的另一型号 → 型号纠正（旧证据失效）；只提到另一品类 → conflict 澄清。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await _send(client, sid, "扫地机 X10 不吸了")
        ev = await _send(client, sid, "说错了，是 X9 不吸")
        s = await _state(sid)
        assert s["product_confirmed"]["sku"] == "EUFY-X9-PRO" and all(e["source"] == "approved_plan" for e in s["evidence"].values())
        assert "diagnose" in _stages(ev)

        ev2 = await _send(client, sid, "吸奶器也坏了")
    assert _message_text(ev2) == (
        "您之前确认的是 eufy X9 Pro，这次提到的是 吸奶器，请问需要排查的是哪一台？"
    )
    s2 = await _state(sid)
    assert s2["clarification"]["reason"] == "conflict" and s2["product_confirmed"]["sku"] == (
        "EUFY-X9-PRO"
    )


def test_fake_router_helper_shape():
    fake = FakeChatModel(script=[json.dumps({"question": "q"})])
    assert fake.script and fake.calls == []
