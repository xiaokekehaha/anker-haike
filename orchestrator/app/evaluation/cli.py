"""Reproducible deterministic evaluations; unpopulated vision data is explicitly pending."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from app.settings import REPO_ROOT

KINDS = ("vision", "routing", "emotion", "warranty", "authorization", "commitments", "tickets")

# 这几个金标字段断言的是「出现在列表里」，不是整列表相等。
MEMBERSHIP: dict[str, str] = {}


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    input: dict
    expected: dict


def evaluate(kind, value):
    if kind == "routing":
        from app.conversation.tasks import ordered_intents

        return {"order": ordered_intents(value["primary"], value["secondary"])}
    if kind == "emotion":
        from app.emotion.policy import evaluate_emotion

        return evaluate_emotion(**value)["emotion"]
    if kind == "warranty":
        from datetime import date

        from app.backends.service import OrderBook
        from app.warranty.service import decide_by_dealer, decide_by_order

        as_of = date.fromisoformat(value["as_of"])
        if value.get("order_no"):
            order = OrderBook().orders[value["order_no"].casefold()]
            decision = decide_by_order(order, value.get("sku"), as_of)
        else:
            purchase = date.fromisoformat(value["purchase_date"]) if value.get("purchase_date") else None
            decision = decide_by_dealer(value.get("seller"), value.get("country"), purchase, as_of)
        return {
            "status": decision.status,
            "basis": decision.basis,
            "warranty_end": decision.warranty_end.isoformat() if decision.warranty_end else None,
        }
    if kind == "authorization":
        from datetime import date

        from haike_contracts.common import WarrantyDecision

        from app.actions.gate import AuthorizationGate

        gate = {
            "kind": "replace",
            "warranty": WarrantyDecision(
                status=value.get("warranty", "in_warranty"), basis="order", as_of=date(2026, 10, 8), reason="eval"
            ),
            "logistics_ok": False,
            "evidence": {"order_or_receipt": "order:Anker016", "address": "order", "photo_or_video": "images:1", "serial_number": "customer:SN1"},
            "risk_cases": [],
            "allowed_operations": True,
            "user_confirmed": True,
            "case_status": "awaiting_confirmation",
        }
        return {"passed": AuthorizationGate().check(**(gate | value.get("gate", {}))).passed}
    if kind == "vision":
        from haike_contracts.common import FaultLocalization

        from app.diagnose.localization import normalize, signature_plans

        result = normalize(FaultLocalization.model_validate(value))
        return {"usable": result["image_quality"]["usable"], "plans": signature_plans(result)}
    if kind == "commitments":
        from app.cases.commitments import valid_commitment

        return {"valid": valid_commitment(value)}
    raise ValueError(kind)


def run(kind):
    if kind == "tickets":
        from app.evaluation.tickets import run as run_tickets

        return {**run_tickets(), "mode": "deterministic_regression", "at": datetime.now(UTC).isoformat()}
    raw = yaml.safe_load((REPO_ROOT / f"data/eval/{kind}/cases.yaml").read_text())
    cases = [EvalCase.model_validate(c) for c in raw["cases"]]
    if len({c.id for c in cases}) != len(cases):
        raise ValueError("duplicate evaluation IDs")
    failures = []
    for case in cases:
        actual = evaluate(kind, case.input)
        if any(
            (v not in actual.get(MEMBERSHIP[k], []) if k in MEMBERSHIP else actual.get(k) != v)
            for k, v in case.expected.items()
        ):
            failures.append({"id": case.id, "expected": case.expected, "actual": actual})
    return {
        "kind": kind,
        "mode": "deterministic_regression",
        "total": len(cases),
        "passed": len(cases) - len(failures),
        "failures": failures,
        "status": "pending_data" if not cases else "failed" if failures else "passed",
        "source": raw.get("source"),
        "at": datetime.now(UTC).isoformat(),
    }


def main():
    import asyncio

    from app.evaluation.semantic import MODEL_KINDS, run_model

    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=[*KINDS, "intent", "all", "live-tickets"])
    parser.add_argument("--mode", choices=["deterministic", "model"], default="deterministic")
    parser.add_argument("--lane", default=None)
    parser.add_argument("--min-accuracy", type=float, default=0.9)
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "reports/eval")
    parser.add_argument("--base-url", default="http://localhost:8000", help="live-tickets：运行中的编排服务")
    parser.add_argument("--ids", default="", help="live-tickets：只跑这些工单，逗号分隔，如 T55,T8")
    parser.add_argument("--concurrency", type=int, default=3, help="live-tickets：并发会话数（智谱账号并发 4 即限流）")
    args = parser.parse_args()
    if args.kind == "live-tickets":
        from app.evaluation.live_tickets import run_live

        ids = [i.strip() for i in args.ids.split(",") if i.strip()] or None
        result = asyncio.run(run_live(args.base_url, ids, args.concurrency, REPO_ROOT / "reports" / "eval"))
        print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
        print(f"report: {result['report']}")
        return 0
    if args.mode == "model":
        if args.kind not in MODEL_KINDS:
            parser.error("model mode supports intent, routing, emotion")
        report = asyncio.run(run_model(args.kind, args.output, lane=args.lane))
        print(f"{args.kind} real-model accuracy: {report['passed']}/{report['total']}")
        return int(report["accuracy"] < args.min_accuracy)
    if args.kind == "intent":
        parser.error("intent requires --mode model")
    reports = [run(k) for k in KINDS] if args.kind == "all" else [run(args.kind)]
    args.output.mkdir(parents=True, exist_ok=True)
    for report in reports:
        path = args.output / (report["kind"] + ".json")
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(
            f"{report['kind']}: {report['status']} {report['passed']}/{report['total']} -> {path}"
        )
    return int(any(r["failures"] for r in reports))
