"""票 25：范围外产品 R8（out_of_scope 子流程）与 request_human 全局动作（08 §4 步骤 4）。"""

from __future__ import annotations

import asyncio
import uuid

from haike_contracts.snapshot import SessionSnapshot
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.sessions import sse
from app.sessions.graph import OUT_OF_SCOPE_TEXT

MULTI = "我的 S1 Pro 不吸了"


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _send(client, sid: str, text: str) -> list[dict]:
    resp = await client.post(f"/sessions/{sid}/messages", data={"text": text})
    assert resp.status_code == 200, resp.text
    return sse.parse(resp.text)


def _human(**over) -> dict:
    return {"action_id": uuid.uuid4().hex, "expected_version": 0, "kind": "request_human", **over}


def _stages(events):
    return [e["stage"] for e in events if e["type"] == "progress"]


def _summary(events) -> dict:
    return next(e for e in events if e["type"] == "escalation_summary")["summary"]


async def _state(sid: str):
    return await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})


async def _snap(client, sid: str) -> SessionSnapshot:
    return SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())


async def test_a2_select_breast_pump_out_of_scope_then_r8(mem_runtime):
    """A2 选吸奶器 → 说明文本 → escalation_summary(reason R8)（验收项 1）。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        pending = next(e for e in await _send(client, sid, MULTI) if e["type"] == "awaiting_input")
        resp = await client.post(
            f"/sessions/{sid}/actions",
            json={
                "action_id": uuid.uuid4().hex,
                "interrupt_id": pending["interrupt_id"],
                "card_id": pending["card_id"],
                "expected_version": pending["version"],
                "kind": "select_product",
                "payload": {"sku": "EUFY-BP-S1-PRO"},
            },
        )
        assert resp.status_code == 200
        events = sse.parse(resp.text)
        snap = await _snap(client, sid)
    assert _stages(events) == ["out_of_scope", "escalate"]
    texts = [
        "".join(e["delta"] for e in events if e["type"] == "message" and e["message_id"] == mid)
        for mid in dict.fromkeys(e["message_id"] for e in events if e["type"] == "message_start")
    ]
    assert texts[0] == OUT_OF_SCOPE_TEXT.format(name="eufy S1 Pro 吸奶器", category="吸奶器")
    summary = _summary(events)
    assert summary["reason"]["rule_id"] == "R8" and summary["product"] == "eufy S1 Pro 吸奶器"
    assert summary["receipt"]["status"] == "not_collected"
    assert events[-1]["reason"] == "completed"
    st = (await _state(sid)).values
    assert st["stage"] == "escalate" and st["out_of_scope"] is True
    assert st["product_state"] == "confirmed_sku" and st["escalate_reason"] == "R8"
    # 快照：卡片带已选结果、说明文本与摘要卡各一张，无 pending
    kinds = [i.kind for i in snap.timeline]
    assert kinds.count("product_card") == 1 and kinds.count("escalation_summary") == 1
    assert next(i for i in snap.timeline if i.kind == "product_card").selected_sku == (
        "EUFY-BP-S1-PRO"
    )
    assert snap.pending_input is None and snap.stage == "escalate"


async def test_out_of_scope_category_without_sku_goes_r8_with_category_product(mem_runtime):
    """只提到范围外品类（充电器）、无具体型号：不追问，直接说明并 R8；摘要产品写品类。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events = await _send(client, sid, "充电器不亮灯")
    assert _stages(events) == ["intake", "disambiguate", "out_of_scope", "escalate"]
    assert "product_card" not in [e["type"] for e in events]
    summary = _summary(events)
    assert summary["reason"]["rule_id"] == "R8" and summary["product"] == "充电器（型号未确认）"
    st = (await _state(sid)).values
    assert st["product_state"] == "category_only" and st["category"] == "charger"


async def test_request_human_while_awaiting_input_is_not_409(mem_runtime):
    """awaiting_input 中点「请求人工」：忽略 version / pending 校验，不返回 409；卡片作废、R3 升级（验收项 3）。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        first = await _send(client, sid, MULTI)
        assert first[-1]["reason"] == "awaiting_input"
        body = _human(expected_version=0)  # 故意给错版本、不带 card_id
        resp = await client.post(f"/sessions/{sid}/actions", json=body)
        assert resp.status_code == 200 and resp.headers["x-action-replayed"] == "false"
        events = sse.parse(resp.text)
        snap = await _snap(client, sid)
        # 同 action_id 重放
        again = await client.post(f"/sessions/{sid}/actions", json=body)
        assert again.status_code == 200 and again.headers["x-action-replayed"] == "true"
    assert events[0]["resumed"] is True  # 经 interrupt 恢复
    assert _stages(events) == ["escalate"] and "awaiting_input" not in [e["type"] for e in events]
    summary = _summary(events)
    assert summary["reason"]["rule_id"] == "R3"
    assert summary["product"].startswith("未确认")  # 卡片未选，产品仍未确认
    st = (await _state(sid)).values
    assert st["escalate_reason"] == "R3" and st["pending_card"] is None
    flag = st["safety_flags"][-1]
    assert (
        flag["rule_id"] == "R3"
        and flag["source"] == "action"
        and flag["action_id"] == (body["action_id"])
    )
    assert snap.pending_input is None and snap.stage == "escalate"
    card = next(i for i in snap.timeline if i.kind == "product_card")
    assert card.selected_sku is None  # 用户没有选


async def test_request_human_during_streaming_cancels_then_escalates(mem_runtime, monkeypatch):
    """streaming 中点「请求人工」→ 当前 run 停止（done cancelled）→ 升级摘要（验收项 2）。"""
    monkeypatch.setenv("PLACEHOLDER_NODE_DELAY_S", "1.5")
    manager = app.state.run_manager
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        running = await manager.start(sid, "扫地机 X10 不吸了")
        for _ in range(200):  # 等 intake 进入 sleep（progress 已落库）
            await asyncio.sleep(0.01)
            if len(await mem_runtime.list_events(sid, run_id=running.run_id)) >= 2:
                break
        monkeypatch.setenv("PLACEHOLDER_NODE_DELAY_S", "0")
        t0 = asyncio.get_event_loop().time()
        resp = await client.post(f"/sessions/{sid}/actions", json=_human())
        elapsed = asyncio.get_event_loop().time() - t0
        assert resp.status_code == 200, resp.text
        events = sse.parse(resp.text)
        prev = await mem_runtime.list_events(sid, run_id=running.run_id)
        snap = await _snap(client, sid)
    assert elapsed < 1.2, "取消应立刻中止正在 sleep 的节点"
    assert prev[-1]["type"] == "done" and prev[-1]["reason"] == "cancelled"
    assert events[0]["resumed"] is False and events[0]["run_id"] != running.run_id
    assert _stages(events) == ["escalate"] and _summary(events)["reason"]["rule_id"] == "R3"
    assert snap.cancelled_run is not None and snap.cancelled_run.run_id == running.run_id
    assert snap.stage == "escalate" and snap.active_run is None


async def test_request_human_when_idle_starts_from_entry(mem_runtime):
    """idle 状态（无 interrupt、无 active run）点「请求人工」：从 START 直达 human_request → escalate。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await _send(client, sid, "扫地机 X10 不吸了")  # 完整一轮，回到 idle
        before = await _snap(client, sid)
        assert before.pending_input is None and before.active_run is None
        resp = await client.post(f"/sessions/{sid}/actions", json=_human(expected_version=999))
        assert resp.status_code == 200
        events = sse.parse(resp.text)
        after = await _snap(client, sid)
    assert events[0]["resumed"] is False
    assert [e["type"] for e in events if e["type"] != "ping"] == [
        "run_started",
        "progress",
        "message_start",
        "message",
        "message_end",
        "escalation_summary",
        "done",
    ]
    summary = _summary(events)
    assert summary["reason"]["rule_id"] == "R3" and summary["product"] == "eufy X10 Pro Omni"
    assert summary["problem"] == "扫地机 X10 不吸了"
    st = (await _state(sid)).values
    assert st["product_confirmed"]["sku"] == "EUFY-X10-PRO-OMNI"  # 已确认信息带进摘要、未被清空
    assert after.version == events[-1]["version"] and after.stage == "escalate"


async def test_request_human_on_fresh_session(mem_runtime):
    """会话刚创建、一句话没说就请求人工：同样可用。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        resp = await client.post(f"/sessions/{sid}/actions", json=_human())
        assert resp.status_code == 200
        events = sse.parse(resp.text)
    summary = _summary(events)
    assert summary["reason"]["rule_id"] == "R3" and summary["problem"] == "（用户尚未描述问题）"
