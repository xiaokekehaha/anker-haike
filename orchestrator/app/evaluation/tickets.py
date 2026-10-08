"""63 单主办方工单的确定性评测（data/eval/tickets/cases.yaml）：不调模型、不连知识库。

逐单核对首封消息能被确定性层解对的部分：
- 语言、PN、错误码、订单号（app.official.message）；
- 错误码精确命中的官方 Q&A，以及硬件故障 / 未收录码两类直达结论（app.official.qa_index）；
- 物流与质保两条 SOP 分支的终点（订单包裹状态、订单质保结束日期，按评测集的 as_of 判断）。
意图、现象召回（qa_gold）和多轮流程需要模型与知识库，由端到端测试与线上抽检覆盖，这里只统计覆盖面。
"""

from __future__ import annotations

from datetime import date
from typing import Any

import yaml

from app.backends import logistics
from app.backends.service import OrderBook
from app.official.message import parse_message
from app.official.models import OfficialData
from app.official.qa_index import get_qa_index
from app.settings import REPO_ROOT
from app.warranty.service import decide_by_order

CASES = REPO_ROOT / "data" / "eval" / "tickets" / "cases.yaml"
LOGISTICS_SOP = {
    "delivered": "logistics_delivered",
    "reship_eligible": "logistics_reship",
    "in_transit": "logistics_in_transit",
    "presale": "logistics_presale",
}


def evaluate_case(case: dict[str, Any], body: str, as_of: date, orders: OrderBook) -> dict[str, Any]:
    parsed = parse_message(body)
    actual: dict[str, Any] = {"language": parsed.language}
    if "pn" in case:
        actual["pn"] = parsed.pn
    if "codes" in case:
        actual["codes"] = list(parsed.codes)
    if "order_no" in case:
        actual["order_no"] = parsed.order_no
    index = get_qa_index()
    if parsed.codes:
        hits = [g for code in parsed.codes for g in index.lookup(parsed.pn, code)]
        if not hits:
            actual["sop"] = "code_miss"
        else:
            actual["qa_exact"] = hits[0].qa_id
            actual["sop"] = "warranty_by_qa" if hits[0].kind == "warranty" else "troubleshoot"
    elif case["sop"].startswith("logistics_") and parsed.order_no:
        order = orders.orders[parsed.order_no.casefold()]
        actual["sop"] = LOGISTICS_SOP.get(logistics.verdict(order, as_of), "unknown")
    elif case["sop"] == "ask_order" and not parsed.order_no:
        actual["sop"] = "ask_order"
    elif case["sop"] in {"out_of_warranty", "warranty_replace"} and parsed.order_no:
        decision = decide_by_order(orders.orders[parsed.order_no.casefold()], None, as_of)
        actual["sop"] = "out_of_warranty" if decision.status == "out_of_warranty" else "warranty_replace"
    expected = {k: case[k] for k in ("language", "pn", "codes", "order_no", "qa_exact") if k in case}
    if "sop" in actual:
        expected["sop"] = case["sop"]
    failures = {k: {"expected": v, "actual": actual.get(k)} for k, v in expected.items() if actual.get(k) != v}
    return {"id": case["id"], "deterministic": "sop" in actual, "failures": failures}


def run() -> dict[str, Any]:
    raw = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    as_of = date.fromisoformat(raw["as_of"])
    bodies = {t.id: t.body for t in OfficialData().tickets}
    orders = OrderBook()
    results = [evaluate_case(c, bodies[c["id"]], as_of, orders) for c in raw["cases"]]
    failed = [r for r in results if r["failures"]]
    covered = [r for r in results if r["deterministic"]]
    return {
        "kind": "tickets",
        "total": len(results),
        "sop_deterministic": len(covered),
        "passed": len(results) - len(failed),
        "failures": failed,
        "status": "failed" if failed else "passed",
    }
