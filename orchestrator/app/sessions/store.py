"""会话存储：sessions 投影表 + session_events 事件日志（08 §2，03 §3.1）。

- append_event 先落库再由调用方发送；seq 由同会话事件的 max(seq)+1 得出，
  同会话 run 串行（active_run 守卫）保证不冲突。
- sessions 表只存可从 checkpoint 与事件日志重建的字段；票 07 提供重建命令。
- InMemorySessionStore 用于单元测试，行为与 Postgres 实现一致。
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

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
    session_id  text not null references sessions(session_id) on delete cascade,
    seq         integer not null,
    run_id      text not null,
    event_json  jsonb not null,
    created_at  timestamptz not null default now(),
    primary key (session_id, seq)
);
create index if not exists session_events_run_idx on session_events(session_id, run_id, seq);
"""


class SessionNotFound(LookupError):
    pass


class ActiveRunConflict(RuntimeError):
    """同一会话已有 active run：不允许并发第二个 run（票 05 验收项 5）。"""

    def __init__(self, session_id: str, active_run_id: str) -> None:
        super().__init__(f"session {session_id} has active run {active_run_id}")
        self.session_id = session_id
        self.active_run_id = active_run_id


@dataclass
class SessionRow:
    session_id: str
    version: int
    stage: str
    active_run_id: str | None
    pending_input: dict | None
    updated_at: datetime


class SessionStore(Protocol):
    async def create_session(self) -> SessionRow: ...
    async def get_session(self, session_id: str) -> SessionRow: ...
    async def try_start_run(self, session_id: str, run_id: str) -> SessionRow: ...
    async def finish_run(
        self, session_id: str, run_id: str, *, stage: str | None = None
    ) -> int: ...
    async def append_event(self, session_id: str, run_id: str, event: dict[str, Any]) -> int: ...
    async def list_events(
        self, session_id: str, *, run_id: str | None = None, after_seq: int = 0
    ) -> list[dict[str, Any]]: ...


def new_session_id() -> str:
    return uuid.uuid4().hex


class PostgresSessionStore:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def setup(self) -> None:
        # 池按 PostgresSaver 要求设 prepare_threshold=0，多语句不能走预处理，逐条执行
        async with self._pool.connection() as conn:
            for stmt in (x.strip() for x in DDL.split(";")):
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

    async def try_start_run(self, session_id: str, run_id: str) -> SessionRow:
        """原子占用 active_run_id；已被占用则抛 ActiveRunConflict。"""
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """update sessions set active_run_id = %s, updated_at = now()
                   where session_id = %s and active_run_id is null returning *""",
                (run_id, session_id),
            )
            row = await cur.fetchone()
            if row is not None:
                return _row(row)
            await cur.execute(
                "select active_run_id from sessions where session_id = %s", (session_id,)
            )
            cur_row = await cur.fetchone()
        if cur_row is None:
            raise SessionNotFound(session_id)
        raise ActiveRunConflict(session_id, cur_row["active_run_id"])

    async def finish_run(self, session_id: str, run_id: str, *, stage: str | None = None) -> int:
        """释放 active run 并把 version +1（票 05 粒度：每个 run 一次提交；票 07 细化到 checkpoint）。"""
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """update sessions
                   set active_run_id = null, version = version + 1,
                       stage = coalesce(%s, stage), updated_at = now()
                   where session_id = %s and active_run_id = %s returning version""",
                (stage, session_id, run_id),
            )
            row = await cur.fetchone()
        if row is None:
            raise SessionNotFound(session_id)
        return int(row["version"])

    async def append_event(self, session_id: str, run_id: str, event: dict[str, Any]) -> int:
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
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
                """select event_json from session_events
                   where session_id = %s and seq > %s and (%s::text is null or run_id = %s)
                   order by seq""",
                (session_id, after_seq, run_id, run_id),
            )
            rows = await cur.fetchall()
        return [r["event_json"] for r in rows]


def _row(r: dict) -> SessionRow:
    return SessionRow(
        session_id=r["session_id"],
        version=int(r["version"]),
        stage=r["stage"],
        active_run_id=r["active_run_id"],
        pending_input=r["pending_input_json"],
        updated_at=r["updated_at"],
    )


@dataclass
class _MemSession:
    row: SessionRow
    events: list[dict[str, Any]] = field(default_factory=list)


class InMemorySessionStore:
    """与 PostgresSessionStore 同语义的内存实现，供单元测试使用。"""

    def __init__(self) -> None:
        self._sessions: dict[str, _MemSession] = {}
        self._lock = asyncio.Lock()

    async def create_session(self) -> SessionRow:
        sid = new_session_id()
        row = SessionRow(sid, 0, "intake", None, None, datetime.now(UTC))
        self._sessions[sid] = _MemSession(row)
        return row

    async def get_session(self, session_id: str) -> SessionRow:
        return self._get(session_id).row

    async def try_start_run(self, session_id: str, run_id: str) -> SessionRow:
        async with self._lock:
            s = self._get(session_id)
            if s.row.active_run_id is not None:
                raise ActiveRunConflict(session_id, s.row.active_run_id)
            s.row.active_run_id = run_id
            return s.row

    async def finish_run(self, session_id: str, run_id: str, *, stage: str | None = None) -> int:
        async with self._lock:
            s = self._get(session_id)
            if s.row.active_run_id != run_id:
                raise SessionNotFound(session_id)
            s.row.active_run_id = None
            s.row.version += 1
            if stage:
                s.row.stage = stage
            return s.row.version

    async def append_event(self, session_id: str, run_id: str, event: dict[str, Any]) -> int:
        async with self._lock:
            s = self._get(session_id)
            seq = len(s.events) + 1
            # 与 Postgres 一致：存 JSON 可序列化副本
            s.events.append(json.loads(json.dumps(event)))
            return seq

    async def list_events(
        self, session_id: str, *, run_id: str | None = None, after_seq: int = 0
    ) -> list[dict[str, Any]]:
        s = self._get(session_id)
        return [e for e in s.events[after_seq:] if run_id is None or e.get("run_id") == run_id]

    def _get(self, session_id: str) -> _MemSession:
        try:
            return self._sessions[session_id]
        except KeyError:
            raise SessionNotFound(session_id) from None
