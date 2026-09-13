"""User-visible lifecycle invariants of the single conversation protocol."""

import asyncio

import pytest

from app.main import app
from app.sessions import sse
from tests.conversation_runtime import REPORT, REPORT_TEXT
from tests.conversation_runtime import conversation as conversation  # noqa: PLC0414


async def test_refresh_preserves_order_sources_and_answer_time(conversation):
    c = conversation
    first = await c.send(REPORT_TEXT, REPORT, input_id="report")
    snapshot = await c.snapshot()
    assert [item["first_seq"] for item in snapshot["timeline"]] == sorted(
        item["first_seq"] for item in snapshot["timeline"]
    )
    assert all(item["at"] for item in snapshot["timeline"])
    assert snapshot["timeline"][0]["id"] == "report"
    assert (
        next(item for item in snapshot["timeline"] if item["kind"] == "assistant_message")[
            "reply_to_input_id"
        ]
        == "report"
    )
    original = {
        item["card_id"]: item for item in snapshot["timeline"] if item["kind"].endswith("card")
    }
    before_calls = len(c.knowledge.calls)
    await c.send("为什么要这样做", {"primary_intent": "explain", "device_relation": "current"})
    after = await c.snapshot()
    assert len(c.knowledge.calls) == before_calls
    assert after["pending_input"]["card_id"] == snapshot["pending_input"]["card_id"]
    assert {
        item["card_id"]: item for item in after["timeline"] if item["kind"].endswith("card")
    } == original
    replay = await c.client.get(f"/sessions/{c.sid}/runs/{first[0]['run_id']}/events")
    assert sse.parse(replay.text) == first
    last_intake = c.models["intake"].calls[-1]
    messages = "\n".join(str(m.content) for m in last_intake["messages"])
    assert REPORT_TEXT in messages and "请看下面的排查步骤" in messages
    assert after["timeline"][0]["at"] in messages


async def test_cancelled_turn_keeps_original_card_and_receipt(conversation, monkeypatch):
    c = conversation
    await c.send(REPORT_TEXT, REPORT)
    before = await c.snapshot()
    waiting = asyncio.Event()

    async def paused(*args, **kwargs):
        waiting.set()
        await asyncio.Future()

    monkeypatch.setattr("app.conversation.interpret.interpret_turn", paused)
    body = {
        "input_id": "cancelled",
        "expected_version": before["version"],
        "text": "再补充一个情况",
    }
    request = asyncio.create_task(c.client.post(f"/sessions/{c.sid}/messages", data=body))
    await asyncio.wait_for(waiting.wait(), 3)
    rid = (await app.state.session_store.get_session(c.sid)).active_run_id
    response = await c.client.post(f"/sessions/{c.sid}/cancel", json={"run_id": rid})
    assert response.status_code == 200
    original = c.check(await request)
    assert original[-1]["reason"] == "cancelled"
    after = await c.snapshot()
    assert after["pending_input"] == before["pending_input"]
    assert after["version"] == before["version"]
    retry = await c.client.post(f"/sessions/{c.sid}/messages", data=body)
    assert c.check(retry) == original
    assert retry.headers["x-input-replayed"] == "true"


async def test_partial_publication_returns_recovering_not_mixed_snapshot(conversation, monkeypatch):
    c = conversation
    store = app.state.session_store
    append = store.append_event
    waiting, release = asyncio.Event(), asyncio.Event()

    async def paused(sid, rid, event):
        if event["type"] == "issue_changed":
            waiting.set()
            await release.wait()
        return await append(sid, rid, event)

    monkeypatch.setattr(store, "append_event", paused)
    c.models["intake"].script.append(REPORT)
    request = asyncio.create_task(
        c.client.post(
            f"/sessions/{c.sid}/messages",
            data={"input_id": "report", "expected_version": 0, "text": REPORT_TEXT},
        )
    )
    try:
        await asyncio.wait_for(waiting.wait(), 3)
        response = await c.client.get(f"/sessions/{c.sid}")
        assert response.status_code == 503 and response.json()["detail"]["code"] == "recovering"
        assert response.headers["retry-after"] == "1"
    finally:
        release.set()
    c.check(await request)
    final = await c.snapshot()
    assert final["version"] == 1 and final["pending_input"]["kind"] == "step_feedback"


async def test_disconnect_does_not_cancel_and_resume_has_no_duplicates(conversation, monkeypatch):
    import app.conversation.interpret as semantic

    c = conversation
    real = semantic.interpret_turn
    waiting, release = asyncio.Event(), asyncio.Event()

    async def paused(*args, **kwargs):
        waiting.set()
        await release.wait()
        return await real(*args, **kwargs)

    monkeypatch.setattr(semantic, "interpret_turn", paused)
    request = asyncio.create_task(c.send(REPORT_TEXT, REPORT))
    await asyncio.wait_for(waiting.wait(), 3)
    rid = (await app.state.session_store.get_session(c.sid)).active_run_id
    manager = app.state.run_manager
    subscriber = manager.subscribe(c.sid, rid)
    first = await anext(subscriber)
    await subscriber.aclose()
    assert manager.is_live(rid)
    release.set()
    output = await request
    response = await c.client.get(
        f"/sessions/{c.sid}/runs/{rid}/events", params={"after_seq": first["seq"]}
    )
    assert [first, *sse.parse(response.text)] == output
    assert len({event["seq"] for event in output}) == len(output)
    assert not any(event.get("visibility") == "internal" for event in output)


@pytest.mark.parametrize("kind", ["rediagnose", "resume"])
async def test_removed_actions_are_not_accepted(conversation, kind):
    c = conversation
    response = await c.client.post(
        f"/sessions/{c.sid}/actions",
        json={"action_id": "old", "kind": kind, "expected_version": 0, "payload": {"text": "继续"}},
    )
    assert response.status_code == 422
    assert await app.state.session_store.get_input(c.sid, "old") is None
