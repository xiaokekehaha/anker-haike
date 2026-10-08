from datetime import date
from typing import Literal, Protocol

from haike_contracts.common import ServiceOrderType, Strict
from pydantic import Field

from app.official.models import Order, Package


class BackendError(RuntimeError):
    recoverable = False
    user_message = "Our after-sales tool can't process this right now."


class NotFound(BackendError):
    user_message = "I couldn't find that order. Please check the order number."


class Conflict(BackendError):
    user_message = "There is already a service request, or the order status conflicts. A colleague will need to check this."


class Unavailable(BackendError):
    recoverable = True
    user_message = "Our after-sales tool is temporarily unavailable. Please try again later or ask for a colleague."


class Timeout(BackendError):
    recoverable = True
    user_message = "Our after-sales tool timed out. Please try again later or ask for a colleague."


class ServiceOrderRequest(Strict):
    type: ServiceOrderType
    order_no: str | None = None
    sku: str | None = None
    reason: str = Field(min_length=1)
    evidence: dict[str, str] = Field(default_factory=dict)
    # Caller's idempotency key. After an ambiguous timeout the caller looks the
    # order up by it instead of creating again; a real backend must honour it.
    client_ref: str


class ServiceOrder(Strict):
    service_order_no: str
    type: ServiceOrderType
    order_no: str | None = None
    sku: str | None = None
    reason: str
    evidence: dict[str, str] = Field(default_factory=dict)
    # 主办方工具只收单：提交后一律转人工处理，没有自动发货或退款。
    status: Literal["submitted", "in_review", "completed", "rejected"] = "submitted"
    created_at: str
    client_ref: str


class Logistics(Strict):
    order_no: str
    packages: list[Package]
    as_of: date


class BackendClient(Protocol):
    async def get_order(self, order_no: str) -> Order: ...
    async def find_order_by_tracking(self, tracking_no: str) -> Order: ...
    async def create_service_order(self, req: ServiceOrderRequest) -> ServiceOrder: ...
    async def get_service_order(self, service_order_no: str) -> ServiceOrder: ...
    async def find_service_order(self, client_ref: str) -> ServiceOrder | None: ...
