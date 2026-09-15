"""数据保留与按会话删除（票 48；07 §12 记忆分类 TTL、§15 数据）。

分类 TTL（默认，均可由环境变量覆盖）：
- 图片 1 小时：session_images，由 app.images.runtime 的清理循环负责（票 29）。
- 会话状态 24 小时：sessions 投影 + session_events + session_inputs + session_images + LangGraph checkpoint 三表，
  以 sessions.updated_at 为准，有 active run 的会话不删；没有投影行的孤儿事件 / checkpoint 按 created_at 同步清。
- 检索追踪 7 天：retrieval_trace 随 checkpoint 一起过期；复盘用的 JSONL 日志轮转备份文件超过 7 天删除。

按 session_id 删除全部数据：`delete_session_data`（人工处理用户删除请求），HTTP 入口 DELETE /sessions/{id}
（X-Admin-Token），CLI `haike-retention delete <session_id>` / `haike-retention purge`。
每轮清理输出结构化日志 event=retention_purge，带各表删除行数。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.settings import settings

log = logging.getLogger("retention")

# 会话数据所在的表 → 会话键列。checkpoint 三表由 LangGraph AsyncPostgresSaver 建，可能尚不存在（惰性建表）。
SESSION_TABLES: tuple[tuple[str, str], ...] = (
    ("model_calls", "session_id"),
    ("retrieval_calls", "session_id"),
    ("node_runs", "session_id"),
    ("run_facts", "session_id"),
    ("session_facts", "session_id"),
    ("conversation_summaries", "session_id"),
    ("session_inputs", "session_id"),
    ("session_images", "session_id"),
    ("session_events", "session_id"),
    ("checkpoint_writes", "thread_id"),
    ("checkpoint_blobs", "thread_id"),
    ("checkpoints", "thread_id"),
    ("sessions", "session_id"),
)


@dataclass
class PurgeStats:
    cutoff: str
    sessions: int = 0
    orphan_sessions: int = 0
    deleted: dict[str, int] = field(default_factory=dict)
    log_backups_removed: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


async def _existing_tables(conn) -> set[str]:
    cur = await conn.execute(
        "select table_name from information_schema.tables where table_schema = current_schema()"
    )
    return {r[0] if not isinstance(r, dict) else r["table_name"] for r in await cur.fetchall()}


async def delete_session_data(pool: AsyncConnectionPool, session_id: str, *, expired_before: datetime | None = None) -> dict[str, int]:
    """删除一个会话在所有表里的数据，返回 {table: rows}。不存在的表跳过；总行数为 0 表示本来就没有数据。"""
    counts: dict[str, int] = {}
    async with pool.connection() as conn, conn.transaction():
        # Same row lock as acceptance/publication/snapshot; recheck expiry after acquiring it.
        cur = await conn.execute("select active_run_id,updated_at from sessions where session_id=%s for update", (session_id,))
        row = await cur.fetchone()
        if row:
            active, updated = (row["active_run_id"], row["updated_at"]) if isinstance(row, dict) else row
            if active or (expired_before is not None and updated >= expired_before):
                return {}
        tables = await _existing_tables(conn)
        if "cases" in tables:
            # Serialize the final aggregate snapshot with late manual decisions.
            await conn.execute("select case_id from cases where session_id=%s for update", (session_id,))
        if expired_before is not None and "cases" in tables:
            cur = await conn.execute("""select 1 from cases where session_id=%s and
                (closed_at is null or closed_at >= now()-interval '30 days') limit 1""", (session_id,))
            if await cur.fetchone():
                return {}
        if "service_episodes" in tables:
            from app.analytics.l3 import METRIC_ROWS_SQL

            await conn.execute(
                "with latest as (" + METRIC_ROWS_SQL + " where e.session_id=%s) "
                "update service_episodes e set rating=l.rating,intent_correct=l.intent_correct,"
                "human_involved=l.human_involved,outcome=l.outcome,session_id=null,issue_id=null "
                "from latest l where e.episode_id=l.episode_id", (session_id,),
            )
        if "cases" in tables:
            # L3 cases outlive the conversation; retain aggregate status, erase identifying content.
            for table, statement in (
                ("case_events", "update case_events set payload='{}',actor='anonymized' where case_id in (select case_id from cases where session_id=%s)"),
                ("human_decisions", "update human_decisions set actor='anonymized',note='',override_reason=null,edited_proposal=null,consumed_input_id=null where case_id in (select case_id from cases where session_id=%s)"),
                ("action_executions", "update action_executions set session_id=null,issue_id=null,request='{}',receipt=jsonb_build_object('status',status),error=null,gate_result=null where session_id=%s"),
                ("satisfaction_ratings", "update satisfaction_ratings set session_id=null,issue_id=null,comment=null where session_id=%s"),
                ("cases", "update cases set session_id=null,issue_id=null,proposal=null,policy_decision=null,gate_result=null,external_refs='{}',owner=null where session_id=%s"),
            ):
                if table in tables:
                    cur = await conn.execute(statement, (session_id,))
                    counts[table + "_anonymized"] = cur.rowcount or 0
        for table, col in SESSION_TABLES:
            if table not in tables:
                continue
            cur = await conn.execute(f"delete from {table} where {col} = %s", (session_id,))
            counts[table] = cur.rowcount or 0
    if sum(counts.values()):
        log.info(
            "session data deleted session=%s rows=%s",
            session_id,
            counts,
            extra={"event": "session_deleted", "session_id": session_id, "deleted": counts},
        )
    return counts


async def purge_expired(
    pool: AsyncConnectionPool,
    *,
    session_ttl: timedelta,
    log_path: str | None = None,
    trace_ttl: timedelta | None = None,
) -> PurgeStats:
    """按分类 TTL 清理：过期且无 active run 的会话整体删除；孤儿事件 / checkpoint 按时间清；日志备份按 trace_ttl 清。"""
    cutoff = datetime.now(UTC) - session_ttl
    stats = PurgeStats(cutoff=cutoff.isoformat())
    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        tables = await _existing_tables(conn)
        await cur.execute(
            "select session_id from sessions where updated_at < %s and active_run_id is null",
            (cutoff,),
        )
        expired = [r["session_id"] for r in await cur.fetchall()]
        # 没有投影行的孤儿数据（投影被删或重建前的残留）：以最后一条事件时间判定
        if "session_events" in tables:
            await cur.execute(
                """select e.session_id from session_events e
                   left join sessions s on s.session_id = e.session_id
                   where s.session_id is null
                   group by e.session_id having max(e.created_at) < %s""",
                (cutoff,),
            )
            orphans = [r["session_id"] for r in await cur.fetchall()]
        else:
            orphans = []
    for sid in [*expired, *orphans]:
        for table, n in (await delete_session_data(pool, sid, expired_before=cutoff)).items():
            stats.deleted[table] = stats.deleted.get(table, 0) + n
    stats.sessions, stats.orphan_sessions = len(expired), len(orphans)
    if log_path and trace_ttl is not None:
        stats.log_backups_removed = purge_log_backups(log_path, trace_ttl)
    log.info(
        "retention purge sessions=%d orphans=%d deleted=%s log_backups=%d cutoff=%s",
        stats.sessions, stats.orphan_sessions, stats.deleted, stats.log_backups_removed, stats.cutoff,
        extra={"event": "retention_purge", **stats.as_dict()},
    )
    return stats


def purge_log_backups(log_path: str, older_than: timedelta) -> int:
    """删除 JSONL 轮转备份（<name>.1、<name>.2 …）里修改时间早于 TTL 的文件；当前文件不动。"""
    path = Path(log_path)
    if not path.parent.is_dir():
        return 0
    cutoff = datetime.now(UTC) - older_than
    removed = 0
    for p in path.parent.glob(f"{path.name}.*"):
        try:
            if p.is_file() and datetime.fromtimestamp(p.stat().st_mtime, UTC) < cutoff:
                p.unlink()
                removed += 1
        except OSError:
            log.warning("cannot remove log backup %s", p)
    return removed


def ttl_config() -> dict[str, timedelta]:
    return {
        "images": timedelta(hours=1),
        "sessions": timedelta(hours=settings.retention_session_hours),
        "traces": timedelta(days=settings.retention_trace_days),
    }


async def retention_loop(pool: AsyncConnectionPool, interval_s: float | None = None) -> None:
    """后台清理循环（lifespan 启动）。任何异常只记日志，下一轮继续。"""
    interval = settings.retention_interval_s if interval_s is None else interval_s
    ttl = ttl_config()
    log.info(
        "retention loop every %ss; sessions %s, traces %s, images %s",
        interval, ttl["sessions"], ttl["traces"], ttl["images"],
    )
    while True:
        try:
            await purge_expired(
                pool,
                session_ttl=ttl["sessions"],
                log_path=settings.observability_log_path,
                trace_ttl=ttl["traces"],
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("retention purge failed")
        await asyncio.sleep(interval)


# ---------------- CLI ----------------


async def _with_pool(fn):
    pool = AsyncConnectionPool(
        settings.database_url,
        min_size=1,
        max_size=2,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await pool.open(wait=True, timeout=10)
    try:
        return await fn(pool)
    finally:
        await pool.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="数据保留：按分类 TTL 清理，或按 session_id 删除全部数据（票 48）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("purge", help="按 TTL 清理一轮并打印统计")
    p.add_argument("--session-hours", type=float, default=None, help="覆盖会话 TTL（小时）")
    d = sub.add_parser("delete", help="删除指定会话的全部数据")
    d.add_argument("session_id")
    sub.add_parser("ttl", help="打印当前 TTL 配置")
    ns = ap.parse_args(sys.argv[1:] if argv is None else argv)
    if ns.cmd == "ttl":
        for k, v in ttl_config().items():
            print(f"{k}: {v}")
        return 0
    if ns.cmd == "delete":
        counts = asyncio.run(_with_pool(lambda pool: delete_session_data(pool, ns.session_id)))
        print(f"{ns.session_id}: {counts}")
        return 0 if sum(counts.values()) else 1
    ttl = ttl_config()
    session_ttl = timedelta(hours=ns.session_hours) if ns.session_hours is not None else ttl["sessions"]
    stats = asyncio.run(
        _with_pool(
            lambda pool: purge_expired(
                pool,
                session_ttl=session_ttl,
                log_path=settings.observability_log_path,
                trace_ttl=ttl["traces"],
            )
        )
    )
    print(stats.as_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
