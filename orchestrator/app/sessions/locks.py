"""会话锁（08 §4 步骤 1）：同会话动作串行。Postgres advisory lock（跨进程）与内存实现（测试）。"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol

from psycopg_pool import AsyncConnectionPool

log = logging.getLogger("sessions.locks")

DEFAULT_LOCK_TIMEOUT_S = 30.0


class LockTimeout(TimeoutError):
    def __init__(self, session_id: str, timeout_s: float) -> None:
        super().__init__(f"session {session_id} lock not acquired within {timeout_s}s")
        self.session_id = session_id
        self.timeout_s = timeout_s


class SessionLock(Protocol):
    def hold(self, session_id: str, *, timeout_s: float) -> AsyncIterator[None]: ...


class PostgresSessionLock:
    """独占一条连接持有 pg_advisory_lock(hashtext(session_id))，释放时归还连接。"""

    def __init__(self, pool: AsyncConnectionPool, *, poll_s: float = 0.05) -> None:
        self._pool = pool
        self._poll_s = poll_s

    @asynccontextmanager
    async def hold(self, session_id: str, *, timeout_s: float = DEFAULT_LOCK_TIMEOUT_S):
        conn = await self._pool.getconn(timeout=timeout_s)
        acquired = False
        try:
            deadline = time.monotonic() + timeout_s
            while True:
                cur = await conn.execute("select pg_try_advisory_lock(hashtext(%s))", (session_id,))
                row = await cur.fetchone()
                got = row[0] if isinstance(row, tuple) else row["pg_try_advisory_lock"]
                if got:
                    acquired = True
                    break
                if time.monotonic() >= deadline:
                    raise LockTimeout(session_id, timeout_s)
                await asyncio.sleep(self._poll_s)
            yield
        finally:
            if acquired:
                try:
                    await conn.execute("select pg_advisory_unlock(hashtext(%s))", (session_id,))
                except Exception:
                    log.exception("advisory unlock failed session=%s", session_id)
            await self._pool.putconn(conn)


class InMemorySessionLock:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    @asynccontextmanager
    async def hold(self, session_id: str, *, timeout_s: float = DEFAULT_LOCK_TIMEOUT_S):
        lock = self._locks.setdefault(session_id, asyncio.Lock())
        try:
            await asyncio.wait_for(lock.acquire(), timeout=timeout_s)
        except TimeoutError:
            raise LockTimeout(session_id, timeout_s) from None
        try:
            yield
        finally:
            lock.release()
