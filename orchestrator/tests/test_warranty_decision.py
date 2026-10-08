"""订单质保判断与授权经销商名录（主办方 SOP；data/official/dealers.yaml）。"""

from datetime import date

import pytest

from app.backends.service import OrderBook
from app.settings import settings
from app.warranty.service import (
    add_months,
    decide_by_dealer,
    decide_by_order,
    directory,
    normalize_country,
    today,
)

AS_OF = date(2026, 10, 8)


def order(no):
    return OrderBook().orders[no.casefold()]


@pytest.mark.parametrize(
    ("seller", "country", "expected"),
    [
        ("Aeroflow", "US", "Aeroflow Breastpumps"),  # T45：凭证上只写 Aeroflow
        ("best buy", "usa", "best buy"),
        ("BEST BUY Inc.", "United States", "best buy"),
        ("Currys", "uk", "Currys"),
        ("currys", "GB", "Currys"),
        ("MediaMarkt", "Germany", "Media Markt TV-HiFi Elektro"),  # 名录写法带空格与后缀
        ("Albert Heijn", "NL", "Albert Heijn B.V."),
        ("Amazon", "US", None),  # 名录未收录 Amazon US：按 SOP 属于非授权，由客户联系商家
    ],
)
def test_dealer_match_is_country_exact_and_seller_fuzzy(seller, country, expected):
    found = directory().match(seller, country)
    assert (found.dealer.seller if found else None) == expected


def test_dealer_in_other_country_is_not_authorized():
    assert directory().match("Aeroflow Breastpumps", "UK") is None
    assert directory().match("eBay", "US") is None  # eBay 只在 DE 名录内
    assert directory().match("eBay", "DE") is not None


def test_short_or_empty_seller_never_matches():
    assert directory().match("ab", "US") is None
    assert directory().match(None, "US") is None
    assert directory().match("Walmart", None) is None


def test_country_aliases():
    assert normalize_country("United Kingdom") == "UK"
    assert normalize_country("nl") == "NL"
    assert normalize_country("Atlantis") is None


def test_order_decision_uses_line_warranty_end():
    decision = decide_by_order(order("Anker016"), "T8D04121", AS_OF)
    assert (decision.status, decision.basis, decision.warranty_end) == ("in_warranty", "order", date(2027, 4, 1))
    assert decide_by_order(order("Anker011"), None, AS_OF).status == "out_of_warranty"


def test_order_decision_picks_accessory_line_by_sku():
    decision = decide_by_order(order("Anker002"), "T29C2001", AS_OF)
    assert decision.sku == "T29C2001" and decision.warranty_end == date(2026, 10, 13)


def test_dealer_decision_is_twelve_months_from_purchase():
    decision = decide_by_dealer("Aeroflow", "US", date(2025, 12, 9), AS_OF)
    assert (decision.status, decision.basis, decision.warranty_end) == ("in_warranty", "dealer", date(2026, 12, 9))
    assert decide_by_dealer("Unknown Shop", "US", date(2026, 1, 1), AS_OF).status == "unauthorized_dealer"
    assert decide_by_dealer("Aeroflow", "US", None, AS_OF).status == "unknown"
    assert decide_by_dealer(None, None, None, AS_OF).basis == "none"


def test_add_months_clamps_month_end():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2027, 2, 29 - 1), 12) == date(2028, 2, 28)
    assert add_months(date(2024, 2, 29), 12) == date(2025, 2, 28)


def test_demo_clock_overrides_turn_time(monkeypatch):
    monkeypatch.setattr(settings, "demo_today", None)
    assert today("2026-10-08T09:00:00+08:00") == date(2026, 10, 8)
    monkeypatch.setattr(settings, "demo_today", date(2026, 9, 28))
    assert today("2026-10-08T09:00:00+08:00") == date(2026, 9, 28)
