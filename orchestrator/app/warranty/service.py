"""票 41：演示订单/渠道参考库与确定性 L1–L6；只输出事实，不判断质保资格。"""

from __future__ import annotations

import unicodedata
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from haike_contracts.common import ReceiptOutcome
from pydantic import BaseModel, ConfigDict, Field, model_validator


def key(value: str | None) -> str:
    # 精确匹配规范化后的完整名称，不做子串/模糊授权判断。
    return "".join(unicodedata.normalize("NFKC", value or "").casefold().split())


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)


class Order(Record):
    order_no: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    purchase_date: date


class Dealer(Record):
    name: str = Field(min_length=1)
    region: str = Field(min_length=1)
    authorized: bool
    warranty_note: str = ""


class ReferenceData(Record):
    version: str
    orders: list[Order]
    dealers: list[Dealer]

    @model_validator(mode="after")
    def unique_keys(self):
        for values in ([key(o.order_no) for o in self.orders], [key(d.name) for d in self.dealers]):
            if len(values) != len(set(values)):
                raise ValueError("duplicate normalized order number or dealer name")
        return self

    @classmethod
    def from_yaml(cls, path: str | Path) -> ReferenceData:
        return cls.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


NEXT_STEP = {
    "insufficient": "请准备购买凭证，人工协助核实",
    "channel_unknown": "请准备购买凭证，人工协助核实",
    "order_verified": "资料已核实，转人工办理",
    "channel_in_directory": "经销商在名录内，人工确认购买凭证后办理",
    "order_product_mismatch": "凭证与当前设备信息不一致，需人工核实",
    "needs_manual_check": "凭证与当前设备信息不一致，需人工核实",
}


class ReceiptLookup:
    def __init__(self, data: ReferenceData):
        self.data = data
        self.orders = {key(o.order_no): o for o in data.orders}
        self.dealers = {key(d.name): d for d in data.dealers}

    def lookup(self, receipt: dict[str, Any], product: dict[str, Any] | None) -> ReceiptOutcome:
        fields = receipt.get("fields") or {}
        order_no, channel = key(fields.get("order_no")), key(fields.get("channel"))
        facts: dict[str, str] = {}
        conflicts: list[str] = []
        if not order_no and not channel:  # L1
            status = "insufficient"
        elif order := self.orders.get(order_no):
            sku = (product or {}).get("sku")
            if not sku:
                status = "needs_manual_check"
                conflicts.append("当前设备型号未确认，无法核对订单商品")
            elif sku == order.sku:  # L2
                status = "order_verified"
                facts = {"channel": order.channel, "purchase_date": order.purchase_date.isoformat()}
            else:  # L3
                status = "order_product_mismatch"
                conflicts.append(f"订单商品 {order.sku} 与当前设备 {sku} 不一致")
            confidence = (receipt.get("confidence") or {}).get("order_no", 0.0)
            if confidence < 0.7 and "order_no" not in (receipt.get("edited") or []):  # L4
                status = "needs_manual_check"
                conflicts.append("订单号低置信且未经修改，需人工核实")
                # 未确认订单归属，不把可能属于他人的渠道/日期作为已核实事实输出。
                facts = {}
        elif dealer := self.dealers.get(channel):  # L5
            status = "channel_in_directory"
            facts = {"dealer.name": dealer.name, "authorized": str(dealer.authorized).lower()}
        else:  # L6
            status = "channel_unknown"
        return ReceiptOutcome(
            status=status, verified_facts=facts, conflicts=conflicts, next_step=NEXT_STEP[status]
        )
