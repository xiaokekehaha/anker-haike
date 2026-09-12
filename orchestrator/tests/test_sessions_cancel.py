import asyncio
import time

from haike_contracts.snapshot import SessionSnapshot
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.sessions import sse


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _wait_events(store, sid: str, run_id: str, n: int):
    for _ in range(200):
        await asyncio.sleep(0.01)
        evs = await store.list_events(sid, run_id=run_id)
        if len(evs) >= n:
            return evs
    raise AssertionError(f"never saw {n} events")


async def test_cancel_mid_run_stops_at_checkpoint_and_persists(mem_runtime, monkeypatch):
    monkeypatch.setenv("PLACEHOLDER_NODE_DELAY_S", "1.5")
    manager = app.state.run_manager
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        handle = await manager.start(sid, "充不上电")
        # 等 intake 的 progress 落库（intake 节点在 sleep 中）
        await _wait_events(mem_runtime, sid, handle.run_id, 2)
        t0 = time.monotonic()
        resp = await client.post(f"/sessions/{sid}/cancel", json={"run_id": handle.run_id})
        elapsed = time.monotonic() - t0
    assert resp.status_code == 200 and resp.json() == {
        "run_id": handle.run_id,
        "status": "cancelled",
    }
    assert elapsed < 1.0, "取消应立刻中止正在 sleep 的节点，而不是等它跑完"

    events = await mem_runtime.list_events(sid, run_id=handle.run_id)
    assert [e["type"] for e in events] == ["run_started", "progress", "done"]
    assert events[-1]["reason"] == "cancelled"
    # intake 被中止：没有写出 intake 的 checkpoint，只留输入 checkpoint → version 1、stage 仍 intake
    assert events[-1]["version"] == 1
    row = await mem_runtime.get_session(sid)
    assert row.active_run_id is None
    state = await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})
    assert state.values.get("stage") is None and state.values.get("messages", []) == []


async def test_cancel_between_nodes_keeps_completed_checkpoint(mem_runtime, monkeypatch):
    """intake 已完成、reply 进行中时取消：状态停在 intake 之后的 checkpoint（节点边界语义）。"""
    monkeypatch.delenv("PLACEHOLDER_NODE_DELAY_S", raising=False)
    from app.sessions import graph as graph_mod

    real_reply = graph_mod.reply

    async def slow_reply(state):
        await asyncio.sleep(2)
        return await real_reply(state)

    from langgraph.checkpoint.memory import InMemorySaver

    from app.sessions.manager import RunManager

    monkeypatch.setattr(graph_mod, "reply", slow_reply)
    app.state.session_graph = graph_mod.build_graph(InMemorySaver())
    app.state.run_manager = manager = RunManager(mem_runtime, app.state.session_graph)

    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        handle = await manager.start(sid, "第一句")
        await _wait_events(mem_runtime, sid, handle.run_id, 2)  # progress(intake)
        await asyncio.sleep(0.1)  # 让 intake 提交 checkpoint、reply 进入 sleep
        resp = await client.post(f"/sessions/{sid}/cancel", json={"run_id": handle.run_id})
        assert resp.json()["status"] == "cancelled"
        snap = SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())
    assert snap.cancelled_run is not None and snap.cancelled_run.run_id == handle.run_id
    assert snap.active_run is None and snap.pending_input is None
    assert snap.stage == "intake"  # intake 的 checkpoint 保留，reply 未提交
    assert [i.kind for i in snap.timeline] == ["user_message"]  # intake 写入的用户消息保留
    state = await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})
    assert state.values["stage"] == "intake" and state.next == ("reply",)


async def test_cancel_keeps_pending_input_from_before(mem_runtime, monkeypatch):
    """取消后 pending_input 与取消前一致（08 §7）。"""
    monkeypatch.setenv("PLACEHOLDER_NODE_DELAY_S", "1.5")
    store = mem_runtime
    sid = (await store.create_session()).session_id
    # 模拟上一轮以等待输入结束（票 20 前用事件日志构造）
    await store.try_start_run(sid, "prev")
    for ev in [
        {"type": "run_started", "resumed": False, "deadline_ms": 25000},
        {
            "type": "awaiting_input",
            "kind": "select_product",
            "interrupt_id": "c1",
            "card_id": "c1",
            "version": 1,
        },
        {"type": "done", "reason": "awaiting_input", "version": 1},
    ]:
        await store.append_event(sid, "prev", {**ev, "run_id": "prev", "seq": 0})
    await store.finish_run(sid, "prev", version=1)

    manager = app.state.run_manager
    async with _client() as client:
        before = SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())
        assert before.pending_input is not None and before.pending_input.card_id == "c1"
        handle = await manager.start(sid, "补充一句")
        await _wait_events(store, sid, handle.run_id, 2)
        assert (
            await client.post(f"/sessions/{sid}/cancel", json={"run_id": handle.run_id})
        ).status_code == 200
        after = SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())
    assert after.cancelled_run.run_id == handle.run_id
    assert after.pending_input == before.pending_input


async def test_subscriber_receives_done_cancelled_and_stream_closes(mem_runtime, monkeypatch):
    monkeypatch.setenv("PLACEHOLDER_NODE_DELAY_S", "1.5")
    manager = app.state.run_manager
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        handle = await manager.start(sid, "a")
        resume = asyncio.create_task(client.get(f"/sessions/{sid}/runs/{handle.run_id}/events"))
        await _wait_events(mem_runtime, sid, handle.run_id, 2)
        await client.post(f"/sessions/{sid}/cancel", json={"run_id": handle.run_id})
        resp = await asyncio.wait_for(resume, timeout=3)
    events = sse.parse(resp.text)
    assert [e["type"] for e in events] == ["run_started", "progress", "done"]
    assert events[-1]["reason"] == "cancelled"


async def test_cancel_wrong_or_finished_run_409_and_validation(mem_runtime):
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        # 没有 active run
        r = await client.post(f"/sessions/{sid}/cancel", json={"run_id": "nope"})
        assert r.status_code == 409 and r.json()["code"] == "run_not_active"
        SessionSnapshot.model_validate(r.json()["snapshot"])
        # 已结束的 run
        done = sse.parse((await client.post(f"/sessions/{sid}/messages", data={"text": "a"})).text)
        r = await client.post(f"/sessions/{sid}/cancel", json={"run_id": done[0]["run_id"]})
        assert r.status_code == 409
        assert (await client.post(f"/sessions/{sid}/cancel", json={})).status_code == 422
        assert (await client.post("/sessions/nope/cancel", json={"run_id": "x"})).status_code == 404


async def test_cancel_only_affects_own_session(mem_runtime, monkeypatch):
    monkeypatch.setenv("PLACEHOLDER_NODE_DELAY_S", "0.8")
    manager = app.state.run_manager
    async with _client() as client:
        a = (await client.post("/sessions")).json()["session_id"]
        b = (await client.post("/sessions")).json()["session_id"]
        ha = await manager.start(a, "a")
        # 用 b 的会话去取消 a 的 run：拒绝
        r = await client.post(f"/sessions/{b}/cancel", json={"run_id": ha.run_id})
        assert r.status_code == 409
        assert manager.is_live(ha.run_id)
        assert (await client.post(f"/sessions/{a}/cancel", json={"run_id": ha.run_id})).json()[
            "status"
        ] == "cancelled"
        # 取消后会话可继续
        nxt = sse.parse((await client.post(f"/sessions/{a}/messages", data={"text": "再来"})).text)
    assert nxt[-1]["reason"] == "completed"
