
import asyncio

import pytest
from haike_contracts.events import parse_event
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.sessions import runner, sse
from tests.message_form import message_form


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _create(client) -> str:
    resp = await client.post("/sessions")
    assert resp.status_code == 201
    body = resp.json()
    assert body["version"] == 0 and len(body["session_id"]) == 32
    return body["session_id"]


async def _send(client, sid: str, text: str) -> tuple[list[dict], str]:
    resp = await client.post(f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": text}))
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers["x-accel-buffering"] == "no"
    return sse.parse(resp.text), resp.text


async def test_create_session_returns_id_and_version_0(mem_runtime):
    async with _client() as client:
        await _create(client)


async def test_message_stream_order_and_event_log(mem_runtime):
    async with _client() as client:
        sid = await _create(client)
        events, raw = await _send(client, sid, "机器不亮了")

    types = [e["type"] for e in events]
    assert types[0] == "run_started" and types[-1] == "done"
    # 票 24：品类未定 → intake / disambiguate / clarify（一句追问）；run 以 done(completed) 结束
    assert types[1:-1] == ["input_received", "progress", "progress", "issue_changed", "message_start", "message", "message_end"]
    assert [e["stage"] for e in events if e["type"] == "progress"] == ["intake", "disambiguate"]
    # version = checkpoint step + 1：一轮 intake / disambiguate / clarify 三节点 → 4
    assert events[-1]["reason"] == "completed" and events[-1]["version"] == 1
    assert events[0]["resumed"] is False and events[0]["deadline_ms"] == runner.DEFAULT_DEADLINE_MS
    for e in events:
        parse_event(e)  # 全部符合契约
    # SSE 帧：id = seq、event = type
    assert "id: 1\nevent: run_started\n" in raw

    # 事件日志与发送内容一致、seq 连续、同一 run_id
    logged = await mem_runtime.list_events(sid)
    assert [e for e in logged if e.get("visibility") != "internal"] == events
    assert [e["seq"] for e in logged] == list(range(1, len(logged) + 1))
    assert len({e["run_id"] for e in logged}) == 1

    row = await mem_runtime.get_session(sid)
    assert row.version == 1 and row.active_run_id is None and row.stage == "disambiguate"


async def test_second_turn_continues_seq_and_version(mem_runtime):
    async with _client() as client:
        sid = await _create(client)
        first, _ = await _send(client, sid, "第一句")
        second, _ = await _send(client, sid, "第二句")
    assert second[0]["seq"] == first[-1]["seq"] + 1
    assert second[-1]["version"] == 2  # 第二轮 checkpoint 续增
    assert first[0]["run_id"] != second[0]["run_id"]


async def test_ping_every_interval_while_node_runs(mem_runtime, monkeypatch):
    monkeypatch.setenv("PLACEHOLDER_NODE_DELAY_S", "0.35")
    monkeypatch.setattr(runner, "PING_INTERVAL_S", 0.1)
    async with _client() as client:
        sid = await _create(client)
        events, _ = await _send(client, sid, "慢一点")
    types = [e["type"] for e in events]
    assert types.count("ping") >= 2
    # ping 夹在 progress 之间，不影响 seq 连续
    assert [e["seq"] for e in events] == sorted({e["seq"] for e in events})
    assert types[-1] == "done" and events[-1]["reason"] == "completed"


async def test_error_path_ends_with_done_error(mem_runtime, monkeypatch):
    from types import SimpleNamespace

    import app.sessions.graph as graph_module

    def fail(**kwargs):
        raise RuntimeError("injected node failure")

    monkeypatch.setattr(graph_module, "get_rules_service", lambda: SimpleNamespace(check_in=fail))
    async with _client() as client:
        sid = await _create(client)
        events, _ = await _send(client, sid, "机器不亮了")
    types = [e["type"] for e in events]
    assert types == ["run_started", "input_received", "progress", "error", "done"]
    err = next(e for e in events if e["type"] == "error")
    assert err["code"] == "node_failed" and "injected node failure" in err["message"]
    assert err["recoverable"] is False and err["retry_with_same_action"] is False
    assert events[-1]["reason"] == "error"
    # 失败的 run 同样释放 active run，version 仍推进（本 run 已提交事件）
    row = await mem_runtime.get_session(sid)
    assert row.active_run_id is None
    assert await mem_runtime.list_events(sid) == events


async def test_deadline_exceeded_emits_recoverable_error(mem_runtime, monkeypatch):
    monkeypatch.setenv("PLACEHOLDER_NODE_DELAY_S", "1")
    store = mem_runtime
    events = [
        e
        async for e in runner.run_message(
            store,
            app.state.session_graph,
            (await store.create_session()).session_id,
            "x",
            deadline_ms=200,
            ping_interval_s=0.05,
        )
    ]
    types = [e["type"] for e in events]
    assert types[0] == "run_started" and types[-2] == "error" and types[-1] == "done"
    assert events[-2]["code"] == "deadline_exceeded" and events[-2]["recoverable"] is True
    assert events[-1]["reason"] == "error"


async def test_concurrent_second_message_rejected_409(mem_runtime, monkeypatch):
    monkeypatch.setenv("PLACEHOLDER_NODE_DELAY_S", "0.5")
    async with _client() as client:
        sid = await _create(client)
        first_task = asyncio.create_task(
            client.post(f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": "a"}))
        )
        # 等首个 run 占用 active_run
        for _ in range(50):
            await asyncio.sleep(0.01)
            if (await mem_runtime.get_session(sid)).active_run_id:
                break
        else:
            pytest.fail("first run never became active")
        second = await client.post(f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": "b"}))
        assert second.status_code == 409
        body = second.json()
        assert body["code"] == "run_active"
        assert body["snapshot"]["session_id"] == sid and body["snapshot"]["active_run"]["run_id"]
        first = await first_task
    assert first.status_code == 200
    events = sse.parse(first.text)
    assert events[-1]["type"] == "done" and events[-1]["reason"] == "completed"
    # 只产生了一个 run
    assert len({e["run_id"] for e in await mem_runtime.list_events(sid)}) == 1
    assert (await mem_runtime.get_session(sid)).version == 1


async def test_unknown_session_404_and_empty_text_422(mem_runtime):
    async with _client() as client:
        assert (await client.post("/sessions/nope/messages", data=await message_form(client, "/sessions/nope/messages", {"text": "x"}))).status_code == 404
        sid = await _create(client)
        assert (
            await client.post(f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": ""}))
        ).status_code == 422


async def test_probe_reports_only_live_sessions(mem_runtime):
    """前端最近会话列表靠这条路由剔除已回收的本地引用（spec_session_recent_verify）。"""
    async with _client() as client:
        sid = await _create(client)
        resp = await client.post("/sessions/_exists", json={"session_ids": [sid, "gone", sid]})
        assert resp.status_code == 200
        assert resp.json() == {"alive": [sid]}  # 去重后只回存在的

        assert (await client.post("/sessions/_exists", json={"session_ids": []})).json() == {"alive": []}
        over = await client.post("/sessions/_exists", json={"session_ids": [f"s{i}" for i in range(51)]})
        assert over.status_code == 422 and over.json()["detail"]["code"] == "too_many_ids"


async def test_probe_503_when_store_unavailable():
    """存储不可用必须是 503 而不是「都不存在」，否则前端会把整份列表判死。"""
    app.state.session_store = None
    app.state.session_graph = None
    app.state.run_manager = None
    async with _client() as client:
        resp = await client.post("/sessions/_exists", json={"session_ids": ["a"]})
    assert resp.status_code == 503 and resp.json()["detail"]["code"] == "sessions_unavailable"


async def test_sessions_503_when_store_unavailable():
    app.state.session_store = None
    app.state.session_graph = None
    app.state.run_manager = None
    async with _client() as client:
        resp = await client.post("/sessions")
    assert resp.status_code == 503 and resp.json()["detail"]["code"] == "sessions_unavailable"
