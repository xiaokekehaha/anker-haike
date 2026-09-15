from pathlib import Path

from psycopg.types.json import Jsonb

from .mock import load_config
from .protocol import Order, Shipment


async def seed_backends(pool, path: Path):
    config = load_config(path)
    orders = [Order.model_validate(o) for o in config["orders"]]
    shipments = [Shipment.model_validate(s) for s in config["shipments"]]
    async with pool.connection() as conn, conn.transaction():
        for order in orders:
            await conn.execute(
                """insert into orders_mock(order_no,sku,channel,purchase_date,region_purchase,platform,amount,currency)
                values (%(order_no)s,%(sku)s,%(channel)s,%(purchase_date)s,%(region_purchase)s,%(platform)s,%(amount)s,%(currency)s)
                on conflict(order_no) do update set sku=excluded.sku,channel=excluded.channel,purchase_date=excluded.purchase_date,region_purchase=excluded.region_purchase,platform=excluded.platform,amount=excluded.amount,currency=excluded.currency""",
                order.model_dump(),
            )
        for shipment in shipments:
            values = shipment.model_dump()
            values["events"] = Jsonb(values["events"])
            await conn.execute(
                """insert into shipments_mock(tracking_no,order_no,carrier,status,events,updated_at)
                values (%(tracking_no)s,%(order_no)s,%(carrier)s,%(status)s,%(events)s,%(updated_at)s)
                on conflict(tracking_no) do update set status=excluded.status,events=excluded.events,updated_at=excluded.updated_at""",
                values,
            )
    return {"orders": len(orders), "shipments": len(shipments)}
