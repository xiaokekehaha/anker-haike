"""物流判定（主办方 SOP 规则 1）：轨迹未显示送达且客户未收到 → 可补发；显示送达 → 不补发。

送达但客户坚称未收到时提交承运商调查（D3），预售未发告知预计发货日。只看订单里的主商品包裹。
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from app.official.models import Order, Package

Verdict = Literal["delivered", "reship_eligible", "in_transit", "presale", "unknown"]

STATUS_TEXT = {
    "delivered": "已送达",
    "in_transit": "运输中",
    "returned": "已退回发件人",
    "shipped": "已发货，暂无轨迹",
    "not_shipped": "未发货",
}


def main_package(order: Order) -> Package | None:
    sku = order.main_line.sku
    return next((p for p in order.packages if sku in p.skus), order.packages[0] if order.packages else None)


def describe(pkg: Package) -> str:
    head = " ".join(filter(None, [pkg.carrier, pkg.tracking_no])) or "包裹"
    text = STATUS_TEXT[pkg.status]
    if pkg.status == "delivered" and pkg.delivered_on:
        text = f"已于 {pkg.delivered_on.isoformat()} 送达"
    elif pkg.status == "in_transit" and pkg.eta:
        text = f"运输中，预计 {pkg.eta.isoformat()} 送达"
    elif pkg.status == "not_shipped" and pkg.expected_ship_on:
        text = f"未发货（预售），预计 {pkg.expected_ship_on.isoformat()} 发货"
    return f"{head}：{text}（含 {'、'.join(pkg.skus)}）"


def verdict(order: Order, as_of: date) -> Verdict:
    pkg = main_package(order)
    if pkg is None:
        return "unknown"
    if pkg.status == "delivered":
        return "delivered"
    if pkg.status == "returned":
        return "reship_eligible"
    if pkg.status == "not_shipped":
        return "presale"
    if pkg.status == "in_transit":
        return "reship_eligible" if pkg.eta and pkg.eta < as_of else "in_transit"
    return "unknown"


SOP_TEXT = {
    "delivered": "物流显示主商品已送达，按售后规则不再补发。如果确实没有收到，我可以为您提交承运商调查单，由人工跟进。",
    "reship_eligible": "物流未显示送达，按售后规则可以为您申请补发。",
    "in_transit": "包裹仍在运输途中，请以预计送达时间为准；逾期仍未送达可以再联系我们申请补发。",
    "presale": "该商品为预售，尚未发货，会在预计发货日发出。",
    "unknown": "物流信息不完整，我会交由人工核实。",
}
