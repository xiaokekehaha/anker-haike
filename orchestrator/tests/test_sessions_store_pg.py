"""PostgresSessionStore 集成测试：本机 / Compose 的 postgres 可连时运行，否则跳过。"""

import asyncio

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.sessions.store import ActiveRunConflict, PostgresSessionStore, SessionNotFound
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

    assert await pg_store.finish_run(sid, "run-a", version=5, stage="diagnose") == 5
    after = await pg_store.get_session(sid)
    assert after.active_run_id is None and after.stage == "diagnose" and after.version == 5

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


async def test_pg_projection_delete_and_rebuild(pg_store):
    """删除投影行后事件日志仍在，可从事件日志 + checkpoint 重建（票 07 验收项 3）。"""
    from langgraph.checkpoint.memory import InMemorySaver

    from app.sessions import runner
    from app.sessions.graph import build_graph
    from app.sessions.snapshot import build_snapshot, rebuild_projection

    graph = build_graph(InMemorySaver())
    sid = (await pg_store.create_session()).session_id
    async for _ in runner.run_message(pg_store, graph, sid, "你好"):
        pass
    before = await build_snapshot(pg_store, graph, sid)
    before_row = await pg_store.get_session(sid)

    await pg_store.delete_projection(sid)
    assert await pg_store.session_exists(sid)  # 事件日志未受影响
    # run_started + 2 progress + message_start/message/message_end + done；timeline 折叠为用户消息 + 追问（票 24）
    assert len(before.timeline) == 2
    assert len(await pg_store.list_event_records(sid)) == 7
    with pytest.raises(SessionNotFound):
        await pg_store.get_session(sid)

    after = await rebuild_projection(pg_store, graph, sid)
    assert after == before
    row = await pg_store.get_session(sid)
    assert (row.version, row.stage, row.active_run_id, row.pending_input) == (
        before_row.version,
        before_row.stage,
        None,
        None,
    )
    assert sid in await pg_store.list_session_ids()


async def test_pg_saver_awaiting_input_version_matches_done(pg_store):
    """回归（票 20）：真实 AsyncPostgresSaver 下 awaiting_input.version 必须等于 done.version 与快照 version。
    内存 saver 同步写入测不出这个竞态。"""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    from app.sessions import runner
    from app.sessions.graph import build_graph
    from app.sessions.snapshot import build_snapshot

    saver = AsyncPostgresSaver(pg_store._pool)  # type: ignore[arg-type]
    await saver.setup()
    graph = build_graph(saver)
    sid = (await pg_store.create_session()).session_id
    events = [e async for e in runner.run_message(pg_store, graph, sid, "我的 S1 Pro 不吸了")]
    types = [e["type"] for e in events]
    assert types[-3:] == ["product_card", "awaiting_input", "done"]
    card, awaiting, done = events[-3], events[-2], events[-1]
    assert done["reason"] == "awaiting_input"
    assert card["version"] == awaiting["version"] == done["version"]
    snap = await build_snapshot(pg_store, graph, sid)
    assert snap.version == done["version"] and snap.pending_input.version == done["version"]
    # 恢复后 prepare_card 仍只执行一次
    action = {
        "action_id": "a1",
        "interrupt_id": awaiting["interrupt_id"],
        "card_id": awaiting["card_id"],
        "expected_version": awaiting["version"],
        "kind": "select_product",
        "payload": {"sku": "EUFY-S1-PRO"},
    }
    resumed = [e async for e in runner.run_message(pg_store, graph, sid, resume=action)]
    assert resumed[0]["resumed"] is True and resumed[-1]["reason"] == "completed"
    state = await graph.aget_state({"configurable": {"thread_id": sid}})
    assert (
        state.values["prepare_card_calls"] == 1 and state.values["product_state"] == "confirmed_sku"
    )


async def test_pg_actions_table_and_advisory_lock(pg_store):
    from app.sessions.locks import LockTimeout, PostgresSessionLock

    sid = (await pg_store.create_session()).session_id
    assert await pg_store.get_action(sid, "a1") is None
    assert (
        await pg_store.try_insert_action(sid, "a1", {"run_id": "r1", "status": "pending"}) is True
    )
    assert (
        await pg_store.try_insert_action(sid, "a1", {"run_id": "r2", "status": "pending"}) is False
    )
    assert (await pg_store.get_action(sid, "a1"))["run_id"] == "r1"
    await pg_store.set_action_result(
        sid, "a1", {"run_id": "r1", "status": "done", "version_after": 4}
    )
    assert (await pg_store.get_action(sid, "a1"))["version_after"] == 4

    lock = PostgresSessionLock(pg_store._pool)
    async with lock.hold(sid, timeout_s=2):
        with pytest.raises(LockTimeout):
            async with lock.hold(sid, timeout_s=0.2):
                pass
        async with lock.hold(sid + "-other", timeout_s=0.5):
            pass
    async with lock.hold(sid, timeout_s=0.5):
        pass
