"""Postgres demo adapter; MemoryBackend implements the same contract for offline tests."""

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path

import yaml
from psycopg.rows import dict_row

from app.settings import CONFIG_DIR

from .protocol import (
    Conflict,
    NotFound,
    Order,
    ServiceOrder,
    ServiceOrderRequest,
    Shipment,
    Timeout,
    Unavailable,
)


def load_config(path: Path = CONFIG_DIR / "backends_mock.yaml") -> dict:
    return yaml.safe_load(path.read_text())


FAULT_ERRORS = {"timeout": Timeout, "unavailable": Unavailable, "conflict": Conflict}


class FaultInjection:
    def __init__(self, faults=()):
        self.faults = list(faults)

    def check(self, op, order_no):
        for fault in self.faults:
            if fault["op"] == op and fault["order_no"] == order_no and fault["mode"] in FAULT_ERRORS:
                raise FAULT_ERRORS[fault["mode"]]()

    def check_committed(self, op, order_no):
        """The write went through but its answer was lost: the case a retry must look up."""
        if any(
            f["op"] == op and f["order_no"] == order_no and f["mode"] == "created_then_timeout"
            for f in self.faults
        ):
            raise Timeout()


class MockBackend(FaultInjection):
    def __init__(self, pool, faults=()):
        super().__init__(faults)
        self.pool = pool

    async def _one(self, sql, params, model):
        async with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(sql, params)
            row = await cur.fetchone()
            if row is None:
                raise NotFound()
            for key in ("created_at", "updated_at"):
                if isinstance(row.get(key), datetime):
                    row[key] = row[key].isoformat()
            if "amount" in row and row["amount"] is not None:
                row["amount"] = str(row["amount"])
            return model.model_validate(row)

    async def get_order(self, order_no):
        self.check("get_order", order_no)
        return await self._one("select * from orders_mock where order_no=%s", (order_no,), Order)

    async def get_shipment(self, *, order_no=None, tracking_no=None):
        self.check("get_shipment", order_no or tracking_no)
        if tracking_no:
            return await self._one(
                "select * from shipments_mock where tracking_no=%s and (%s::text is null or order_no=%s)",
                (tracking_no, order_no, order_no),
                Shipment,
            )
        return await self._one(
            "select * from shipments_mock where order_no=%s order by updated_at desc limit 1",
            (order_no,),
            Shipment,
        )

    async def create_service_order(self, req: ServiceOrderRequest):
        self.check("create_service_order", req.order_no)
        order = await self.get_order(req.order_no)
        if order.sku != req.sku:
            raise Conflict()
        number = (
            "SRV-" + uuid.uuid5(uuid.NAMESPACE_URL, req.order_no + ":" + req.type).hex[:16].upper()
        )
        created = await self._one(
            """insert into service_orders_mock(service_order_no,order_no,sku,type,reason_code,status,eta_days,client_ref)
            values (%s,%s,%s,%s,%s,'created',3,%s)
            on conflict(order_no,type) do update set order_no=excluded.order_no returning *""",
            (number, req.order_no, req.sku, req.type, req.reason_code, req.client_ref),
            ServiceOrder,
        )
        self.check_committed("create_service_order", req.order_no)
        return created

    async def get_service_order(self, service_order_no):
        self.check("get_service_order", service_order_no)
        return await self._one(
            "select * from service_orders_mock where service_order_no=%s",
            (service_order_no,),
            ServiceOrder,
        )

    async def find_service_order(self, client_ref):
        try:
            return await self._one(
                "select * from service_orders_mock where client_ref=%s", (client_ref,), ServiceOrder
            )
        except NotFound:
            return None


class MemoryBackend(FaultInjection):
    def __init__(self, config=None):
        config = config if config is not None else load_config()
        super().__init__(config.get("faults", []))
        self.orders = {o["order_no"]: Order.model_validate(o) for o in config.get("orders", [])}
        self.shipments = {
            s["tracking_no"]: Shipment.model_validate(s) for s in config.get("shipments", [])
        }
        self.service_orders = {}
        self.create_calls = 0
        self._lock = asyncio.Lock()

    async def get_order(self, order_no):
        self.check("get_order", order_no)
        if order_no not in self.orders:
            raise NotFound()
        return self.orders[order_no].model_copy(deep=True)

    async def get_shipment(self, *, order_no=None, tracking_no=None):
        self.check("get_shipment", order_no or tracking_no)
        rows = [
            s
            for s in self.shipments.values()
            if (not order_no or s.order_no == order_no)
            and (not tracking_no or s.tracking_no == tracking_no)
        ]
        if not rows or not (order_no or tracking_no):
            raise NotFound()
        return max(rows, key=lambda s: s.updated_at).model_copy(deep=True)

    async def create_service_order(self, req):
        self.check("create_service_order", req.order_no)
        order = await self.get_order(req.order_no)
        if order.sku != req.sku:
            raise Conflict()
        async with self._lock:
            number = (
                "SRV-"
                + uuid.uuid5(uuid.NAMESPACE_URL, req.order_no + ":" + req.type).hex[:16].upper()
            )
            if number not in self.service_orders:
                self.create_calls += 1
                self.service_orders[number] = ServiceOrder(
                    service_order_no=number,
                    **req.model_dump(exclude={"evidence_ids"}),
                    status="created",
                    created_at=datetime.now(UTC).isoformat(),
                )
            created = self.service_orders[number].model_copy(deep=True)
        self.check_committed("create_service_order", req.order_no)
        return created

    async def get_service_order(self, service_order_no):
        self.check("get_service_order", service_order_no)
        if service_order_no not in self.service_orders:
            raise NotFound()
        return self.service_orders[service_order_no].model_copy(deep=True)

    async def find_service_order(self, client_ref):
        return next(
            (o.model_copy(deep=True) for o in self.service_orders.values() if o.client_ref == client_ref),
            None,
        )
