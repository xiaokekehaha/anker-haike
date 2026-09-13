"""Real transactions in a disposable schema in the project's PostgreSQL instance."""

import asyncio
import uuid

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.sessions.inputs import InputConflict
from app.sessions.store import PostgresSessionStore
from app.settings import settings


@pytest.fixture
async def isolated_store():
    try:
        conn = await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True, connect_timeout=2
        )
    except psycopg.OperationalError:
        pytest.skip("project PostgreSQL not reachable")
    schema = "conversation_test_" + uuid.uuid4().hex
    await conn.execute(psycopg.sql.SQL("create schema {}").format(psycopg.sql.Identifier(schema)))
    pool = AsyncConnectionPool(
        settings.database_url,
        min_size=1,
        max_size=8,
        open=False,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
            "options": f"-c search_path={schema}",
        },
    )
    try:
        await pool.open(wait=True)
        store = PostgresSessionStore(pool)
        await store.setup()
        yield store
    finally:
        await pool.close()
        await conn.execute(
            psycopg.sql.SQL("drop schema {} cascade").format(psycopg.sql.Identifier(schema))
        )
        await conn.close()


async def test_atomic_receipt_publish_and_finish_under_retries(isolated_store):
    store = isolated_store
    sid = (await store.create_session()).session_id
    results = await asyncio.gather(
        *[
            store.reserve_input(sid, "i1", {"kind": "message", "text": "测试"}, expected_version=0)
            for _ in range(12)
        ]
    )
    assert sum(not replay for _, replay in results) == 1
    receipt = results[0][0]
    assert len(await store.list_events(sid)) == 2
    with pytest.raises(InputConflict, match="input_id_conflict"):
        await store.reserve_input(
            sid, "i1", {"kind": "message", "text": "不同正文"}, expected_version=0
        )
    with pytest.raises(InputConflict, match="run_active"):
        await store.reserve_input(
            sid, "i2", {"kind": "message", "text": "并发"}, expected_version=0
        )
    versions = await asyncio.gather(
        *[
            store.publish_commit(receipt, "checkpoint-1", "guide", {"input_id": "i1"})
            for _ in range(5)
        ]
    )
    assert versions == [1] * 5
    row = await store.get_session(sid)
    assert row.published_checkpoint_id == "checkpoint-1" and row.version == 1
    done = await asyncio.gather(*[store.complete_input(receipt, "completed") for _ in range(5)])
    assert all(e == done[0] for e in done)
    events = await store.list_events(sid)
    assert [e["type"] for e in events] == [
        "run_started",
        "input_received",
        "state_committed",
        "done",
    ]
    assert (await store.get_session(sid)).active_run_id is None
    assert (await store.get_input(sid, "i1"))["state_commit_version"] == 1
    same, replay = await store.reserve_input(
        sid, "i1", {"kind": "message", "text": "测试"}, expected_version=0
    )
    assert replay and same["run_id"] == receipt["run_id"]


async def test_event_identity_is_unique_and_payload_conflicts_fail(isolated_store):
    store = isolated_store
    sid = (await store.create_session()).session_id
    receipt, _ = await store.reserve_input(
        sid, "i1", {"kind": "message", "text": "测试"}, expected_version=0
    )
    event = {"type": "ping", "event_id": "same", "recorded_at": "2026-09-13T00:00:00Z"}
    seqs = await asyncio.gather(
        *[store.append_event(sid, receipt["run_id"], event) for _ in range(8)]
    )
    assert seqs == [3] * 8
    with pytest.raises(RuntimeError, match="event_id_payload_conflict"):
        await store.append_event(sid, receipt["run_id"], {**event, "type": "different"})
    assert len(await store.list_events(sid)) == 3


async def test_images_roll_back_with_receipt_and_retries_reuse_original(isolated_store):
    from app.images.store import PostgresImageStore, stage_image

    store = isolated_store
    images = PostgresImageStore(store._pool)
    await images.setup()
    sid = (await store.create_session()).session_id
    staged = [stage_image(sid, "photo", 0, "fault", b"\x89PNG\r\n\x1a\nexample", "image/png")]
    payload = {
        "kind": "message",
        "text": "",
        "image_ids": [staged[0].ref.image_id],
        "attachment_hashes": [staged[0].ref.sha256],
    }

    class FailingImages(PostgresImageStore):
        async def persist_staged(self, staged, *, conn):
            await super().persist_staged(staged, conn=conn)
            raise RuntimeError("injected_after_image_write")

    with pytest.raises(RuntimeError, match="injected_after_image_write"):
        await store.reserve_input(
            sid,
            "photo",
            payload,
            expected_version=0,
            staged_images=staged,
            image_store=FailingImages(store._pool),
        )
    assert await images.refs(sid, payload["image_ids"]) == []
    assert await store.get_input(sid, "photo") is None
    assert await store.list_events(sid) == []
    assert (await store.get_session(sid)).active_run_id is None
    results = await asyncio.gather(
        *[
            store.reserve_input(
                sid, "photo", payload, expected_version=0, staged_images=staged, image_store=images
            )
            for _ in range(5)
        ]
    )
    assert sum(not replay for _, replay in results) == 1
    assert len(await images.refs(sid, payload["image_ids"])) == 1


async def test_snapshot_pins_pointer_and_watermark_against_publish(isolated_store):
    store = isolated_store
    sid = (await store.create_session()).session_id
    receipt, _ = await store.reserve_input(
        sid, "i1", {"kind": "message", "text": "hello"}, expected_version=0
    )
    async with store.snapshot_view(sid) as (row, records):
        pending = asyncio.create_task(store.publish_commit(receipt, "ckpt1", "guide", {}))
        assert row.version == 0 and row.published_checkpoint_id is None
        assert records[-1].seq == 2
        assert not pending.done()
    assert await pending == 1
    async with store.snapshot_view(sid) as (row, records):
        assert row.version == 1 and row.published_checkpoint_id == "ckpt1"
        assert records[-1].seq == 3
        assert records[-1].event["type"] == "state_committed"
