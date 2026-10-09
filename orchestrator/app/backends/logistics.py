"""物流判定（主办方 SOP 规则 1）：轨迹未显示送达且客户未收到 → 可补发；显示送达 → 不补发。

送达但客户坚称未收到时提交承运商调查（D3），预售未发告知预计发货日。只看订单里的主商品包裹。
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from app.official.models import Order, Package

Verdict = Literal["delivered", "reship_eligible", "in_transit", "presale", "unknown"]

STATUS_TEXT = {
    "delivered": "delivered",
    "in_transit": "in transit",
    "returned": "returned to sender",
    "shipped": "shipped, no tracking updates yet",
    "not_shipped": "not shipped yet",
}


def main_package(order: Order) -> Package | None:
    sku = order.main_line.sku
    return next((p for p in order.packages if sku in p.skus), order.packages[0] if order.packages else None)


def describe(pkg: Package) -> str:
    head = " ".join(filter(None, [pkg.carrier, pkg.tracking_no])) or "Package"
    text = STATUS_TEXT[pkg.status]
    if pkg.status == "delivered" and pkg.delivered_on:
        text = f"delivered on {pkg.delivered_on.isoformat()}"
    elif pkg.status == "in_transit" and pkg.eta:
        text = f"in transit, estimated delivery {pkg.eta.isoformat()}"
    elif pkg.status == "not_shipped" and pkg.expected_ship_on:
        text = f"pre-order, not shipped yet, expected to ship on {pkg.expected_ship_on.isoformat()}"
    return f"{head}: {text} ({', '.join(pkg.skus)})"


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
    "delivered": "Tracking shows the item was delivered, so under our after-sales policy we can't send a replacement "
                 "shipment. If you really haven't received it, I can open a carrier investigation and a colleague will follow up.",
    "reship_eligible": "Tracking doesn't show the item as delivered, so under our after-sales policy we can arrange a reship for you.",
    "in_transit": "The package is still in transit; please allow until the estimated delivery date. If it still hasn't "
                  "arrived after that, contact us again and we can arrange a reship.",
    "presale": "This item is a pre-order and hasn't shipped yet. It will be sent on the expected ship date.",
    "unknown": "The tracking information is incomplete, so I'll pass this to a colleague to check.",
}

# reship_eligible 有两条互不相同的来路，理由必须分开说，否则会说出与事实相反的话：
# 退回发件人，和「在途但已过预计送达日」。后者常见于多包裹订单 —— T5（Anker005）的主机包裹
# ETA 9/30 逾期未达，而同一订单的配件包裹 9/15 已送达；套用「轨迹未显示送达」就是错的
# （2026-10-09 测评逐单核对指出这一条）。理由从包裹状态推出来，不按 verdict 写死。
RESHIP_REASON = {
    "returned": "The package was returned to the sender, so under our after-sales policy we can arrange a reship for you.",
    "overdue": "This package hasn't arrived by its estimated delivery date of {eta}, so under our after-sales policy "
               "we can arrange a reship for you.",
    "not_delivered": "Tracking doesn't show the item as delivered, so under our after-sales policy we can arrange a reship for you.",
}


def sop_text(order: Order, as_of: date) -> str:
    """客户可见的 SOP 结论。只有 reship_eligible 需要看具体来路，其余按 verdict 取。"""
    v = verdict(order, as_of)
    if v != "reship_eligible":
        return SOP_TEXT[v]
    pkg = main_package(order)
    if pkg is not None and pkg.status == "returned":
        return RESHIP_REASON["returned"]
    if pkg is not None and pkg.eta and pkg.eta < as_of:
        return RESHIP_REASON["overdue"].format(eta=pkg.eta.isoformat())
    return RESHIP_REASON["not_delivered"]
