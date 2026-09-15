"""Validate the whole bundle before atomically replacing the cached policy."""

from copy import deepcopy
from pathlib import Path

import yaml

from app.settings import CONFIG_DIR

CONDITIONS = {
    "fault_class",
    "within_warranty",
    "days_since_purchase_lte",
    "not_prior",
    "channel",
    "region_use_in",
    "region_use_not_in",
}


class ConfigError(ValueError):
    pass


def validate(bundle: dict) -> dict:
    policy, clauses = bundle["policy"], bundle["clauses"]["clauses"]
    if policy.get("source") != "demo" or not policy.get("version"):
        raise ConfigError("政策必须声明 demo 来源与 version")
    ids = set()
    policies = policy["policies"]
    for index, item in enumerate(policies):
        if item["policy_id"] in ids:
            raise ConfigError("重复 policy_id")
        ids.add(item["policy_id"])
        if set(item["applies_to"]) != {"category", "region_purchase", "channel"}:
            raise ConfigError("applies_to 必须包含 category/region_purchase/channel")
        if not isinstance(item["warranty_months"], int) or item["warranty_months"] <= 0:
            raise ConfigError("warranty_months 必须为正整数")
        for prior in policies[:index]:
            a, b = item["applies_to"], prior["applies_to"]
            overlap = (
                a["category"] == b["category"]
                and bool(set(a["region_purchase"]) & set(b["region_purchase"]))
                and bool(set(a["channel"]) & set(b["channel"]))
            )
            if overlap and item["priority"] == prior["priority"]:
                raise ConfigError("交叠政策 priority 冲突")
        for rule in item["remedies"] + item.get("exclusions", []) + item.get("cross_region", []):
            if set(rule.get("when", {})) - CONDITIONS:
                raise ConfigError("未知政策条件")
            if any(ref not in clauses for ref in rule.get("clauses", [])):
                raise ConfigError("条款引用不存在")
            if rule.get("auto_allowed") and (
                rule.get("remedy") == "refund" or rule.get("cost_bearer") != "company"
            ):
                raise ConfigError("自动办理只允许公司承担的非退款方案")
            if "remedy" in rule and (
                rule["remedy"] not in {"repair", "replace", "refund"} or not rule.get("clauses")
            ):
                raise ConfigError("非法方案或方案缺条款")
            if "effect" in rule and rule["effect"] not in {
                "allow",
                "needs_human",
                "no_free_remedy",
            }:
                raise ConfigError("非法 effect")
    return bundle


class PolicyLoader:
    def __init__(self, directory: Path | str = CONFIG_DIR / "policy"):
        self.directory = Path(directory)
        self._stamp = None
        self._bundle = None

    def load(self) -> dict:
        paths = [
            self.directory / name
            for name in ("warranty_policy.yaml", "clauses.yaml", "regions.yaml")
        ]
        stamp = tuple((p.stat().st_mtime_ns, p.stat().st_size) for p in paths)
        if stamp != self._stamp:
            bundle = dict(
                zip(
                    ("policy", "clauses", "regions"), [yaml.safe_load(p.read_text()) for p in paths]
                )
            )
            self._bundle = validate(bundle)
            self._stamp = stamp
        return deepcopy(self._bundle)
