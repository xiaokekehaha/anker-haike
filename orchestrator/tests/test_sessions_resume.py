import asyncio

import pytest
from haike_contracts.snapshot import SessionSnapshot
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.sessions import sse


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _wait_active(store, sid: str):
    for _ in range(100):
        await asyncio.sleep(0.01)
        row = await store.get_session(sid)
        if row.active_run_id:
            return row.active_run_id
    pytest.fail("run never became active")


async def _wait_done(store, sid: str):
    for _ in range(300):
        await asyncio.sleep(0.02)
        if (await store.get_session(sid)).active_run_id is None:
            return
    pytest.fail("run never finished")


async def test_disconnect_does_not_cancel_run(mem_runtime, monkeypatch):
    """前端 abort fetch 不等于取消：订阅者中途退出，run 继续到 done，事件照常落库（08 §7）。
    注：httpx ASGITransport 不做真流式，这里直接对 RunManager 订阅后退出来模拟断开。"""
    monkeypatch.setenv("PLACEHOLDER_NODE_DELAY_S", "0.3")
    manager = app.state.run_manager
    sid = (await mem_runtime.create_session()).session_id
    handle = await manager.start(sid, "a")
    sub = manager.subscribe(sid, handle.run_id, after_seq=0)
    first = await anext(sub)
    await sub.aclose()  # 断开
    assert first["type"] == "run_started"
    assert (await mem_runtime.get_session(sid)).active_run_id == handle.run_id
    await _wait_done(mem_runtime, sid)
    events = await mem_runtime.list_events(sid, run_id=handle.run_id)
    assert [e["type"] for e in events] == [
        "run_started",
        "progress",
        "progress",
        "message_start",  # 票 24：品类未定 → 追问
        "message",
        "message_end",
        "done",
    ]
    assert events[-1]["reason"] == "completed"
    assert not manager.is_live(handle.run_id)


async def test_resume_mid_run_replays_then_live_no_dup_no_gap(mem_runtime, monkeypatch):
    monkeypatch.setenv("PLACEHOLDER_NODE_DELAY_S", "0.4")
    manager = app.state.run_manager
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        handle = await manager.start(sid, "a")  # 相当于首连拿到 run_started 后断开
        first = await mem_runtime.list_events(sid, run_id=handle.run_id)
        assert [e["type"] for e in first] == ["run_started"]
        # 等到第一个 progress 已落库（断流期间错过的事件），再续接
        for _ in range(100):
            await asyncio.sleep(0.01)
            if len(await mem_runtime.list_events(sid, run_id=handle.run_id)) >= 2:
                break
        assert manager.is_live(handle.run_id)
        resumed = await client.get(
            f"/sessions/{sid}/runs/{handle.run_id}/events", params={"after_seq": first[-1]["seq"]}
        )
        assert resumed.status_code == 200
        assert resumed.headers["content-type"].startswith("text/event-stream")
        tail = sse.parse(resumed.text)
    all_events = first + tail
    logged = await mem_runtime.list_events(sid, run_id=handle.run_id)
    assert all_events == logged  # 重放 + 实时：不重复不丢失
    assert [e["seq"] for e in all_events] == list(range(1, len(logged) + 1))
    assert tail[0]["type"] == "progress" and tail[-1]["type"] == "done"


async def test_resume_finished_run_replays_full_history_and_closes(mem_runtime):
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        full = sse.parse((await client.post(f"/sessions/{sid}/messages", data={"text": "a"})).text)
        run_id = full[0]["run_id"]
        replay = sse.parse((await client.get(f"/sessions/{sid}/runs/{run_id}/events")).text)
        assert replay == full
        partial = sse.parse(
            (
                await client.get(f"/sessions/{sid}/runs/{run_id}/events", params={"after_seq": 2})
            ).text
        )
        assert partial == full[2:]
        beyond = await client.get(f"/sessions/{sid}/runs/{run_id}/events", params={"after_seq": 99})
        assert beyond.status_code == 200 and sse.parse(beyond.text) == []
        # 标准 SSE 重连头等价于 after_seq
        hdr = sse.parse(
            (
                await client.get(
                    f"/sessions/{sid}/runs/{run_id}/events", headers={"Last-Event-ID": "3"}
                )
            ).text
        )
        assert hdr == full[3:]


async def test_resume_unknown_run_or_session_404(mem_runtime):
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        assert (await client.get(f"/sessions/{sid}/runs/nope/events")).status_code == 404
        assert (await client.get("/sessions/nope/runs/x/events")).status_code == 404
        assert (
            await client.get(f"/sessions/{sid}/runs/x/events", params={"after_seq": -1})
        ).status_code == 422


async def test_two_subscribers_see_same_live_events(mem_runtime, monkeypatch):
    monkeypatch.setenv("PLACEHOLDER_NODE_DELAY_S", "0.3")
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        t1 = asyncio.create_task(client.post(f"/sessions/{sid}/messages", data={"text": "a"}))
        run_id = await _wait_active(mem_runtime, sid)
        t2 = asyncio.create_task(client.get(f"/sessions/{sid}/runs/{run_id}/events"))
        r1, r2 = await asyncio.gather(t1, t2)
    assert (
        sse.parse(r1.text)
        == sse.parse(r2.text)
        == await mem_runtime.list_events(sid, run_id=run_id)
    )


async def test_reconcile_orphans_after_restart(mem_runtime):
    """服务重启：投影里 active 但内存无 live run → error(server_restarted) + done(error)，快照可恢复。"""
    from app.sessions.manager import RunManager

    store = mem_runtime
    sid = (await store.create_session()).session_id
    await store.try_start_run(sid, "dead-run")
    await store.append_event(
        sid,
        "dead-run",
        {
            "type": "run_started",
            "seq": 1,
            "run_id": "dead-run",
            "resumed": False,
            "deadline_ms": 25000,
        },
    )
    await store.append_event(
        sid, "dead-run", {"type": "progress", "seq": 2, "run_id": "dead-run", "stage": "intake"}
    )

    fresh = RunManager(store, app.state.session_graph)  # 模拟新进程
    fixed = await fresh.reconcile_orphans()
    assert fixed == [(sid, "dead-run")]
    events = await store.list_events(sid, run_id="dead-run")
    assert [e["type"] for e in events] == ["run_started", "progress", "error", "done"]
    assert events[2]["code"] == "server_restarted" and events[2]["recoverable"] is True
    assert events[3]["reason"] == "error" and [e["seq"] for e in events] == [1, 2, 3, 4]
    assert (await store.get_session(sid)).active_run_id is None
    # 二次 reconcile 幂等
    assert await fresh.reconcile_orphans() == []

    app.state.run_manager = fresh
    async with _client() as client:
        snap = SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())
        assert snap.active_run is None and snap.last_error.code == "server_restarted"
        # 续接已收尾的孤儿 run：重放到 done 后关闭
        replay = sse.parse(
            (
                await client.get(f"/sessions/{sid}/runs/dead-run/events", params={"after_seq": 2})
            ).text
        )
        assert [e["type"] for e in replay] == ["error", "done"]
        # 会话可继续发消息
        nxt = sse.parse(
            (await client.post(f"/sessions/{sid}/messages", data={"text": "再来"})).text
        )
        assert nxt[-1]["type"] == "done" and nxt[-1]["reason"] == "completed" and nxt[0]["seq"] == 5
