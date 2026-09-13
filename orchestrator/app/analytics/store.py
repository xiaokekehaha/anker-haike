"""analytics 事实的写入存储。

PostgresAnalyticsStore 按 kind 分组批量写（executemany），upsert 键见 schema.CONFLICT_KEY。
InMemoryAnalyticsStore 供单测与「数据库不可用」时的降级（只留在内存，进程结束即丢，不影响业务）。
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from app.analytics.schema import (
    CONFLICT_KEY,
    INSERT_ONLY,
    KEEP_ON_CONFLICT,
    ROW_TYPES,
    SCHEMA,
    TABLE_OF,
    Row,
)

log = logging.getLogger("analytics.store")

# (kind, row) 的写操作
Op = tuple[str, Row]


class AnalyticsStore(Protocol):
    async def write(self, ops: list[Op]) -> None: ...


def _sql(kind: str) -> str:
    """按 kind 生成 insert / upsert 语句；列顺序即 dataclass 字段顺序。"""
    row_type = ROW_TYPES[kind]
    cols = row_type.columns()
    placeholders = ", ".join(["%s"] * len(cols))
    stmt = (
        f"insert into {SCHEMA}.{TABLE_OF[kind]} ({', '.join(cols)}) values ({placeholders})"
    )
    key = CONFLICT_KEY.get(kind)
    if key is None:
        return stmt
    if kind in INSERT_ONLY:
        return f"{stmt} on conflict ({key}) do nothing"
    keep = KEEP_ON_CONFLICT.get(kind, set()) | {c.strip() for c in key.split(",")}
    updates = ", ".join(f"{c} = excluded.{c}" for c in cols if c not in keep)
    if not updates:
        return f"{stmt} on conflict ({key}) do nothing"
    return f"{stmt} on conflict ({key}) do update set {updates}"


_STATEMENTS = {kind: _sql(kind) for kind in ROW_TYPES}


def _adapt(value: Any) -> Any:
    """dict 列走 jsonb；其余交给 psycopg（list[str] → text[]）。"""
    return Jsonb(value) if isinstance(value, dict) else value


class PostgresAnalyticsStore:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def write(self, ops: list[Op]) -> None:
        grouped: dict[str, list[tuple[Any, ...]]] = {}
        for kind, row in ops:
            grouped.setdefault(kind, []).append(tuple(_adapt(v) for v in row.values()))
        async with self._pool.connection() as conn, conn.cursor() as cur:
            for kind, batch in grouped.items():
                await cur.executemany(_STATEMENTS[kind], batch)


class InMemoryAnalyticsStore:
    """按 kind 保存行；upsert 键相同的行覆盖，与 Postgres 语义一致。"""

    def __init__(self) -> None:
        self.rows: dict[str, list[Row]] = {kind: [] for kind in ROW_TYPES}

    async def write(self, ops: list[Op]) -> None:
        for kind, row in ops:
            key = CONFLICT_KEY.get(kind)
            bucket = self.rows.setdefault(kind, [])
            if key is None:
                bucket.append(row)
                continue
            names = [c.strip() for c in key.split(",")]
            ident = tuple(getattr(row, n) for n in names)
            for i, existing in enumerate(bucket):
                if tuple(getattr(existing, n) for n in names) == ident:
                    if kind in INSERT_ONLY:
                        break  # 冲突即丢弃
                    keep = KEEP_ON_CONFLICT.get(kind, set())
                    for col in row.columns():
                        if col not in keep:
                            setattr(existing, col, getattr(row, col))
                    break
            else:
                bucket.append(row)

    def of(self, kind: str) -> list[Row]:
        return self.rows.get(kind, [])
