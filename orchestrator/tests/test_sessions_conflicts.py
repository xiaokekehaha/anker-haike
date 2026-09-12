"""票 23：三种 409（stale_version / stale_card / not_allowed_now）附快照；error.retry_with_same_action 与
同一 action_id 重试的服务端语义；快照 pending_input 以 checkpoint 中断为准。"""

import asyncio
import uuid

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
    events = sse.parse((await client.post(f"/sessions/{sid}/messages", data={"text": MULTI})).text)
    return sid, next(e for e in events if e["type"] == "awaiting_input")


def _action(pending, sku="EUFY-S1-PRO", **over):
    return {
        "action_id": uuid.uuid4().hex,
        "interrupt_id": pending["interrupt_id"],
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
                json=_action(pending, expected_version=pending["version"] + 1, card_id="stale"),
            )
        )
        assert c.code == "stale_version"
        # 2. interrupt_id / card_id 过期 → stale_card
        c = _conflict(
            await client.post(f"/sessions/{sid}/actions", json=_action(pending, interrupt_id="old"))
        )
        assert c.code == "stale_card"
        # 3. kind 不在允许时机 → not_allowed_now（等待 select_product 时发 skip_receipt）
        c = _conflict(
            await client.post(
                f"/sessions/{sid}/actions",
                json={**_action(pending), "kind": "skip_receipt", "payload": {"reason": "later"}},
            )
        )
        assert c.code == "not_allowed_now"
        # 快照可直接用于重建：version 与 pending 与 awaiting_input 一致，卡片只有一张
        snap = SessionSnapshot.model_validate(c.snapshot)
        assert snap.version == pending["version"]
        assert snap.pending_input.card_id == pending["card_id"]
        assert [i.kind for i in snap.timeline if i.kind == "product_card"] == ["product_card"]
        # 三次 409 都没有改变状态：正确动作仍然通过
        ok = await client.post(f"/sessions/{sid}/actions", json=_action(pending))
        assert ok.status_code == 200 and sse.parse(ok.text)[-1]["reason"] == "awaiting_input"


async def test_failed_action_run_is_retryable_with_same_action_id(mem_runtime, monkeypatch):
    """apply_action 第一次抛错：error.retry_with_same_action=true。此时 await_input 已接收动作并提交
    checkpoint（图停在 apply_action 之前），快照 pending 为空、version 前进；前端原样复用 action_id 重试
    （expected_version 仍是旧值）→ 服务端识别为「继续执行」而非重放，run 完成。"""
    real_apply = graph_mod.apply_action
    calls = {"n": 0}

    async def flaky_apply(state):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient failure")
        return await real_apply(state)

    monkeypatch.setattr(graph_mod, "apply_action", flaky_apply)
    app.state.session_graph = graph_mod.build_graph(InMemorySaver())
    app.state.run_manager = RunManager(mem_runtime, app.state.session_graph)

    async with _client() as client:
        sid, pending = await _to_pending(client)
        body = _action(pending)
        r1 = await client.post(f"/sessions/{sid}/actions", json=body)
        assert r1.status_code == 200 and r1.headers["x-action-replayed"] == "false"
        ev1 = sse.parse(r1.text)
        err = next(e for e in ev1 if e["type"] == "error")
        assert err["code"] == "node_failed" and err["recoverable"] is True
        assert err["retry_with_same_action"] is True
        assert ev1[-1]["reason"] == "error"

        snap = SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())
        assert snap.last_error.code == "node_failed"
        # 动作已被接收但未应用：不再等待用户输入，version 已前进（await_input 的 checkpoint 已提交）
        assert snap.pending_input is None and snap.active_run is None
        assert snap.version > pending["version"]
        state = await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})
        assert state.next == ("apply_action",)
        assert state.values["last_action"]["action_id"] == body["action_id"]
        # 另一个 action_id 此时不被接受（没有 pending）
        other = await client.post(
            f"/sessions/{sid}/actions", json=_action(pending, expected_version=snap.version)
        )
        assert other.status_code == 409 and other.json()["code"] == "not_allowed_now"

        # 占位已撤销：等后台回填任务跑完
        for _ in range(100):
            await asyncio.sleep(0.01)
            if await mem_runtime.get_action(sid, body["action_id"]) is None:
                break
        assert await mem_runtime.get_action(sid, body["action_id"]) is None

        # 原样复用 action_id 重试（旧 expected_version）→ 真正执行（继续 apply_action），不是重放失败流
        r2 = await client.post(f"/sessions/{sid}/actions", json=body)
        assert r2.status_code == 200 and r2.headers["x-action-replayed"] == "false"
        assert r2.headers["x-run-id"] != r1.headers["x-run-id"]
        ev2 = sse.parse(r2.text)
        # 不再重发产品卡的 awaiting_input；随后 guide 出步骤卡（票 34）另有一次 awaiting_input(step_feedback)
        awaiting = [e for e in ev2 if e["type"] == "awaiting_input"]
        assert ev2[0]["resumed"] is True and [a["kind"] for a in awaiting] == ["step_feedback"]
        assert ev2[-1]["reason"] == "awaiting_input"
        final = SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())
    assert calls["n"] == 2
    assert final.pending_input.kind == "step_feedback"  # 票 34：产品确认后停在步骤卡
    cards = [i for i in final.timeline if i.kind == "product_card"]
    assert len(cards) == 1 and cards[0].selected_sku == "EUFY-S1-PRO"
    rec = await mem_runtime.get_action(sid, body["action_id"])
    assert rec["status"] == "done" and rec["run_id"] == r2.headers["x-run-id"]


async def test_cancelled_action_run_releases_action_id(mem_runtime, monkeypatch):
    """动作 run 在 apply_action 中被取消：占位撤销，同一 action_id 重试从 apply_action 继续并完成。"""
    real_apply = graph_mod.apply_action
    calls = {"n": 0}

    async def slow_apply(state):
        calls["n"] += 1
        if calls["n"] == 1:
            await asyncio.sleep(2)
        return await real_apply(state)

    monkeypatch.setattr(graph_mod, "apply_action", slow_apply)
    app.state.session_graph = graph_mod.build_graph(InMemorySaver())
    app.state.run_manager = manager = RunManager(mem_runtime, app.state.session_graph)

    async with _client() as client:
        sid, pending = await _to_pending(client)
        body = _action(pending)
        task = asyncio.create_task(client.post(f"/sessions/{sid}/actions", json=body))
        rec = None
        for _ in range(200):
            await asyncio.sleep(0.01)
            rec = await mem_runtime.get_action(sid, body["action_id"])
            if rec and rec.get("run_id"):
                break
        assert rec is not None
        cancel = await client.post(f"/sessions/{sid}/cancel", json={"run_id": rec["run_id"]})
        assert cancel.status_code == 200
        r1 = await task
        assert sse.parse(r1.text)[-1]["reason"] == "cancelled"
        for _ in range(100):
            await asyncio.sleep(0.01)
            if await mem_runtime.get_action(sid, body["action_id"]) is None:
                break
        assert await mem_runtime.get_action(sid, body["action_id"]) is None
        snap = SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())
        assert snap.cancelled_run.run_id == rec["run_id"] and snap.pending_input is None
        assert not manager.is_live(rec["run_id"])
        # 同一 action_id 重试：锁与占位都已释放，从 apply_action 继续并完成
        r2 = await client.post(f"/sessions/{sid}/actions", json=body)
        assert r2.status_code == 200 and r2.headers["x-action-replayed"] == "false"
        assert sse.parse(r2.text)[-1]["reason"] == "awaiting_input"
        final = SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())
    assert calls["n"] == 2
    assert final.pending_input.kind == "step_feedback"  # 票 34：产品确认后进入步骤卡
    assert next(i for i in final.timeline if i.kind == "product_card").selected_sku == "EUFY-S1-PRO"


async def test_stale_version_when_pending_consumed_and_snapshot_shows_result(mem_runtime):
    """前端用旧 version 重发：409 stale_version，快照里卡片已带 selected_sku，pending 为空 → 前端据此重建。"""
    async with _client() as client:
        sid, pending = await _to_pending(client)
        first = await client.post(f"/sessions/{sid}/actions", json=_action(pending))
        assert first.status_code == 200
        c = _conflict(await client.post(f"/sessions/{sid}/actions", json=_action(pending)))
    assert c.code == "stale_version"
    snap = SessionSnapshot.model_validate(c.snapshot)
    # 产品卡已消费；当前 pending 是随后 guide 发出的步骤卡（票 34）
    assert snap.pending_input.kind == "step_feedback" and snap.pending_input.card_id != pending["card_id"]
    assert snap.version == sse.parse(first.text)[-1]["version"]
    card = next(i for i in snap.timeline if i.kind == "product_card")
    assert card.selected_sku == "EUFY-S1-PRO"
