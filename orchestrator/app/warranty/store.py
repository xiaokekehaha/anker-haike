"""orders_mock / dealers 参考表的事务内幂等 seed 与加载；不删除非本次 seed 的记录。"""

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.warranty.service import ReferenceData

DDL = """
create table if not exists orders_mock (
    order_no text primary key,
    sku text not null,
    channel text not null,
    purchase_date date not null
);
create table if not exists dealers (
    name text primary key,
    region text not null,
    authorized boolean not null,
    warranty_note text not null default ''
);
"""


async def seed_reference(pool: AsyncConnectionPool, data: ReferenceData) -> dict[str, int]:
    async with pool.connection() as conn, conn.transaction():
        for statement in DDL.split(";"):
            if statement.strip():
                await conn.execute(statement)
        for order in data.orders:
            await conn.execute(
                "insert into orders_mock(order_no, sku, channel, purchase_date) "
                "values (%(order_no)s, %(sku)s, %(channel)s, %(purchase_date)s) "
                "on conflict (order_no) do update set sku=excluded.sku, "
                "channel=excluded.channel, purchase_date=excluded.purchase_date",
                order.model_dump(),
            )
        for dealer in data.dealers:
            await conn.execute(
                "insert into dealers(name, region, authorized, warranty_note) "
                "values (%(name)s, %(region)s, %(authorized)s, %(warranty_note)s) "
                "on conflict (name) do update set region=excluded.region, "
                "authorized=excluded.authorized, warranty_note=excluded.warranty_note",
                dealer.model_dump(),
            )
    return {"orders_mock": len(data.orders), "dealers": len(data.dealers)}


async def load_from_db(pool: AsyncConnectionPool) -> ReferenceData:
    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("select order_no,sku,channel,purchase_date from orders_mock order by order_no")
        orders = await cur.fetchall()
        await cur.execute("select * from dealers order by name")
        dealers = await cur.fetchall()
    return ReferenceData(version="db", orders=orders, dealers=dealers)
