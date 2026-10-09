"""63 单主办方工单确定性评测（data/eval/tickets/cases.yaml）：事实层与物流 / 质保 / 错误码三类 SOP 终点。"""

import yaml

from app.evaluation.cli import run
from app.evaluation.live_tickets import CASES, sop_passed, terminals_of


def test_ticket_eval_passes_and_covers_deterministic_sop_branches():
    report = run("tickets")
    assert report["total"] == 63
    assert report["failures"] == []
    # 物流 11 单、错误码 18 单、订单质保 6 单可不依赖模型判定终点
    assert report["sop_deterministic"] == 35


def test_handoff_terminal_needs_persisted_evidence_not_wording():
    """「已转交」话术不是转人工证据：只认案件已进人工队列、记录了该诉求、有交接摘要（2026-10-09 T9 假通过）。

    T9 一句两诉求，必须同时到达两个终点：暂缓已交接 + 预售发货日已答。
    """
    claimed = "I can't change or hold an order myself, so I've passed your request to a colleague who can."
    answered = claimed + " Package: pre-order, not shipped yet, expected to ship on 2026-10-20"
    common = {"escalate_reasons": [], "service_types": [], "step_cards": 0}
    # 案件仍 open、无交接：不算转人工
    assert terminals_of({}, case_status="open", review_requested=None, handoff=False, said=claimed, **common) == ["explain"]
    assert terminals_of({}, case_status="open", review_requested=None, handoff=False, said=answered, **common) == ["logistics_presale"]
    reached = terminals_of({}, case_status="awaiting_approval", review_requested="order_change", handoff=True, said=answered, **common)
    assert reached == ["order_change_human", "logistics_presale"]
    t9 = next(c for c in yaml.safe_load(CASES.read_text(encoding="utf-8"))["cases"] if c["id"] == "T9")
    assert t9["sop"] == "logistics_presale" and t9["sop_also"] == ["order_change_human"]
    assert sop_passed(t9, reached)
    assert not sop_passed(t9, ["order_change_human"])  # 只交接、没答物流（本轮实测）
    assert not sop_passed(t9, ["logistics_presale"])  # 只答物流、没交接（首轮实测）
    assert sop_passed({"sop": "logistics_presale"}, ["logistics_presale"])
