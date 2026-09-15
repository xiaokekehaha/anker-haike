from datetime import date
from typing import Protocol

from haike_contracts.common import Strict
from pydantic import Field


class BackendError(RuntimeError):
    recoverable = False
    user_message = "业务系统暂时无法处理"


class NotFound(BackendError):
    user_message = "未找到对应订单，请核对订单号"


class Conflict(BackendError):
    user_message = "已有服务单或订单状态冲突，请联系人工核实"


class Unavailable(BackendError):
    recoverable = True
    user_message = "业务系统暂时不可用，请稍后重试或联系人工"


class Timeout(BackendError):
    recoverable = True
    user_message = "业务系统响应超时，请稍后重试或联系人工"


class Order(Strict):
    order_no: str
    sku: str
    channel: str
    purchase_date: date
    region_purchase: str | None = None
    platform: str | None = None
    amount: str | None = None
    currency: str | None = None


class Shipment(Strict):
    tracking_no: str
    order_no: str
    carrier: str
    status: str
    events: list[dict] = Field(default_factory=list)
    updated_at: str


class ServiceOrderRequest(Strict):
    order_no: str
    sku: str
    type: str = "replacement"
    reason_code: str
    evidence_ids: list[str] = Field(default_factory=list)


class ServiceOrder(Strict):
    service_order_no: str
    order_no: str
    sku: str
    type: str
    reason_code: str
    status: str
    created_at: str
    eta_days: int = 3


class BackendClient(Protocol):
    async def get_order(self, order_no: str) -> Order: ...
    async def get_shipment(
        self, *, order_no: str | None = None, tracking_no: str | None = None
    ) -> Shipment: ...
    async def create_service_order(self, req: ServiceOrderRequest) -> ServiceOrder: ...
    async def get_service_order(self, service_order_no: str) -> ServiceOrder: ...
