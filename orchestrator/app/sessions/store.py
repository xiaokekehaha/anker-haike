"""会话存储：sessions 投影表 + session_events 事件日志（08 §2，03 §3.1）。

- append_event 先落库再由调用方发送；seq 由同会话事件的 max(seq)+1 得出，
  同会话 run 串行（active_run 守卫）保证不冲突。
- sessions 表只存可从 checkpoint 与事件日志重建的字段；票 07 提供重建命令。
- InMemorySessionStore 用于单元测试，行为与 Postgres 实现一致。
"""

from __future__ import annotations

import asyncio
import copy
import json
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from app.sessions.inputs import INPUT_DDL, MemoryInputStore, PostgresInputStore

DDL = """
create table if not exists sessions (
    session_id         text primary key,
    version            integer not null default 0,
    stage              text not null default 'intake',
    active_run_id      text,
    pending_input_json jsonb,
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now()
);
create table if not exists session_events (
    session_id  text not null,
    seq         integer not null,
    run_id      text not null,
    event_json  jsonb not null,
    created_at  timestamptz not null default now(),
    primary key (session_id, seq)
);
create index if not exists session_events_run_idx on session_events(session_id, run_id, seq);
alter table session_events drop constraint if exists session_events_session_id_fkey;

"""
# 注：session_events 不外键到 sessions——投影表可整行删除后由事件日志 + checkpoint 重建（08 §2，票 07）。


class SessionNotFound(LookupError):
    pass


@dataclass
class SessionRow:
    session_id: str
    version: int
    stage: str
    active_run_id: str | None
    pending_input: dict | None
    updated_at: datetime
    published_checkpoint_id: str | None = None


@dataclass
class EventRecord:
    seq: int
    run_id: str
    created_at: datetime
    event: dict[str, Any]


def _with_identity(event: dict[str, Any], seq: int, run_id: str) -> dict[str, Any]:
    """用 session_events 的列值覆盖事件 JSON 里的 seq / run_id。

    历史行的 event_json 可能缺这两个字段（早期集成测试残留），而调用方普遍直接读
    ev["seq"] / ev["run_id"]，缺字段会抛 KeyError 并中断整条重放 / 启动链路。列是权威值，
    JSON 只是副本，因此这里始终以列为准而不是仅在缺失时补。"""
    return {**event, "seq": seq, "run_id": run_id}


class SessionStore(Protocol):
    async def create_session(self) -> SessionRow: ...
    async def get_session(self, session_id: str) -> SessionRow: ...
    async def session_exists(self, session_id: str) -> bool: ...
    async def append_event(self, session_id: str, run_id: str, event: dict[str, Any]) -> int: ...
    async def list_events(
        self, session_id: str, *, run_id: str | None = None, after_seq: int = 0
    ) -> list[dict[str, Any]]: ...
    async def list_event_records(self, session_id: str) -> list[EventRecord]: ...
    async def list_session_ids(self) -> list[str]: ...
    async def list_active_runs(self) -> list[tuple[str, str]]: ...
    async def upsert_projection(
        self,
        session_id: str,
        *,
        version: int,
        stage: str,
        active_run_id: str | None,
        pending_input: dict | None,
        published_checkpoint_id: str | None = None,
    ) -> None: ...
    async def delete_projection(self, session_id: str) -> None: ...
    async def delete_session_data(self, session_id: str) -> dict[str, int]: ...


def new_session_id() -> str:
    return uuid.uuid4().hex


class PostgresSessionStore(PostgresInputStore):
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def setup(self) -> None:
        # 池按 PostgresSaver 要求设 prepare_threshold=0，多语句不能走预处理，逐条执行
        async with self._pool.connection() as conn:
            for stmt in (x.strip() for x in (DDL + INPUT_DDL).split(";")):
                if stmt:
                    await conn.execute(stmt)

    async def create_session(self) -> SessionRow:
        sid = new_session_id()
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("insert into sessions(session_id) values (%s) returning *", (sid,))
            return _row(await cur.fetchone())

    async def get_session(self, session_id: str) -> SessionRow:
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("select * from sessions where session_id = %s", (session_id,))
            row = await cur.fetchone()
        if row is None:
            raise SessionNotFound(session_id)
        return _row(row)

    @asynccontextmanager
    async def snapshot_view(self, session_id: str):
        """Pin the published pointer and event watermark while its checkpoint is read."""
        async with (
            self._pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as cur,
        ):
            await cur.execute("select * from sessions where session_id=%s for share", (session_id,))
            row = await cur.fetchone()
            if row is None:
                raise SessionNotFound(session_id)
            await cur.execute(
                "select seq,run_id,event_json,created_at from session_events where session_id=%s order by seq",
                (session_id,),
            )
            records = [
                EventRecord(
                    r["seq"],
                    r["run_id"],
                    r["created_at"],
                    _with_identity(r["event_json"], r["seq"], r["run_id"]),
                )
                for r in await cur.fetchall()
            ]
            yield _row(row), records

    async def append_event(self, session_id: str, run_id: str, event: dict[str, Any]) -> int:
        async with (
            self._pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as cur,
        ):
            await cur.execute(
                "select session_id from sessions where session_id=%s for update", (session_id,)
            )
            if event.get("event_id"):
                await cur.execute(
                    "select seq,event_json from session_events where session_id=%s and event_json->>'event_id'=%s",
                    (session_id, event["event_id"]),
                )
                previous = await cur.fetchone()
                if previous:
                    _check_event_payload(previous["event_json"], event)
                    return previous["seq"]
            await cur.execute(
                """insert into session_events(session_id, seq, run_id, event_json)
                   select %(sid)s, coalesce(max(seq), 0) + 1, %(rid)s, %(ev)s
                   from session_events where session_id = %(sid)s
                   returning seq""",
                {"sid": session_id, "rid": run_id, "ev": Jsonb(event)},
            )
            row = await cur.fetchone()
        return int(row["seq"])

    async def list_events(
        self, session_id: str, *, run_id: str | None = None, after_seq: int = 0
    ) -> list[dict[str, Any]]:
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """select seq, run_id, event_json from session_events
                   where session_id = %s and seq > %s and (%s::text is null or run_id = %s)
                   order by seq""",
                (session_id, after_seq, run_id, run_id),
            )
            rows = await cur.fetchall()
        return [_with_identity(r["event_json"], r["seq"], r["run_id"]) for r in rows]

    async def session_exists(self, session_id: str) -> bool:
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """select exists(select 1 from sessions where session_id = %(s)s)
                       or exists(select 1 from session_events where session_id = %(s)s) as ok""",
                {"s": session_id},
            )
            return bool((await cur.fetchone())["ok"])

    async def list_event_records(self, session_id: str) -> list[EventRecord]:
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """select seq, run_id, created_at, event_json from session_events
                   where session_id = %s order by seq""",
                (session_id,),
            )
            rows = await cur.fetchall()
        return [EventRecord(r["seq"], r["run_id"], r["created_at"], r["event_json"]) for r in rows]

    async def list_session_ids(self) -> list[str]:
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """select session_id from sessions
                   union select distinct session_id from session_events order by 1"""
            )
            return [r["session_id"] for r in await cur.fetchall()]

    async def list_active_runs(self) -> list[tuple[str, str]]:
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "select session_id, active_run_id from sessions where active_run_id is not null"
            )
            return [(r["session_id"], r["active_run_id"]) for r in await cur.fetchall()]

    async def upsert_projection(
        self,
        session_id: str,
        *,
        version: int,
        stage: str,
        active_run_id: str | None,
        pending_input: dict | None,
        published_checkpoint_id: str | None = None,
    ) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                """insert into sessions(session_id, version, stage, active_run_id, pending_input_json, published_checkpoint_id)
                   values (%s, %s, %s, %s, %s, %s)
                   on conflict (session_id) do update set
                       version = excluded.version, stage = excluded.stage,
                       active_run_id = excluded.active_run_id,
                       pending_input_json = excluded.pending_input_json,
                       published_checkpoint_id = coalesce(excluded.published_checkpoint_id, sessions.published_checkpoint_id), updated_at = now()""",
                (
                    session_id,
                    version,
                    stage,
                    active_run_id,
                    Jsonb(pending_input) if pending_input is not None else None,
                    published_checkpoint_id,
                ),
            )

    async def delete_projection(self, session_id: str) -> None:
        async with self._pool.connection() as conn:
            await conn.execute("delete from sessions where session_id = %s", (session_id,))

    async def delete_session_data(self, session_id: str) -> dict[str, int]:
        """票 48：本 store 三张表按会话删除；checkpoint 与图片由 app.retention.delete_session_data 统一处理。"""
        counts: dict[str, int] = {}
        async with self._pool.connection() as conn, conn.transaction():
            await conn.execute(
                "select session_id from sessions where session_id=%s for update", (session_id,)
            )
            for table in ("conversation_summaries", "session_inputs", "session_events", "sessions"):
                cur = await conn.execute(
                    f"delete from {table} where session_id = %s", (session_id,)
                )
                counts[table] = cur.rowcount or 0
        return counts


def _row(r: dict) -> SessionRow:
    return SessionRow(
        session_id=r["session_id"],
        version=int(r["version"]),
        stage=r["stage"],
        active_run_id=r["active_run_id"],
        pending_input=r["pending_input_json"],
        updated_at=r["updated_at"],
        published_checkpoint_id=r.get("published_checkpoint_id"),
    )


@dataclass
class _MemSession:
    row: SessionRow | None
    events: list[EventRecord] = field(default_factory=list)


class InMemorySessionStore(MemoryInputStore):
    """与 PostgresSessionStore 同语义的内存实现，供单元测试使用。"""

    def __init__(self) -> None:
        self._sessions: dict[str, _MemSession] = {}
        self._lock = asyncio.Lock()
        self._inputs: dict[tuple[str, str], dict] = {}

    async def create_session(self) -> SessionRow:
        sid = new_session_id()
        row = SessionRow(sid, 0, "intake", None, None, datetime.now(UTC))
        self._sessions[sid] = _MemSession(row)
        return row

    async def get_session(self, session_id: str) -> SessionRow:
        row = self._get(session_id).row
        if row is None:
            raise SessionNotFound(session_id)
        return row

    async def session_exists(self, session_id: str) -> bool:
        return session_id in self._sessions

    @asynccontextmanager
    async def snapshot_view(self, session_id: str):
        async with self._lock:
            mem = self._get(session_id)
            if mem.row is None:
                raise SessionNotFound(session_id)
            yield copy.deepcopy(mem.row), copy.deepcopy(mem.events)

    async def append_event(self, session_id: str, run_id: str, event: dict[str, Any]) -> int:
        async with self._lock:
            s = self._get(session_id)
            if event.get("event_id"):
                old = next(
                    (r for r in s.events if r.event.get("event_id") == event["event_id"]), None
                )
                if old:
                    _check_event_payload(old.event, event)
                    return old.seq
            seq = len(s.events) + 1
            # 与 Postgres 一致：存 JSON 可序列化副本
            s.events.append(
                EventRecord(seq, run_id, datetime.now(UTC), json.loads(json.dumps(event)))
            )
            return seq

    async def list_events(
        self, session_id: str, *, run_id: str | None = None, after_seq: int = 0
    ) -> list[dict[str, Any]]:
        s = self._get(session_id)
        return [
            _with_identity(r.event, r.seq, r.run_id)
            for r in s.events[after_seq:]
            if run_id is None or r.run_id == run_id
        ]

    async def list_event_records(self, session_id: str) -> list[EventRecord]:
        return list(self._get(session_id).events)

    async def list_session_ids(self) -> list[str]:
        return sorted(self._sessions)

    async def list_active_runs(self) -> list[tuple[str, str]]:
        return [
            (sid, s.row.active_run_id)
            for sid, s in self._sessions.items()
            if s.row is not None and s.row.active_run_id
        ]

    async def upsert_projection(
        self,
        session_id: str,
        *,
        version: int,
        stage: str,
        active_run_id: str | None,
        pending_input: dict | None,
        published_checkpoint_id: str | None = None,
    ) -> None:
        s = self._sessions.setdefault(session_id, _MemSession(None))
        s.row = SessionRow(
            session_id,
            version,
            stage,
            active_run_id,
            pending_input,
            datetime.now(UTC),
            published_checkpoint_id or (s.row.published_checkpoint_id if s.row else None),
        )

    async def delete_projection(self, session_id: str) -> None:
        s = self._sessions.get(session_id)
        if s is not None:
            s.row = None
            if not s.events:
                del self._sessions[session_id]

    async def delete_session_data(self, session_id: str) -> dict[str, int]:
        async with self._lock:
            mem = self._sessions.pop(session_id, None)
            getattr(self, "_summary_cache", {}).pop(session_id, None)
            inputs = [k for k in self._inputs if k[0] == session_id]
            for k in inputs:
                self._inputs.pop(k, None)
        return {
            "sessions": 1 if mem and mem.row else 0,
            "session_events": len(mem.events) if mem else 0,
            "session_inputs": len(inputs),
        }

    def _get(self, session_id: str) -> _MemSession:
        try:
            return self._sessions[session_id]
        except KeyError:
            raise SessionNotFound(session_id) from None


def _check_event_payload(previous: dict, event: dict) -> None:
    meta = {"seq", "run_id", "recorded_at"}
    if {k: v for k, v in previous.items() if k not in meta} != {
        k: v for k, v in event.items() if k not in meta
    }:
        raise RuntimeError("event_id_payload_conflict")
