"""Canonical receipt is the transaction boundary, including concurrent retries."""

import asyncio

import pytest

from app.sessions.inputs import InputConflict, payload_digest
from app.sessions.store import InMemorySessionStore


async def test_retry_precedes_version_and_active_checks():
    store = InMemorySessionStore()
    sid = (await store.create_session()).session_id
    payload = {"kind": "message", "text": "耳机没有声音", "expected_version": 0}
    first, replay = await store.reserve_input(sid, "i1", payload, expected_version=0)
    assert not replay
    retry, replay = await store.reserve_input(sid, "i1", payload, expected_version=999)
    assert replay and retry == first
    assert len(await store.list_events(sid)) == 2
    with pytest.raises(InputConflict, match="input_id_conflict"):
        await store.reserve_input(sid, "i1", {**payload, "text": "新问题"}, expected_version=0)
    with pytest.raises(InputConflict, match="run_active"):
        await store.reserve_input(sid, "i2", payload, expected_version=0)
    assert await store.get_input(sid, "i2") is None


async def test_concurrent_identical_requests_have_one_run_and_input():
    store = InMemorySessionStore()
    sid = (await store.create_session()).session_id
    results = await asyncio.gather(
        *[
            store.reserve_input(sid, "i1", {"kind": "message", "text": "你好"}, expected_version=0)
            for _ in range(20)
        ]
    )
    assert sum(not replay for _, replay in results) == 1
    assert len({r["run_id"] for r, _ in results}) == 1
    events = await store.list_events(sid)
    assert [e["type"] for e in events] == ["run_started", "input_received"]
    assert events[1]["input_id"] == "i1"
    assert events[0]["recorded_at"] and events[0]["event_id"]


def test_digest_excludes_transport_but_preserves_attachment_order():
    base = {"text": "原话", "purpose": "fault", "attachment_hashes": ["a", "b"]}
    assert payload_digest(base) == payload_digest({**base, "expected_version": 42})
    assert payload_digest(base) != payload_digest({**base, "attachment_hashes": ["b", "a"]})


async def test_invalid_version_does_not_leave_partial_receipt():
    store = InMemorySessionStore()
    sid = (await store.create_session()).session_id
    with pytest.raises(InputConflict, match="stale_version"):
        await store.reserve_input(sid, "i1", {"kind": "message"}, expected_version=9)
    assert await store.list_events(sid) == []
    assert (await store.get_session(sid)).active_run_id is None


async def test_delete_removes_receipts():
    store = InMemorySessionStore()
    sid = (await store.create_session()).session_id
    await store.reserve_input(sid, "i1", {"kind": "message"}, expected_version=0)
    await store.delete_session_data(sid)
    assert await store.get_input(sid, "i1") is None
