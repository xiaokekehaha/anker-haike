"""haike-analytics：观测台的离线命令。

    haike-analytics backfill [--since 2026-09-01] [--no-logs] [--dry-run]
    haike-analytics stats

backfill 幂等（按 run_id / (run_id, idx) / session_id upsert），可反复跑。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.analytics.backfill import Backfiller, rotated
from app.analytics.store import InMemoryAnalyticsStore, PostgresAnalyticsStore
from app.settings import settings

log = logging.getLogger("analytics.cli")


async def _pool() -> AsyncConnectionPool:
    from psycopg.rows import dict_row as row_factory

    pool = AsyncConnectionPool(
        settings.database_url,
        min_size=1,
        max_size=4,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": row_factory},
    )
    await pool.open(wait=True, timeout=10)
    return pool


async def _graph(pool: AsyncConnectionPool):
    """带 checkpointer 的图，仅用于读会话状态；读不到就退化成空状态。"""
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        from app.sessions.graph import build_graph

        return build_graph(AsyncPostgresSaver(pool))  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001
        log.warning("checkpoint reader unavailable: %s", type(exc).__name__)
        return None


async def _backfill(args: argparse.Namespace) -> int:
    pool = await _pool()
    try:
        store = InMemoryAnalyticsStore() if args.dry_run else PostgresAnalyticsStore(pool)
        worker = Backfiller(pool, store, await _graph(pool))
        since = datetime.fromisoformat(args.since) if args.since else None
        paths = None if args.no_logs else rotated(Path(settings.observability_log_path))
        stats = await worker.run(
            since=since, log_paths=paths, store_text=settings.analytics_store_text
        )
    finally:
        await pool.close()
    print(json.dumps({"dry_run": args.dry_run, **stats.as_dict()}, ensure_ascii=False, indent=2))
    if stats.sessions_without_nodes:
        print(
            f"注意：{stats.sessions_without_nodes} 个会话没有节点轨迹"
            "（checkpoint 已按 TTL 清理），其 DAG 路径为空，指标不受影响。"
        )
    return 0


async def _stats(_args: argparse.Namespace) -> int:
    pool = await _pool()
    try:
        async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            out: dict[str, object] = {}
            for table in (
                "session_facts",
                "run_facts",
                "node_runs",
                "model_calls",
                "retrieval_calls",
                "cases",
            ):
                await cur.execute(f"select count(*) as n from analytics.{table}")
                out[table] = (await cur.fetchone())["n"]
            await cur.execute(
                """select outcome, count(*) as n from analytics.session_facts
                   group by 1 order by 2 desc"""
            )
            out["outcomes"] = {r["outcome"]: r["n"] for r in await cur.fetchall()}
    finally:
        await pool.close()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="管理员观测台的离线命令")
    sub = parser.add_subparsers(dest="command", required=True)

    bf = sub.add_parser("backfill", help="把历史会话补成 analytics 事实（幂等）")
    bf.add_argument("--since", help="只回填该时间之后的会话（ISO 格式）")
    bf.add_argument("--no-logs", action="store_true", help="跳过 JSONL 的模型 / 检索事实")
    bf.add_argument("--dry-run", action="store_true", help="只统计不写库")
    bf.set_defaults(func=_backfill)

    st = sub.add_parser("stats", help="打印各事实表行数与结果分布")
    st.set_defaults(func=_stats)

    args = parser.parse_args()
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
