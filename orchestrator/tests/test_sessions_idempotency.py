"""票 22：动作幂等与会话锁。"""

from tests.message_form import action_body, message_form

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.sessions import router as router_mod
from app.sessions import sse
from app.sessions.locks import InMemorySessionLock, LockTimeout

MULTI = "我的 S1 Pro 不吸了"


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _to_pending(client):
    sid = (await client.post("/sessions")).json()["session_id"]
    events = sse.parse((await client.post(f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": MULTI}))).text)
    pending = next(e for e in events if e["type"] == "awaiting_input")
    return sid, pending


def _action(pending, sku="EUFY-S1-PRO", action_id=None, **over):
    return {
        "action_id": action_id or uuid.uuid4().hex,
        "input_token": pending["input_token"],
        "card_id": pending["card_id"],
        "expected_version": pending["version"],
        "kind": "select_product",
        "payload": {"sku": sku},
        **over,
    }


async def test_same_action_id_twice_replays_and_advances_once(mem_runtime):
    async with _client() as client:
        sid, pending = await _to_pending(client)
        body = _action(pending)
        r1 = await client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", body))
        r2 = await client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", body))
        snap = (await client.get(f"/sessions/{sid}")).json()
    assert r1.status_code == 200 and r1.headers["x-input-replayed"] == "false"
    assert r2.status_code == 200 and r2.headers["x-input-replayed"] == "true"
    assert r1.headers["x-run-id"] == r2.headers["x-run-id"] == r1.headers["x-run-id"]
    assert sse.parse(r1.text) == sse.parse(r2.text)  # 重放同一事件流
    # 业务状态只推进一次
    runs = {e["run_id"] for e in await mem_runtime.list_events(sid)}
    assert len(runs) == 2  # 首轮消息 + 一次动作
    state = await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})
    assert state.values["prepare_card_calls"] == 1
    assert snap["version"] == sse.parse(r1.text)[-1]["version"]
    # session_actions：回填后的结果
    rec = await mem_runtime.get_input(sid, body["action_id"])
    assert rec["status"] == "completed" and rec["run_id"] == r1.headers["x-run-id"]
    assert rec["state_commit_version"] == snap["version"]


async def test_same_action_id_concurrent_double_click(mem_runtime, monkeypatch):
    """连点两次同时到达：一个执行、一个等锁后重放；只产生一个 run。"""
    monkeypatch.setenv("PLACEHOLDER_NODE_DELAY_S", "0.3")
    async with _client() as client:
        sid, pending = await _to_pending(client)
        body = _action(pending)
        r1, r2 = await asyncio.gather(
            client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", body)),
            client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", body)),
        )
    assert {r1.status_code, r2.status_code} == {200}
    assert sorted([r1.headers["x-input-replayed"], r2.headers["x-input-replayed"]]) == [
        "false",
        "true",
    ]
    assert r1.headers["x-run-id"] == r2.headers["x-run-id"]
    assert sse.parse(r1.text) == sse.parse(r2.text)
    assert len({e["run_id"] for e in await mem_runtime.list_events(sid)}) == 2


async def test_two_different_actions_are_serialized_not_rejected(mem_runtime, monkeypatch):
    """两个不同动作并发：第二个等第一个 run 结束后再校验（拿到 409 not_allowed_now，而不是 run_active）。"""
    monkeypatch.setenv("PLACEHOLDER_NODE_DELAY_S", "0.4")
    async with _client() as client:
        sid, pending = await _to_pending(client)
        a1 = _action(pending, "EUFY-S1-PRO")
        a2 = _action(pending, "EUFY-BP-S1-PRO")
        t1 = asyncio.create_task(client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", a1)))
        await asyncio.sleep(0.05)
        t2 = asyncio.create_task(client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", a2)))
        r1, r2 = await asyncio.gather(t1, t2)
    assert r1.status_code == 200 and sse.parse(r1.text)[-1]["reason"] == "awaiting_input"
    assert r2.status_code == 409
    assert r2.json()["code"] == "run_active"  # 串行后 version 已前进（08 §4 先校 version）
    assert r2.json()["snapshot"]["pending_input"]["kind"] == "select_product"  # 票 34：步骤卡
    state = await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})
    assert state.values["product_confirmed"]["sku"] == "EUFY-S1-PRO"


async def test_placeholder_execute_backfill_three_steps(mem_runtime, monkeypatch):
    monkeypatch.setenv("PLACEHOLDER_NODE_DELAY_S", "0.4")
    async with _client() as client:
        sid, pending = await _to_pending(client)
        body = _action(pending)
        task = asyncio.create_task(client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", body)))
        # 占位：run 进行中时记录已存在且 status=pending、带 run_id
        rec = None
        for _ in range(100):
            await asyncio.sleep(0.01)
            rec = await mem_runtime.get_input(sid, body["action_id"])
            if rec:
                break
        assert rec and rec["status"] == "accepted" and rec["run_id"] and rec["state_commit_version"] is None
        assert (await mem_runtime.get_session(sid)).active_run_id == rec["run_id"]  # 执行中
        resp = await task
        # 回填：等后台任务写完
        for _ in range(100):
            await asyncio.sleep(0.01)
            rec = await mem_runtime.get_input(sid, body["action_id"])
            if rec["status"] == "completed":
                break
    assert rec["status"] == "completed" and rec["state_commit_version"] == sse.parse(resp.text)[-1]["version"]


async def test_lock_timeout_does_not_accept_input(mem_runtime, monkeypatch):
    monkeypatch.setattr(router_mod, "LOCK_TIMEOUT_S", 0.05)
    async with _client() as client:
        sid, pending = await _to_pending(client)
        body = await action_body(client, f"/sessions/{sid}/actions", _action(pending))
        async with app.state.session_lock.hold(sid, timeout_s=1):
            response = await client.post(f"/sessions/{sid}/actions", json=body)
        assert response.status_code == 503 and response.headers["retry-after"] == "2"
        assert response.json()["code"] == "lock_timeout"
        assert await mem_runtime.get_input(sid, body["action_id"]) is None
        accepted = await client.post(f"/sessions/{sid}/actions", json=body)
        assert accepted.status_code == 200


async def test_lock_released_after_409_and_replay(mem_runtime, monkeypatch):
    """409 / 重放分支必须释放锁，否则后续动作会撞上 lock_timeout。"""
    monkeypatch.setattr(router_mod, "LOCK_TIMEOUT_S", 0.3)
    async with _client() as client:
        sid, pending = await _to_pending(client)
        bad = await client.post(
            f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", _action(pending, expected_version=99))
        )
        assert bad.status_code == 409
        body = _action(pending)
        ok = await asyncio.wait_for(client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", body)), 3)
        assert ok.status_code == 200
        replay = await client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", body))
        assert replay.status_code == 200 and replay.headers["x-input-replayed"] == "true"
        after = await client.post(
            f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", _action(pending, "EUFY-BP-S1-PRO"))
        )
    assert after.status_code == 409  # 不是 503 lock_timeout


async def test_replay_of_action_from_finished_run_after_restart(mem_runtime):
    """占位带 run_id：进程重启后同一 action_id 仍能重放该 run 的事件。"""
    async with _client() as client:
        sid, pending = await _to_pending(client)
        body = _action(pending)
        r1 = await client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", body))
        # 模拟新进程：新的 manager（内存里没有 live run），同一 store
        from app.sessions.manager import RunManager

        app.state.run_manager = RunManager(mem_runtime, app.state.session_graph)
        r2 = await client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", body))
    assert r2.status_code == 200 and r2.headers["x-input-replayed"] == "true"
    assert sse.parse(r2.text) == sse.parse(r1.text)


async def test_in_memory_lock_semantics():
    lock = InMemorySessionLock()
    async with lock.hold("s", timeout_s=1):
        with pytest.raises(LockTimeout):
            async with lock.hold("s", timeout_s=0.05):
                pass
        async with lock.hold("other", timeout_s=0.05):  # 不同会话互不影响
            pass
    async with lock.hold("s", timeout_s=0.05):  # 释放后可再获取
        pass
