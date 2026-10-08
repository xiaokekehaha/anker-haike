"""63 单主办方工单确定性评测（data/eval/tickets/cases.yaml）：事实层与物流 / 质保 / 错误码三类 SOP 终点。"""

from app.evaluation.cli import run


def test_ticket_eval_passes_and_covers_deterministic_sop_branches():
    report = run("tickets")
    assert report["total"] == 63
    assert report["failures"] == []
    # 物流 11 单、错误码 18 单、订单质保 6 单可不依赖模型判定终点
    assert report["sop_deterministic"] == 35
