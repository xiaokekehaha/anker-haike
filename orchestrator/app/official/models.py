"""主办方资料包（黑客松智能服务赛题资料.xlsx）导出后的数据模型与加载。

data/official/*.yaml 由 `python -m app.official.build` 从 xlsx 生成，禁止手改；
运行时只依赖本模块（pyyaml），不依赖 openpyxl。
"""

from __future__ import annotations

import os
import re
from datetime import date
from functools import cached_property
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.settings import REPO_ROOT

# 容器内 REPO_ROOT 解析为 /，由 OFFICIAL_DATA_DIR 指到 /srv/data/official（见 orchestrator/Dockerfile）。
OFFICIAL_DIR = Path(os.environ.get("OFFICIAL_DATA_DIR") or REPO_ROOT / "data" / "official")

PackageStatus = Literal["delivered", "in_transit", "returned", "shipped", "not_shipped"]
Scenario = Literal["shipping", "troubleshooting"]


PN = re.compile(r"T8D\d{2}|T\d{4}")


def pn_of(sku: str | None) -> str | None:
    """SKU → 产品 PN（Q&A 与产品目录的键）：T8D04121→T8D04、T81701W1→T8170、T2080A→T2080。
    订单 Anker001 的 SKU 写作 E235311B（E25 套装），按 T2353 处理。"""
    if not sku:
        return None
    text = sku.strip().upper()
    if match := PN.match(text):
        return match.group()
    if text.startswith("E2353"):
        return "T2353"
    return None


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OrderLine(Strict):
    sku: str
    description: str
    qty: int
    purchase_date: date | None
    warranty_end: date | None
    amount: str | None


class Package(Strict):
    tracking_no: str | None
    carrier: str | None
    skus: list[str]
    status: PackageStatus
    shipped_on: date | None = None
    delivered_on: date | None = None
    eta: date | None = None
    expected_ship_on: date | None = None
    raw_status: str = ""


class Order(Strict):
    order_no: str
    purchase_date: date
    address: str
    raw_status: str
    lines: list[OrderLine] = Field(min_length=1)
    packages: list[Package]

    @property
    def main_line(self) -> OrderLine:
        return self.lines[0]


class Dealer(Strict):
    country: str
    seller: str


class QAEntry(Strict):
    id: str
    sheet: str
    directory: list[str]
    title: str
    content: str
    visible: bool
    pn: list[str]
    pdt: str


class Ticket(Strict):
    id: str
    product_line: str
    product_name: str
    body: str
    order_ref: str | None
    order_no: str | None
    sku: str | None
    scenario: Scenario
    attachments: list[str] = Field(default_factory=list)


class OfficialData:
    """data/official 下各文件的只读视图；各集合按需加载。"""

    def __init__(self, root: Path = OFFICIAL_DIR):
        self.root = root

    def _load(self, name: str) -> dict:
        return yaml.safe_load((self.root / name).read_text(encoding="utf-8"))

    @cached_property
    def orders(self) -> list[Order]:
        return [Order.model_validate(o) for o in self._load("orders.yaml")["orders"]]

    @cached_property
    def dealers(self) -> list[Dealer]:
        return [Dealer.model_validate(d) for d in self._load("dealers.yaml")["dealers"]]

    @cached_property
    def qa(self) -> list[QAEntry]:
        return [QAEntry.model_validate(q) for q in self._load("qa.yaml")["entries"]]

    @cached_property
    def tickets(self) -> list[Ticket]:
        return [Ticket.model_validate(t) for t in self._load("tickets.yaml")["tickets"]]

    def attachment(self, name: str) -> Path:
        return self.root / "attachments" / name
