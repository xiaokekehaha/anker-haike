"""主办方 SOP 的「订单质保判断」与经销商名录（data/official/dealers.yaml）。

    有订单        → 订单行的质保结束日期 ≥ 演示今天 → 保内，否则过保
    查不到订单    → 核实购买商家：country 精确 + seller 模糊命中名录 → 授权经销，购买日起 12 个月
                    （工单 T45 注明「Reseller（提供12个月质保）」）；未命中 → 引导客户联系商家售后
    信息不足      → unknown，追问而不是猜

只输出判定与依据，不做任何办理动作。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime
from difflib import SequenceMatcher
from functools import lru_cache

from haike_contracts.common import WarrantyDecision

from app.official.models import Dealer, OfficialData, Order, pn_of
from app.settings import settings

DEALER_WARRANTY_MONTHS = 12
FUZZY_THRESHOLD = 0.85
# 名录里常见的公司后缀与标点，对授权判定没有区分度。
NOISE = re.compile(
    r"\b(inc|llc|ltd|limited|gmbh|corp|corporation|co|b\.?v|s\.?a|sarl|sasu|plc|eg|ag|mbh|ta|t/a)\b"
)
COUNTRY_ALIASES = {
    "usa": "US", "unitedstates": "US", "america": "US",
    "gb": "UK", "unitedkingdom": "UK", "england": "UK", "britain": "UK", "greatbritain": "UK",
    "germany": "DE", "deutschland": "DE",
    "netherlands": "NL", "holland": "NL", "nederland": "NL",
    "ireland": "IE", "france": "FR", "canada": "CA",
    "saudiarabia": "KSA", "sa": "KSA", "ksa": "KSA",
    "uae": "UAE", "unitedarabemirates": "UAE", "ae": "UAE",
    "russia": "RU",
}


def today(at: str | None = None) -> date:
    """演示时钟：设置 DEMO_TODAY 时固定，否则取本轮时间。"""
    if settings.demo_today:
        return settings.demo_today
    return date.fromisoformat(at[:10]) if at else datetime.now(UTC).date()


def normalize_country(value: str | None) -> str | None:
    if not value:
        return None
    compact = re.sub(r"[^a-z]", "", value.casefold())
    if compact.upper() in {"US", "UK", "DE", "NL", "IE", "FR", "CA", "RU"}:
        return compact.upper()
    return COUNTRY_ALIASES.get(compact)


def seller_key(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold()
    text = NOISE.sub(" ", text.replace("&", " and "))
    return re.sub(r"[^\w]", "", text)


def add_months(start: date, months: int) -> date:
    month = start.month - 1 + months
    year, month = start.year + month // 12, month % 12 + 1
    days = [31, 29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return date(year, month, min(start.day, days))


@dataclass(frozen=True)
class DealerMatch:
    dealer: Dealer
    score: float


class DealerDirectory:
    def __init__(self, dealers: list[Dealer]):
        self.by_country: dict[str, list[tuple[str, Dealer]]] = {}
        for dealer in dealers:
            self.by_country.setdefault(dealer.country, []).append((seller_key(dealer.seller), dealer))

    def match(self, seller: str | None, country: str | None) -> DealerMatch | None:
        code = normalize_country(country)
        key = seller_key(seller or "")
        if not code or len(key) < 3:
            return None
        best: DealerMatch | None = None
        for candidate, dealer in self.by_country.get(code, []):
            if len(candidate) < 3:
                continue
            if key == candidate or (min(len(key), len(candidate)) >= 4 and (key in candidate or candidate in key)):
                score = 1.0
            else:
                score = SequenceMatcher(None, key, candidate).ratio()
            if score >= FUZZY_THRESHOLD and (best is None or score > best.score):
                best = DealerMatch(dealer, score)
        return best


@lru_cache(maxsize=1)
def directory() -> DealerDirectory:
    return DealerDirectory(OfficialData().dealers)


def order_line(order: Order, sku: str | None):
    """案件产品对应的订单行；未指定时取主商品行（订单第一行）。"""
    if sku:
        for line in order.lines:
            if line.sku == sku or pn_of(line.sku) == pn_of(sku):
                return line
    return order.main_line


def decide_by_order(order: Order, sku: str | None, as_of: date) -> WarrantyDecision:
    line = order_line(order, sku)
    if line.warranty_end is None:
        return WarrantyDecision(
            status="unknown", basis="order", as_of=as_of, order_no=order.order_no, sku=line.sku,
            reason=f"order {order.order_no} has no warranty end date on record",
        )
    inside = line.warranty_end >= as_of
    return WarrantyDecision(
        status="in_warranty" if inside else "out_of_warranty",
        basis="order", warranty_end=line.warranty_end, as_of=as_of,
        order_no=order.order_no, sku=line.sku,
        reason=f"order {order.order_no} {'is' if inside else 'was'} under warranty until {line.warranty_end.isoformat()}",
    )


def decide_by_dealer(
    seller: str | None, country: str | None, purchase_date: date | None, as_of: date
) -> WarrantyDecision:
    if not seller or not normalize_country(country):
        return WarrantyDecision(
            status="unknown", basis="none", as_of=as_of, dealer=seller, country=country,
            reason="the order wasn't found, and the seller name and country of purchase are needed",
        )
    found = directory().match(seller, country)
    if found is None:
        return WarrantyDecision(
            status="unauthorized_dealer", basis="dealer", as_of=as_of, dealer=seller,
            country=normalize_country(country),
            reason=f"{seller} is not on our list of authorized dealers in {normalize_country(country)}",
        )
    base = {"basis": "dealer", "as_of": as_of, "dealer": found.dealer.seller, "country": found.dealer.country}
    if purchase_date is None:
        return WarrantyDecision(
            status="unknown",
            reason=f"{found.dealer.seller} ({found.dealer.country}) is an authorized dealer, but the purchase date is missing",
            **base,
        )
    end = add_months(purchase_date, DEALER_WARRANTY_MONTHS)
    inside = end >= as_of
    return WarrantyDecision(
        status="in_warranty" if inside else "out_of_warranty",
        warranty_end=end,
        reason=f"{found.dealer.seller} is an authorized dealer; the {DEALER_WARRANTY_MONTHS}-month warranty from purchase "
               f"{'runs' if inside else 'ran'} until {end.isoformat()}",
        **base,
    )
