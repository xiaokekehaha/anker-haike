"""data/official 由主办方 xlsx 导出；这里锁定导出产物的结构与关键业务事实（findings.md §3–§6）。"""

from datetime import date

import pytest

from app.official.build import month_day, package, tracking
from app.official.models import OfficialData

DATA = OfficialData()


def order(no: str):
    return next(o for o in DATA.orders if o.order_no == no)


def test_counts_match_source_sheets():
    assert len(DATA.orders) == 16
    assert len(DATA.tickets) == 63
    assert len(DATA.qa) == 875
    assert len(DATA.dealers) == 330  # 336 行去掉完全重复的 country+seller


def test_ticket_ids_follow_sheet_rows_and_attachments_exist():
    ids = [t.id for t in DATA.tickets]
    assert ids == [f"T{i}" for i in range(1, 64)]
    attached = {t.id: t.attachments for t in DATA.tickets if t.attachments}
    assert set(attached) == {"T14", "T20", "T30", "T38", "T42", "T45", "T46", "T48", "T53", "T55"}
    for names in attached.values():
        for name in names:
            assert DATA.attachment(name).is_file()


def test_split_shipment_and_accessory_package():
    # Anker001 拆成两个包裹均送达；Anker002 主机与配件包各有自己的单号。
    assert [p.status for p in order("Anker001").packages] == ["delivered", "delivered"]
    first, accessory = order("Anker002").packages
    assert (first.tracking_no, first.delivered_on) == ("Anker1234567-2", date(2026, 9, 21))
    assert (accessory.tracking_no, accessory.skus) == ("Anker1234567-3", ["T29C2001"])


def test_accessory_without_tracking_rides_with_main_package():
    (only,) = order("Anker004").packages
    assert only.skus == ["T2353T11", "T29YQA20"]


@pytest.mark.parametrize(
    ("order_no", "status", "field", "value"),
    [
        ("Anker005", "in_transit", "eta", date(2026, 9, 30)),
        ("Anker007", "returned", "delivered_on", None),
        ("Anker008", "not_shipped", "expected_ship_on", date(2026, 10, 20)),
    ],
)
def test_non_delivered_package_states(order_no, status, field, value):
    main = order(order_no).packages[0]
    assert main.status == status
    assert getattr(main, field) == value


def test_warranty_end_is_taken_from_order_sheet():
    assert order("Anker011").main_line.warranty_end == date(2025, 11, 30)
    assert order("Anker016").main_line.warranty_end == date(2027, 4, 1)


def test_qa_keeps_error_code_titles_and_pn():
    hits = [q for q in DATA.qa if "4090" in q.title]
    assert hits and all("T2352" in q.pn for q in hits)
    assert {q.sheet for q in DATA.qa} == {"eufy Robovacs Q&A", "eufy Breast Pump Q&A"}


def test_ticket_order_reference_variants():
    t45 = next(t for t in DATA.tickets if t.id == "T45")
    assert t45.order_no is None and t45.order_ref and "Reseller" in t45.order_ref
    t7 = next(t for t in DATA.tickets if t.id == "T7")
    assert t7.order_no is None and t7.sku is None


def test_month_day_rolls_into_next_year_after_anchor():
    assert month_day("Delivered on 1/3", date(2026, 12, 28)) == date(2027, 1, 3)
    assert month_day("Delivered on 2025/12/07", date(2025, 12, 3)) == date(2025, 12, 7)
    assert month_day("Delivered on 9/21", None) is None


def test_tracking_prefix_and_spaces_removed():
    assert tracking("Tracking number2: Anker1234567-1") == "Anker1234567-1"
    assert tracking("Anker 1234567-4") == "Anker1234567-4"


def test_presale_package_keeps_expected_ship_date():
    pkg = package("T2292111", "/", "/", "/", "预售产品，预计2026/10/20发货", "未发货")
    assert pkg["status"] == "not_shipped"
    assert pkg["expected_ship_on"] == date(2026, 10, 20)
    assert pkg["tracking_no"] is None and pkg["carrier"] is None
