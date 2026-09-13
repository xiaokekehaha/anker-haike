from datetime import UTC, datetime, timedelta

from app.conversation.history import ConversationEntry
from app.conversation.summary_cache import SummaryCache, extract_summary, read_summary
from app.sessions.store import InMemorySessionStore
from tests.test_conversation_inputs_pg import isolated_store  # noqa: F401


def candidate(sid):
    return dict(
        session_id=sid,
        summary_id="summary1",
        through_seq=10,
        source_context_revision=3,
        source_entry_ids=["old-q", "old-a"],
        text="完整原话",
        generated_at=datetime.now(UTC).isoformat(),
        status="active",
        expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    )


def test_extract_keeps_complete_qa_and_source_times():
    entries = []
    for i in range(31):
        for j, role in enumerate(["user", "assistant"]):
            entries.append(
                ConversationEntry(
                    entry_id=f"{role}{i}",
                    session_id="s",
                    run_id=f"r{i}",
                    kind="message",
                    role=role,
                    first_seq=i * 2 + j + 1,
                    last_seq=i * 2 + j + 1,
                    recorded_at="2026-09-13T00:00:00Z",
                    text=f"{role}完整原话{i}",
                )
            )
    result = extract_summary(entries)
    assert "user完整原话0" in result["text"] and "assistant完整原话0" in result["text"]
    assert "2026-09-13T00:00:00Z" in result["text"]
    assert len(result["source_entry_ids"]) % 2 == 0
    assert result["through_seq"] <= 50


async def exercise_cache(store):
    sid = (await store.create_session()).session_id
    receipt, _ = await store.reserve_input(
        sid, "i", {"kind": "message", "text": "x"}, expected_version=0
    )
    await store.publish_commit(receipt, "checkpoint1", "intake", {})
    await store.complete_input(receipt, "completed")
    cache = SummaryCache(store, None)
    value = candidate(sid)
    assert not await cache.save(value, "wrong-checkpoint")
    updated = (await store.get_session(sid)).updated_at
    assert await cache.save(value, "checkpoint1")
    assert (await store.get_session(sid)).updated_at == updated  # derived writes do not extend TTL
    assert await read_summary(store, sid, 3, 11)
    assert await read_summary(store, sid, 4, 11) is None  # correction
    assert await read_summary(store, sid, 3, 9) is None  # future summary cannot enter old snapshot
    await store.delete_session_data(sid)
    assert not await cache.save(value, "checkpoint1")
    assert await read_summary(store, sid, 3, 11) is None


async def test_memory_cache_cas_expiry_and_deleted_session():
    await exercise_cache(InMemorySessionStore())


async def test_postgres_cache_cas_expiry_and_deleted_session(isolated_store):
    await exercise_cache(isolated_store)
