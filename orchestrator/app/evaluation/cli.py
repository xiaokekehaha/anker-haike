"""Reproducible deterministic evaluations; unpopulated vision data is explicitly pending."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from app.settings import REPO_ROOT

KINDS = ("vision", "symptom", "routing", "emotion", "policy", "authorization", "commitments")

# 这几个金标字段断言的是「出现在列表里」，不是整列表相等：一次判定可以有多个缺参数或多条转人工理由，
# 用例只钉自己关心的那一条。
MEMBERSHIP = {"missing": "missing_inputs", "reason": "needs_human_reasons"}


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    input: dict
    expected: dict


def evaluate(kind, value):
    if kind == "symptom":
        from app.conversation.taxonomy import normalize

        hits = normalize(value["text"])
        return (
            {"fault_family": hits[0]["fault_family"], "symptom_code": hits[0]["symptom_code"]}
            if hits
            else {"fault_family": None, "symptom_code": None}
        )
    if kind == "routing":
        from app.conversation.tasks import ordered_intents

        return {"order": ordered_intents(value["primary"], value["secondary"])}
    if kind == "emotion":
        from app.emotion.policy import evaluate_emotion

        return evaluate_emotion(**value)["emotion"]
    if kind in {"policy", "authorization"}:
        from app.policy import PolicyEngine, PolicyInput

        decision = PolicyEngine().decide(
            PolicyInput.model_validate(value if kind == "policy" else value["policy"])
        )
        if kind == "policy":
            return {
                "needs_human": decision.needs_human,
                "replace_auto": any(
                    r.remedy == "replace" and r.auto_allowed for r in decision.remedies
                ),
                "parts_auto": any(
                    r.remedy == "parts" and r.auto_allowed for r in decision.remedies
                ),
                "paid_repair": any(
                    r.remedy == "paid_repair" and r.eligible for r in decision.remedies
                ),
                "within_warranty": decision.within_warranty,
                "warranty_end": decision.warranty_end.isoformat()
                if decision.warranty_end
                else None,
                "policy_id": decision.policy_id,
                "missing_inputs": decision.missing_inputs,
                "needs_human_reasons": decision.needs_human_reasons,
            }
        from app.actions.gate import AuthorizationGate

        gate = {
            "decision": decision,
            "option": {"remedy": "replace"},
            "receipt": {"status": "order_verified"},
            "product_state": "confirmed_sku",
            "risk_cases": [],
            "allowed_operations": True,
            "user_confirmed": True,
            "case_status": "awaiting_confirmation",
        }
        return {"passed": AuthorizationGate().check(**(gate | value["gate"])).passed}
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
    parser.add_argument("kind", choices=[*KINDS, "intent", "all"])
    parser.add_argument("--mode", choices=["deterministic", "model"], default="deterministic")
    parser.add_argument("--lane", default=None)
    parser.add_argument("--min-accuracy", type=float, default=0.9)
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "reports/eval")
    args = parser.parse_args()
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
