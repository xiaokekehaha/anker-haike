"""首封消息确定性解析：63 单主办方工单表驱动（data/official/tickets.yaml）。"""

from collections import Counter

import pytest

from app.official.message import detect_language, parse_message
from app.official.models import OfficialData, pn_of

TICKETS = {t.id: t for t in OfficialData().tickets}


def test_formats_and_languages_over_all_tickets():
    parsed = {tid: parse_message(t.body) for tid, t in TICKETS.items()}
    assert Counter(m.format for m in parsed.values()) == {"email": 27, "app_report": 30, "rma": 6}
    assert {tid for tid, m in parsed.items() if m.language == "nl"} == {"T6", "T13", "T18", "T20", "T22", "T36", "T37"}
    assert {tid: m.language for tid, m in parsed.items() if m.language in {"fr", "de", "es"}} == {
        "T21": "fr", "T28": "de", "T43": "es",
    }


def test_app_report_pn_matches_ticket_sku():
    for tid, t in TICKETS.items():
        m = parse_message(t.body)
        if m.format == "app_report":
            assert m.pn == pn_of(t.sku), tid


@pytest.mark.parametrize(
    ("ticket", "expected"),
    [
        ("T11", {"pn": "T2080", "sn": "12345678A", "codes": ("EB1L",)}),
        ("T13", {"pn": "T2353", "sn": None, "codes": ("5116",)}),  # 荷兰语字段名；SN 空值不误读下一行
        ("T28", {"pn": "T2351", "codes": ("2111",)}),  # 德语 Fehlercode
        ("T23", {"sn": "AK7RCN1E15600379", "codes": ("E41",)}),  # 8 位内部号忽略，码取 Push
        ("T2", {"order_no": "Anker002", "tracking_no": "Anker1234567-2"}),
        ("T45", {"sn": "ANKER1234567E", "tracking_no": None, "country": "US", "seller": "Aeroflow"}),
        ("T47", {"pn": "T8D02", "sn": "T8D02P20262058EB", "order_no": "Anker010"}),
        ("T55", {"format": "rma", "order_no": "Anker016", "sn": None}),
        ("T7", {"order_no": None, "tracking_no": None, "codes": ()}),
    ],
)
def test_extracted_facts(ticket, expected):
    m = parse_message(TICKETS[ticket].body)
    assert {k: getattr(m, k) for k in expected} == expected


def test_language_detection_basics():
    assert detect_language("我的扫地机不吸了") == "zh"
    assert detect_language("The vacuum did not arrive. What should I do?") == "en"
    assert detect_language("Heb vorige week de robot stofzuiger besteld. Deze is nog steeds niet binnen!") == "nl"
