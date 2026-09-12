"""PostgresSessionStore 集成测试：本机 / Compose 的 postgres 可连时运行，否则跳过。"""

import asyncio

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.sessions.store import ActiveRunConflict, PostgresSessionStore
from app.settings import settings


async def _reachable() -> bool:
    try:
        async with await asyncio.wait_for(
            psycopg.AsyncConnection.connect(settings.database_url, connect_timeout=1), 1.5
        ):
            return True
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture
async def pg_store():
    if not await _reachable():
        pytest.skip("postgres not reachable")
    pool = AsyncConnectionPool(
        settings.database_url,
        min_size=1,
        max_size=3,
        open=False,
        # 与 app.sessions.runtime 相同的连接参数，保证复现运行时行为
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await pool.open(wait=True, timeout=5)
    store = PostgresSessionStore(pool)
    await store.setup()
    yield store
    await pool.close()


async def test_pg_roundtrip_conflict_and_seq(pg_store):
    row = await pg_store.create_session()
    assert row.version == 0 and row.active_run_id is None
    sid = row.session_id

    await pg_store.try_start_run(sid, "run-a")
    with pytest.raises(ActiveRunConflict) as ei:
        await pg_store.try_start_run(sid, "run-b")
    assert ei.value.active_run_id == "run-a"

    seqs = [
        await pg_store.append_event(sid, "run-a", {"type": "ping", "seq": i, "run_id": "run-a"})
        for i in range(1, 4)
    ]
    assert seqs == [1, 2, 3]
    assert [e["seq"] for e in await pg_store.list_events(sid, after_seq=1)] == [2, 3]

    assert await pg_store.finish_run(sid, "run-a", stage="diagnose") == 1
    after = await pg_store.get_session(sid)
    assert after.active_run_id is None and after.stage == "diagnose" and after.version == 1

    # 第二个 run 的 seq 接着排
    await pg_store.try_start_run(sid, "run-b")
    assert (
        await pg_store.append_event(sid, "run-b", {"type": "ping", "seq": 4, "run_id": "run-b"})
        == 4
    )
    assert [e["run_id"] for e in await pg_store.list_events(sid, run_id="run-b")] == ["run-b"]


async def test_pg_concurrent_start_only_one_wins(pg_store):
    sid = (await pg_store.create_session()).session_id
    results = await asyncio.gather(
        *(pg_store.try_start_run(sid, f"run-{i}") for i in range(5)), return_exceptions=True
    )
    winners = [r for r in results if not isinstance(r, Exception)]
    losers = [r for r in results if isinstance(r, ActiveRunConflict)]
    assert len(winners) == 1 and len(losers) == 4
