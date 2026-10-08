"""售后业务后端：订单与物流只读主办方数据（data/official），服务单写库。

主办方不提供订单 / 工单接口，「创建换货单 / 退款单」只是把信息交给工具、再转人工；
所以服务单只有 submitted 起点，没有自动发货或退款。PostgresBackend 与 MemoryBackend
共享同一份订单视图，只在服务单存储上不同。
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.official.models import OfficialData, Order, pn_of

from .protocol import (
    Conflict,
    NotFound,
    ServiceOrder,
    ServiceOrderRequest,
    Timeout,
    Unavailable,
)

FAULT_ERRORS = {"timeout": Timeout, "unavailable": Unavailable, "conflict": Conflict}


class FaultInjection:
    """测试用故障注入：faults 由调用方传入，不来自配置文件。"""

    def __init__(self, faults=()):
        self.faults = list(faults)

    def check(self, op, key):
        for fault in self.faults:
            if fault["op"] == op and fault["key"] == key and fault["mode"] in FAULT_ERRORS:
                raise FAULT_ERRORS[fault["mode"]]()

    def check_committed(self, op, key):
        """The write went through but its answer was lost: the case a retry must look up."""
        if any(
            f["op"] == op and f["key"] == key and f["mode"] == "created_then_timeout"
            for f in self.faults
        ):
            raise Timeout()


def service_order_no(client_ref: str) -> str:
    return "SRV-" + uuid.uuid5(uuid.NAMESPACE_URL, client_ref).hex[:12].upper()


class OrderBook(FaultInjection):
    def __init__(self, data: OfficialData | None = None, faults=()):
        super().__init__(faults)
        data = data or OfficialData()
        self.orders = {o.order_no.casefold(): o for o in data.orders}

    async def get_order(self, order_no: str) -> Order:
        self.check("get_order", order_no)
        order = self.orders.get(order_no.strip().casefold())
        if order is None:
            raise NotFound()
        return order

    async def find_order_by_tracking(self, tracking_no: str) -> Order:
        self.check("get_order", tracking_no)
        wanted = tracking_no.replace(" ", "").casefold()
        for order in self.orders.values():
            if any((p.tracking_no or "").casefold() == wanted for p in order.packages):
                return order
        raise NotFound()

    async def _validate(self, req: ServiceOrderRequest) -> None:
        self.check("create_service_order", req.order_no or req.client_ref)
        if req.order_no:
            order = await self.get_order(req.order_no)
            # 产品目录以 PN 为键，订单行是完整 SKU。
            if req.sku and pn_of(req.sku) not in {pn_of(line.sku) for line in order.lines}:
                raise Conflict()


class PostgresBackend(OrderBook):
    def __init__(self, pool, data: OfficialData | None = None, faults=()):
        super().__init__(data, faults)
        self.pool = pool

    async def _one(self, sql, params):
        async with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(sql, params)
            row = await cur.fetchone()
        if row is None:
            return None
        row["created_at"] = row["created_at"].isoformat()
        return ServiceOrder.model_validate(row)

    async def create_service_order(self, req: ServiceOrderRequest) -> ServiceOrder:
        await self._validate(req)
        created = await self._one(
            """insert into service_orders(service_order_no,type,order_no,sku,reason,evidence,client_ref)
            values (%s,%s,%s,%s,%s,%s,%s)
            on conflict(client_ref) do update set client_ref=excluded.client_ref returning *""",
            (
                service_order_no(req.client_ref), req.type, req.order_no, req.sku,
                req.reason, Jsonb(req.evidence), req.client_ref,
            ),
        )
        self.check_committed("create_service_order", req.order_no or req.client_ref)
        return created

    async def get_service_order(self, service_order_no: str) -> ServiceOrder:
        self.check("get_service_order", service_order_no)
        found = await self._one(
            "select * from service_orders where service_order_no=%s", (service_order_no,)
        )
        if found is None:
            raise NotFound()
        return found

    async def find_service_order(self, client_ref: str) -> ServiceOrder | None:
        return await self._one("select * from service_orders where client_ref=%s", (client_ref,))


class MemoryBackend(OrderBook):
    def __init__(self, data: OfficialData | None = None, faults=()):
        super().__init__(data, faults)
        self.service_orders: dict[str, ServiceOrder] = {}
        self.create_calls = 0
        self._lock = asyncio.Lock()

    async def create_service_order(self, req: ServiceOrderRequest) -> ServiceOrder:
        await self._validate(req)
        async with self._lock:
            number = service_order_no(req.client_ref)
            if number not in self.service_orders:
                self.create_calls += 1
                self.service_orders[number] = ServiceOrder(
                    service_order_no=number,
                    **req.model_dump(),
                    created_at=datetime.now(UTC).isoformat(),
                )
            created = self.service_orders[number]
        self.check_committed("create_service_order", req.order_no or req.client_ref)
        return created

    async def get_service_order(self, service_order_no: str) -> ServiceOrder:
        self.check("get_service_order", service_order_no)
        if service_order_no not in self.service_orders:
            raise NotFound()
        return self.service_orders[service_order_no]

    async def find_service_order(self, client_ref: str) -> ServiceOrder | None:
        return next(
            (o for o in self.service_orders.values() if o.client_ref == client_ref), None
        )
