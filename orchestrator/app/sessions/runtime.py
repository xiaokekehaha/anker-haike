"""应用生命周期内的会话运行时：连接池、存储、LangGraph checkpointer 与编译图。"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from app.sessions.graph import build_graph
from app.sessions.manager import RunManager
from app.sessions.store import PostgresSessionStore
from app.settings import settings

log = logging.getLogger("sessions.runtime")


async def open_session_runtime(app: FastAPI) -> None:
    app.state.session_store = None
    app.state.session_graph = None
    app.state.run_manager = None
    app.state.session_pool = None
    app.state.session_checkpointer_cm = None
    try:
        # PostgresSaver 需要 autocommit 与 dict_row（官方要求）；投影表存储用同一个池即可
        pool = AsyncConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=settings.db_pool_max,
            open=False,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": _dict_row()},
            timeout=settings.health_timeout_s * 2,
        )
        await pool.open(wait=True, timeout=settings.health_timeout_s * 2)
        store = PostgresSessionStore(pool)
        await store.setup()
        saver = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
        await saver.setup()
        app.state.session_pool = pool
        app.state.session_store = store
        app.state.session_graph = build_graph(saver)
        manager = RunManager(store, app.state.session_graph)
        app.state.run_manager = manager
        # 票 08：上次进程留下的 active run 以 error → done(error) 收尾，快照恢复到可继续状态
        fixed = await manager.reconcile_orphans()
        log.info("session runtime ready (orphan runs finalized: %d)", len(fixed))
    except Exception as exc:  # noqa: BLE001 - 启动期数据库故障要可见但不致命
        log.error("session runtime unavailable: %s: %s", type(exc).__name__, str(exc)[:200])


async def close_session_runtime(app: FastAPI) -> None:
    manager = getattr(app.state, "run_manager", None)
    if manager is not None:
        await manager.shutdown()
    pool = getattr(app.state, "session_pool", None)
    if pool is not None:
        await pool.close()


def _dict_row():
    from psycopg.rows import dict_row

    return dict_row
