"""票 23：三种 409（stale_version / stale_card / not_allowed_now）附快照；error.retry_with_same_action 与
同一 action_id 重试的服务端语义；快照 pending_input 以 checkpoint 中断为准。"""

from tests.message_form import action_body, message_form

import asyncio
import uuid
import pytest

from haike_contracts.actions import ActionConflict
from haike_contracts.snapshot import SessionSnapshot
from httpx import ASGITransport, AsyncClient
from langgraph.checkpoint.memory import InMemorySaver

from app.main import app
from app.sessions import graph as graph_mod
from app.sessions import sse
from app.sessions.manager import RunManager

MULTI = "我的 S1 Pro 不吸了"


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _to_pending(client):
    sid = (await client.post("/sessions")).json()["session_id"]
    events = sse.parse((await client.post(f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": MULTI}))).text)
    return sid, next(e for e in events if e["type"] == "awaiting_input")


def _action(pending, sku="EUFY-S1-PRO", **over):
    return {
        "action_id": uuid.uuid4().hex,
        "input_token": pending["input_token"],
        "card_id": pending["card_id"],
        "expected_version": pending["version"],
        "kind": "select_product",
        "payload": {"sku": sku},
        **over,
    }


def _conflict(resp) -> ActionConflict:
    assert resp.status_code == 409, resp.text
    body = ActionConflict.model_validate(resp.json())
    SessionSnapshot.model_validate(body.snapshot)  # 快照完整可解析
    return body


async def test_three_conflict_codes_each_with_snapshot(mem_runtime):
    async with _client() as client:
        sid, pending = await _to_pending(client)
        # 1. expected_version 不符 → stale_version（先于 card / kind 校验）
        c = _conflict(
            await client.post(
                f"/sessions/{sid}/actions",
                json=await action_body(client, f"/sessions/{sid}/actions", _action(pending, expected_version=pending["version"] + 1, card_id="stale")),
            )
        )
        assert c.code == "stale_version"
        # 2. input_token / card_id 过期 → stale_card
        c = _conflict(
            await client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", _action(pending, input_token="old")))
        )
        assert c.code == "stale_card"
        # 3. kind 不在允许时机 → not_allowed_now（等待 select_product 时发 skip_receipt）
        c = _conflict(
            await client.post(
                f"/sessions/{sid}/actions",
                json=await action_body(client, f"/sessions/{sid}/actions", {**_action(pending), "kind": "skip_receipt", "payload": {"reason": "later"}}),
            )
        )
        assert c.code == "not_allowed_now"
        # 快照可直接用于重建：version 与 pending 与 awaiting_input 一致，卡片只有一张
        snap = SessionSnapshot.model_validate(c.snapshot)
        assert snap.version == pending["version"]
        assert snap.pending_input.card_id == pending["card_id"]
        assert [i.kind for i in snap.timeline if i.kind == "product_card"] == ["product_card"]
        # 三次 409 都没有改变状态：正确动作仍然通过
        ok = await client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", _action(pending)))
        assert ok.status_code == 200 and sse.parse(ok.text)[-1]["reason"] == "awaiting_input"


@pytest.mark.parametrize("terminal", ["error", "cancelled"])
async def test_terminal_input_replays_without_reexecution_and_new_id_can_continue(mem_runtime, monkeypatch, terminal):
    real_apply = graph_mod.apply_action
    started = asyncio.Event()
    calls = 0
    async def interrupted_apply(state):
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            if terminal == "cancelled":
                await asyncio.sleep(10)
            raise RuntimeError("transient failure")
        return await real_apply(state)
    monkeypatch.setattr(graph_mod, "apply_action", interrupted_apply)
    app.state.session_graph = graph_mod.build_graph(InMemorySaver())
    app.state.run_manager = manager = RunManager(mem_runtime, app.state.session_graph)
    async with _client() as client:
        sid, pending = await _to_pending(client)
        body = await action_body(client, f"/sessions/{sid}/actions", _action(pending))
        request = asyncio.create_task(client.post(f"/sessions/{sid}/actions", json=body))
        await asyncio.wait_for(started.wait(), 2)
        if terminal == "cancelled":
            receipt = await mem_runtime.get_input(sid, body["action_id"])
            await manager.cancel(sid, receipt["run_id"])
        first = await request
        events = sse.parse(first.text)
        assert events[-1]["reason"] == terminal
        if terminal == "error":
            error = next(e for e in events if e["type"] == "error")
            assert error["code"] == "node_failed" and not error["retry_with_same_action"]
        snapshot = (await client.get(f"/sessions/{sid}")).json()
        assert snapshot["version"] == pending["version"] and snapshot["active_run"] is None
        assert snapshot["pending_input"]["card_id"] == pending["card_id"]
        receipt = await mem_runtime.get_input(sid, body["action_id"])
        assert receipt["status"] == ("failed" if terminal == "error" else "cancelled")
        assert receipt["state_commit_version"] is None
        replay = await client.post(f"/sessions/{sid}/actions", json=body)
        assert replay.headers["x-input-replayed"] == "true" and sse.parse(replay.text) == events
        assert calls == 1
        next_input = await client.post(f"/sessions/{sid}/actions", json={**body, "action_id": uuid.uuid4().hex})
        assert next_input.status_code == 200 and sse.parse(next_input.text)[-1]["reason"] == "awaiting_input"
        final = (await client.get(f"/sessions/{sid}")).json()
        assert final["version"] == pending["version"] + 1
        assert final["pending_input"]["kind"] == "step_feedback"
        assert next(i for i in final["timeline"] if i["kind"] == "product_card")["selected_sku"] == "EUFY-S1-PRO"
        assert calls == 2


async def test_stale_version_when_pending_consumed_and_snapshot_shows_result(mem_runtime):
    """前端用旧 version 重发：409 stale_version，快照里卡片已带 selected_sku，pending 为空 → 前端据此重建。"""
    async with _client() as client:
        sid, pending = await _to_pending(client)
        first = await client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", _action(pending)))
        assert first.status_code == 200
        c = _conflict(await client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", _action(pending))))
    assert c.code == "stale_version"
    snap = SessionSnapshot.model_validate(c.snapshot)
    # 产品卡已消费；当前 pending 是随后 guide 发出的步骤卡（票 34）
    assert snap.pending_input.kind == "step_feedback" and snap.pending_input.card_id != pending["card_id"]
    assert snap.version == sse.parse(first.text)[-1]["version"]
    card = next(i for i in snap.timeline if i.kind == "product_card")
    assert card.selected_sku == "EUFY-S1-PRO"
