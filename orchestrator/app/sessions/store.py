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
    session_id  text not null,
    seq         integer not null,
    run_id      text not null,
    event_json  jsonb not null,
    created_at  timestamptz not null default now(),
    primary key (session_id, seq)
);
create index if not exists session_events_run_idx on session_events(session_id, run_id, seq);
alter table session_events drop constraint if exists session_events_session_id_fkey;
create table if not exists session_actions (
    session_id  text not null,
    action_id   text not null,
    result_json jsonb,
    created_at  timestamptz not null default now(),
    primary key (session_id, action_id)
);
"""
# 注：session_events 不外键到 sessions——投影表可整行删除后由事件日志 + checkpoint 重建（08 §2，票 07）。


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


@dataclass
class EventRecord:
    seq: int
    run_id: str
    created_at: datetime
    event: dict[str, Any]


class SessionStore(Protocol):
    async def create_session(self) -> SessionRow: ...
    async def get_session(self, session_id: str) -> SessionRow: ...
    async def session_exists(self, session_id: str) -> bool: ...
    async def try_start_run(self, session_id: str, run_id: str) -> SessionRow: ...
    async def finish_run(
        self, session_id: str, run_id: str, *, version: int, stage: str | None = None
    ) -> int: ...
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
    ) -> None: ...
    async def delete_projection(self, session_id: str) -> None: ...
    # 动作幂等（08 §4 步骤 2、5；票 22）：占位 → 执行 → 回填
    async def try_insert_action(
        self, session_id: str, action_id: str, placeholder: dict
    ) -> bool: ...
    async def get_action(self, session_id: str, action_id: str) -> dict | None: ...
    async def set_action_result(self, session_id: str, action_id: str, result: dict) -> None: ...
    async def delete_action(self, session_id: str, action_id: str) -> None: ...


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

    async def finish_run(
        self, session_id: str, run_id: str, *, version: int, stage: str | None = None
    ) -> int:
        """释放 active run，并把 checkpoint 推导出的 version 写入投影（08 §2：每次 checkpoint 提交 +1）。"""
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """update sessions
                   set active_run_id = null, version = %s,
                       stage = coalesce(%s, stage), updated_at = now()
                   where session_id = %s and active_run_id = %s returning version""",
                (version, stage, session_id, run_id),
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
    ) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                """insert into sessions(session_id, version, stage, active_run_id, pending_input_json)
                   values (%s, %s, %s, %s, %s)
                   on conflict (session_id) do update set
                       version = excluded.version, stage = excluded.stage,
                       active_run_id = excluded.active_run_id,
                       pending_input_json = excluded.pending_input_json, updated_at = now()""",
                (
                    session_id,
                    version,
                    stage,
                    active_run_id,
                    Jsonb(pending_input) if pending_input is not None else None,
                ),
            )

    async def delete_projection(self, session_id: str) -> None:
        async with self._pool.connection() as conn:
            await conn.execute("delete from sessions where session_id = %s", (session_id,))

    async def try_insert_action(self, session_id: str, action_id: str, placeholder: dict) -> bool:
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """insert into session_actions(session_id, action_id, result_json)
                   values (%s, %s, %s) on conflict do nothing returning action_id""",
                (session_id, action_id, Jsonb(placeholder)),
            )
            return (await cur.fetchone()) is not None

    async def get_action(self, session_id: str, action_id: str) -> dict | None:
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "select result_json from session_actions where session_id = %s and action_id = %s",
                (session_id, action_id),
            )
            row = await cur.fetchone()
        return None if row is None else row["result_json"]

    async def set_action_result(self, session_id: str, action_id: str, result: dict) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                "update session_actions set result_json = %s where session_id = %s and action_id = %s",
                (Jsonb(result), session_id, action_id),
            )

    async def delete_action(self, session_id: str, action_id: str) -> None:
        """动作未被应用（run 出错 / 取消）时撤销占位，让同一 action_id 的重试真正执行（票 23）。"""
        async with self._pool.connection() as conn:
            await conn.execute(
                "delete from session_actions where session_id = %s and action_id = %s",
                (session_id, action_id),
            )


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
    row: SessionRow | None
    events: list[EventRecord] = field(default_factory=list)


class InMemorySessionStore:
    """与 PostgresSessionStore 同语义的内存实现，供单元测试使用。"""

    def __init__(self) -> None:
        self._sessions: dict[str, _MemSession] = {}
        self._lock = asyncio.Lock()
        self._actions: dict[tuple[str, str], dict | None] = {}

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

    async def try_start_run(self, session_id: str, run_id: str) -> SessionRow:
        async with self._lock:
            s = self._get(session_id)
            if s.row is None:
                raise SessionNotFound(session_id)
            if s.row.active_run_id is not None:
                raise ActiveRunConflict(session_id, s.row.active_run_id)
            s.row.active_run_id = run_id
            return s.row

    async def finish_run(
        self, session_id: str, run_id: str, *, version: int, stage: str | None = None
    ) -> int:
        async with self._lock:
            s = self._get(session_id)
            if s.row is None or s.row.active_run_id != run_id:
                raise SessionNotFound(session_id)
            s.row.active_run_id = None
            s.row.version = version
            if stage:
                s.row.stage = stage
            return s.row.version

    async def append_event(self, session_id: str, run_id: str, event: dict[str, Any]) -> int:
        async with self._lock:
            s = self._get(session_id)
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
        return [r.event for r in s.events[after_seq:] if run_id is None or r.run_id == run_id]

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
    ) -> None:
        s = self._sessions.setdefault(session_id, _MemSession(None))
        s.row = SessionRow(
            session_id, version, stage, active_run_id, pending_input, datetime.now(UTC)
        )

    async def delete_projection(self, session_id: str) -> None:
        s = self._sessions.get(session_id)
        if s is not None:
            s.row = None
            if not s.events:
                del self._sessions[session_id]

    async def try_insert_action(self, session_id: str, action_id: str, placeholder: dict) -> bool:
        async with self._lock:
            if (session_id, action_id) in self._actions:
                return False
            self._actions[(session_id, action_id)] = json.loads(json.dumps(placeholder))
            return True

    async def get_action(self, session_id: str, action_id: str) -> dict | None:
        return self._actions.get((session_id, action_id))

    async def set_action_result(self, session_id: str, action_id: str, result: dict) -> None:
        self._actions[(session_id, action_id)] = json.loads(json.dumps(result))

    async def delete_action(self, session_id: str, action_id: str) -> None:
        self._actions.pop((session_id, action_id), None)

    def _get(self, session_id: str) -> _MemSession:
        try:
            return self._sessions[session_id]
        except KeyError:
            raise SessionNotFound(session_id) from None
