"""投影表重建：haike-sessions-rebuild [--all | session_id ...]（票 07）。"""

from __future__ import annotations

import argparse
import asyncio
import sys

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.sessions.graph import build_graph
from app.sessions.snapshot import rebuild_projection
from app.sessions.store import PostgresSessionStore
from app.settings import settings


async def _run(session_ids: list[str], all_: bool) -> int:
    pool = AsyncConnectionPool(
        settings.database_url,
        min_size=1,
        max_size=4,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await pool.open(wait=True, timeout=10)
    try:
        store = PostgresSessionStore(pool)
        await store.setup()
        saver = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
        await saver.setup()
        graph = build_graph(saver)
        targets = await store.list_session_ids() if all_ else session_ids
        for sid in targets:
            snap = await rebuild_projection(store, graph, sid)
            print(
                f"{sid} version={snap.version} stage={snap.stage} "
                f"active_run={snap.active_run.run_id if snap.active_run else '-'} "
                f"pending={snap.pending_input.kind if snap.pending_input else '-'}"
            )
        print(f"rebuilt {len(targets)} session(s)")
        return 0
    finally:
        await pool.close()


def rebuild(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="从事件日志与 checkpoint 重建 sessions 投影表")
    ap.add_argument("session_ids", nargs="*")
    ap.add_argument("--all", action="store_true", help="重建全部会话")
    ns = ap.parse_args(sys.argv[1:] if argv is None else argv)
    if not ns.all and not ns.session_ids:
        ap.error("给出 session_id 或 --all")
    return asyncio.run(_run(ns.session_ids, ns.all))


if __name__ == "__main__":
    raise SystemExit(rebuild())
