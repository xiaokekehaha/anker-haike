"""官方 Q&A 确定性索引：错误码抽取、精确命中、条目类型与步骤拆分（data/official/qa.yaml）。"""

from collections import Counter

import pytest

from app.official.models import OfficialData
from app.official.qa_index import QAIndex, inline_steps, message_codes, title_codes

INDEX = QAIndex.build()
TICKETS = {t.id: t for t in OfficialData().tickets}


@pytest.mark.parametrize(
    ("title", "codes"),
    [
        ("what should I do when T2080 S1 Pro has E20: Robot clean water pump abnormal", ("E20",)),
        ("What should I do when T2353 Omni E25 /T2352 Omni E28 has 2220/2221/2224/2225 Error: Side brush", ("2220", "2221", "2224", "2225")),
        ("What should I do if my X10 Pro Omni T2351 reports a warning 6025:The dirty water tank is full", ("6025",)),
        ("What should I do if my X10 Pro Omni T2351 reports an error-1012 Left wheel module error or 1022 Right wheel module error", ("1012", "1022")),
        ("What should I do if my X10 Pro Omni T2351 reports a warning 4111&4112:Front bumper stuck", ("4111", "4112")),
        ("what should I do when T2080 S1 Pro has EB01: Base station dust bag full", ("EB01",)),
        ("What should I do if my X10 Pro Omni T2351 reports tips 7032:Failed to find station", ("7032",)),
        ("My RoboVac S1 Pro/T2080 gives out E10: Please install the dirty water tank.", ("E10",)),
        # 机型名 Omni E25 / E28 不是 S1 Pro 的 E25 / E28 错误码
        ("What should I do when T2353 Omni E25 /T2352 Omni E28 stuck on rug", ()),
        ("What should I do if my omni E28/E25/T2353/T2352 cannot clean on floors without a base station?", ()),
    ],
)
def test_title_codes_are_anchored(title, codes):
    assert title_codes(title) == codes


def test_no_model_name_is_indexed_as_a_code():
    bad = [g.qa_id for g in INDEX.guides.values() if {"E25", "E28"} & set(g.codes) and "T2080" not in g.pns]
    assert bad == []


# 18 单带错误码的工单：17 单唯一命中，5116（T13）知识库未收录。
EXPECTED_HITS = {
    "T11": ("EB1L", "rv-0481"), "T14": ("4090", "rv-0028"), "T15": ("EB03", "rv-0428"),
    "T16": ("2310", "rv-0056"), "T17": ("6063", "rv-0498"), "T18": ("3212", "rv-0147"),
    "T19": ("6011", "rv-0023"), "T22": ("7002", "rv-0106"), "T23": ("E41", "rv-0138"),
    "T24": ("6013", "rv-0273"), "T25": ("E53", "rv-0451"), "T26": ("E23", "rv-0063"),
    "T27": ("3212", "rv-0147"), "T28": ("2111", "rv-0256"), "T30": ("E4", "rv-0443"),
    "T32": ("3021", "rv-0061"), "T33": ("E5A", "rv-0439"),
}


@pytest.mark.parametrize(("ticket", "expected"), sorted(EXPECTED_HITS.items()))
def test_ticket_error_code_hits_one_entry(ticket, expected):
    t = TICKETS[ticket]
    code, qa_id = expected
    assert message_codes(t.body) == (code,)
    assert [g.qa_id for g in INDEX.lookup(t.sku, code)] == [qa_id]


def test_unindexed_code_is_a_miss_not_a_neighbour():
    t = TICKETS["T13"]
    assert message_codes(t.body) == ("5116",)
    assert INDEX.lookup(t.sku, "5116") == []


def test_s1_pro_internal_problem_code_is_ignored():
    # 21037332- 是内部号，真正的码在 Problem Push 的 EB1L
    assert message_codes("Problem Code: 21037332-\nProblem Push: EB1L: The robot encountered an error") == ("EB1L",)
    assert message_codes("Problem Code: 20972810-E5A: Gyroscope abnormal") == ("E5A",)


def test_code_without_model_resolves_to_owning_family():
    assert INDEX.pns_for_code("EB1L") == {"T2080"}
    assert [g.qa_id for g in INDEX.lookup(None, "EB1L")] == ["rv-0481"]


def test_kinds_and_step_parsing():
    kinds = Counter(g.kind for g in INDEX.guides.values())
    assert kinds == {"answer": 427, "steps": 410, "warranty": 38}
    guide = INDEX.guides["rv-0481"]
    assert [s.no for s in guide.steps] == [1, 2, 3, 4, 5]
    assert guide.plan_id == "qa_rv_0481"
    # 链接从正文剥离，挂到步骤媒体上
    assert "http" not in guide.steps[0].text and [m.kind for m in guide.steps[0].media] == ["image", "image"]


def test_hardware_malfunction_entries_go_to_warranty():
    assert INDEX.guides["rv-0028"].kind == "warranty"  # 4090 墙边传感器
    # 先排查、末步写硬件故障：该步带质保标记
    assert [s.warranty for s in INDEX.guides["rv-0273"].steps] == [False, True]


def test_inline_steps_require_sequential_sentence_start_numbers():
    assert [n for n, _ in inline_steps("1. Delete the map. 2. Recreate it.")] == [1, 2]
    assert inline_steps("Update the firmware to version 7.0.143 or higher.") == []
    steps = inline_steps("* 1. Check the box. * * 2. Enable pet mode. * Tips: no dust collection at night")
    assert [t for _, t in steps] == ["Check the box.", "Enable pet mode."]


def test_version_tracks_source_sha():
    assert len(INDEX.version) == 12 and INDEX.version != "unknown"


def test_restart_first_entries_become_two_steps_before_warranty():
    # rv-0256（T28 的 2111）：先重启，仍未解决才走质保
    steps = INDEX.guides["rv-0256"].steps
    assert INDEX.guides["rv-0256"].kind == "steps"
    assert [s.warranty for s in steps] == [False, True] and "restart" in steps[0].text.lower()
