"""products 表：建表与可重复执行的 seed（upsert），并支持从表加载 L4 缓存。"""

from __future__ import annotations

from psycopg_pool import AsyncConnectionPool

from app.catalog.service import CategorySpec, ProductCatalog, ProductRecord

DDL = """
create table if not exists products (
    sku        text primary key,
    name       text not null,
    aliases    text[] not null default '{}',
    category   text not null,
    image_url  text,
    in_scope   boolean not null default true,
    updated_at timestamptz not null default now()
);
create table if not exists catalog_meta (
    key   text primary key,
    value text not null
);
"""

UPSERT = """
insert into products(sku, name, aliases, category, image_url, in_scope, updated_at)
values (%(sku)s, %(name)s, %(aliases)s, %(category)s, %(image_url)s, %(in_scope)s, now())
on conflict (sku) do update set
    name = excluded.name, aliases = excluded.aliases, category = excluded.category,
    image_url = excluded.image_url, in_scope = excluded.in_scope, updated_at = now()
"""


async def setup(pool: AsyncConnectionPool) -> None:
    async with pool.connection() as conn:
        for stmt in (x.strip() for x in DDL.split(";")):
            if stmt:
                await conn.execute(stmt)


async def seed_products(
    pool: AsyncConnectionPool, catalog: ProductCatalog, *, prune: bool = True
) -> dict[str, int]:
    """把内存目录写入 products 表；重复执行结果一致。prune 删除配置里已不存在的 SKU。"""
    await setup(pool)
    async with pool.connection() as conn:
        for p in catalog.products:
            await conn.execute(UPSERT, p.as_row())
        removed = 0
        if prune:
            cur = await conn.execute(
                "delete from products where not (sku = any(%s))",
                ([p.sku for p in catalog.products],),
            )
            removed = cur.rowcount or 0
        await conn.execute(
            "insert into catalog_meta(key, value) values ('products_version', %s) "
            "on conflict (key) do update set value = excluded.value",
            (catalog.version,),
        )
        cur = await conn.execute("select count(*) from products")
        total = (await cur.fetchone())["count"]
    return {"upserted": len(catalog.products), "removed": removed, "total": int(total)}


async def load_from_db(
    pool: AsyncConnectionPool, categories: dict[str, CategorySpec]
) -> ProductCatalog:
    async with pool.connection() as conn:
        cur = await conn.execute("select * from products order by sku")
        rows = await cur.fetchall()
        cur = await conn.execute("select value from catalog_meta where key = 'products_version'")
        meta = await cur.fetchone()
    products = [
        ProductRecord(
            sku=r["sku"],
            name=r["name"],
            category=r["category"],
            in_scope=bool(r["in_scope"]),
            aliases=tuple(r["aliases"] or ()),
            image=r["image_url"],
        )
        for r in rows
    ]
    return ProductCatalog(meta["value"] if meta else "db", products, categories)
