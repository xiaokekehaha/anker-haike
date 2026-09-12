"""plans 表：建表与可重复 seed（03 §3.1）。运行时读 L4 缓存，不查表。"""

from __future__ import annotations

from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from app.plans.library import PlanLibrary

DDL = """
create table if not exists plans (
    plan_id    text not null,
    version    integer not null,
    fault      text not null,
    applies_to jsonb not null,
    steps      jsonb not null,
    updated_at timestamptz not null default now(),
    primary key (plan_id, version)
);
"""

UPSERT = """
insert into plans(plan_id, version, fault, applies_to, steps, updated_at)
values (%(plan_id)s, %(version)s, %(fault)s, %(applies_to)s, %(steps)s, now())
on conflict (plan_id, version) do update set
    fault = excluded.fault, applies_to = excluded.applies_to, steps = excluded.steps, updated_at = now()
"""


async def setup(pool: AsyncConnectionPool) -> None:
    async with pool.connection() as conn:
        for stmt in (x.strip() for x in DDL.split(";")):
            if stmt:
                await conn.execute(stmt)


async def seed_plans(pool: AsyncConnectionPool, library: PlanLibrary) -> dict[str, int]:
    await setup(pool)
    async with pool.connection() as conn:
        for p in library.plans:
            await conn.execute(
                UPSERT,
                {
                    "plan_id": p.plan_id,
                    "version": p.version,
                    "fault": p.fault,
                    "applies_to": Jsonb(p.applies_to.model_dump()),
                    "steps": Jsonb([s.model_dump() for s in p.steps]),
                },
            )
        cur = await conn.execute("select count(*) from plans")
        total = (await cur.fetchone())["count"]
    return {"upserted": len(library.plans), "total": int(total)}
