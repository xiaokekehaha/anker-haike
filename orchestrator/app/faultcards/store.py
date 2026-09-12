"""sku_fault_cards(sku, card_text, doc_version, updated_at)（03 §3.1）：seed 与运行时读取（运行时以 L4 为准）。"""

from __future__ import annotations

from psycopg_pool import AsyncConnectionPool

from app.faultcards.library import FaultCardLibrary

DDL = """
create table if not exists sku_fault_cards (
    sku         text primary key,
    card_text   text not null,
    doc_version text not null,
    updated_at  timestamptz not null default now()
);
"""
UPSERT = """
insert into sku_fault_cards(sku, card_text, doc_version, updated_at) values (%s, %s, %s, now())
on conflict (sku) do update set card_text = excluded.card_text, doc_version = excluded.doc_version, updated_at = now()
"""


async def setup(pool: AsyncConnectionPool) -> None:
    async with pool.connection() as conn:
        for stmt in (x.strip() for x in DDL.split(";")):
            if stmt:
                await conn.execute(stmt)


async def seed_fault_cards(pool: AsyncConnectionPool, library: FaultCardLibrary) -> dict[str, int]:
    await setup(pool)
    async with pool.connection() as conn:
        for c in library.cards:
            await conn.execute(UPSERT, (c.key, c.render(), c.doc_version))
        cur = await conn.execute("select count(*) from sku_fault_cards")
        total = (await cur.fetchone())["count"]
    return {"upserted": len(library.cards), "total": int(total)}
