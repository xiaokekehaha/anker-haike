"""No IO in decide: the frozen bundle and input fully determine the result."""

import calendar
import hashlib
import json
from datetime import date

from haike_contracts.common import Clause, PolicyCondition, PolicyDecision, RemedyDecision

from .loader import PolicyLoader, validate
from .models import PolicyInput


def _add_months(day: date, months: int) -> date:
    year, month0 = divmod(day.year * 12 + day.month - 1 + months, 12)
    return date(year, month0 + 1, min(day.day, calendar.monthrange(year, month0 + 1)[1]))


def conditions(when: dict, context: dict) -> list[PolicyCondition]:
    results = []
    for name, expected in when.items():
        field = {
            "days_since_purchase_lte": "days_since_purchase",
            "not_prior": "prior_remedies",
            "region_use_in": "region_use",
            "region_use_not_in": "region_use",
        }.get(name, name)
        actual = context.get(field)
        if name == "days_since_purchase_lte":
            met = actual is not None and 0 <= actual <= expected
        elif name == "not_prior":
            met = not set(actual or []) & set(expected)
        elif name == "region_use_not_in":
            met = actual not in expected
        elif isinstance(expected, list):
            met = actual in expected
        else:
            met = actual == expected
        results.append(PolicyCondition(name=name, expected=expected, actual=actual, met=met))
    return results


class PolicyEngine:
    def __init__(self, bundle: dict | None = None):
        self.bundle = validate(bundle) if bundle is not None else PolicyLoader().load()

    def decide(self, value: PolicyInput) -> PolicyDecision:
        data = value.model_dump(mode="json")
        aliases = self.bundle["regions"].get("aliases", {})
        for field in ("region_purchase", "region_use", "channel"):
            data[field] = aliases.get(data[field], data[field])
        rules = self.bundle["policy"]
        digest = json.dumps(
            [rules, self.bundle["clauses"], data], ensure_ascii=False, sort_keys=True
        ).encode()
        result = PolicyDecision(
            policy_version=rules["version"],
            fault_class=value.fault_class,
            trace_id=hashlib.sha256(digest).hexdigest()[:24],
        )
        result.missing_inputs = [
            f for f in ("region_purchase", "region_use", "channel", "purchase_date") if not data[f]
        ]
        if result.missing_inputs:
            result.needs_human = True
            result.needs_human_reasons = ["missing_inputs"]
            return result
        matches = [
            p
            for p in rules["policies"]
            if all(
                data[k] in v if isinstance(v, list) else data[k] == v
                for k, v in p["applies_to"].items()
            )
        ]
        if not matches:
            result.needs_human = True
            result.needs_human_reasons = ["no_policy_matched"]
            return result
        policy = max(matches, key=lambda p: p["priority"])
        result.matched, result.policy_id = True, policy["policy_id"]
        result.warranty_end = _add_months(value.purchase_date, policy["warranty_months"])
        result.within_warranty = value.purchase_date <= value.today <= result.warranty_end
        data.update(
            within_warranty=result.within_warranty,
            days_since_purchase=(value.today - value.purchase_date).days,
        )
        reasons = []
        if value.purchase_date > value.today:
            reasons.append("future_purchase_date")
        if value.fault_class in {"unknown", "safety"}:
            reasons.append("fault_" + value.fault_class)
        if value.dealer_authorized is False:
            reasons.append("unauthorized_dealer")
        hits = []

        def clauses(refs):
            return [
                Clause(
                    clause_id=ref,
                    policy_version=rules["version"],
                    **self.bundle["clauses"]["clauses"][ref],
                )
                for ref in refs
            ]

        for rule in policy.get("exclusions", []) + policy.get("cross_region", []):
            checks = conditions(rule["when"], data)
            if all(c.met for c in checks):
                hits.append(
                    {
                        "effect": rule["effect"],
                        "conditions": [c.model_dump() for c in checks],
                        "clauses": [c.model_dump() for c in clauses(rule.get("clauses", []))],
                    }
                )
                if rule["effect"] == "needs_human":
                    reasons.extend(rule.get("clauses", ["needs_human"]))
        no_free = any(h["effect"] == "no_free_remedy" for h in hits)
        result.needs_human = bool(reasons)
        result.needs_human_reasons = list(dict.fromkeys(reasons))
        result.exclusions_hit = hits
        for rule in policy["remedies"]:
            checks = conditions(rule["when"], data)
            eligible = all(c.met for c in checks) and not (
                no_free and rule["cost_bearer"] == "company"
            )
            result.remedies.append(
                RemedyDecision(
                    remedy=rule["remedy"],
                    eligible=eligible,
                    auto_allowed=eligible and rule["auto_allowed"] and not result.needs_human,
                    cost_bearer=rule["cost_bearer"],
                    conditions=checks,
                    clauses=clauses(rule["clauses"]),
                )
            )
        return result
