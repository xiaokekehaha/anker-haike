"""Validate the whole bundle before atomically replacing the cached policy."""

from copy import deepcopy
from pathlib import Path

import yaml
from haike_contracts.common import REMEDY_LADDER

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

# demo = 虚构演示；public_site = 公开售后政策页；sop = 内部 SOP。
# 非 demo 的来源必须逐条给出 url / fetched_at / quote，否则条款无法回链，用户可见文本不能引用。
SOURCES = {"demo", "public_site", "sop"}

REQUIRED_SCOPE = {"category", "region_purchase", "channel"}
OPTIONAL_SCOPE = {"series_pattern", "part_class"}

# 正整数月数，或终身保（Anker 多款线材），或明确不保（eufy 部分配件）。
SPECIAL_TERMS = {"lifetime", "none"}


class ConfigError(ValueError):
    pass


def _as_set(value) -> set:
    if value is None:
        return set()
    return set(value) if isinstance(value, list) else {value}


def _scope_overlap(a: dict, b: dict) -> bool:
    """两条规则是否可能命中同一次请求。

    缺省的可选键表示「匹配全部」，所以一边缺省就一定相交；品类兜底与系列特例正是这种关系，
    它们靠 priority 分先后，不算冲突。
    """
    if a["category"] != b["category"]:
        return False
    if not set(a["region_purchase"]) & set(b["region_purchase"]):
        return False
    if not set(a["channel"]) & set(b["channel"]):
        return False
    for key in OPTIONAL_SCOPE:
        left, right = _as_set(a.get(key)), _as_set(b.get(key))
        if left and right and not left & right:
            return False
    return True


def validate(bundle: dict) -> dict:
    policy, clauses = bundle["policy"], bundle["clauses"]["clauses"]
    if policy.get("source") not in SOURCES or not policy.get("version"):
        raise ConfigError(f"政策必须声明 version 与来源（{'/'.join(sorted(SOURCES))}）")
    cited = policy["source"] != "demo"
    ids = set()
    policies = policy["policies"]
    for index, item in enumerate(policies):
        if item["policy_id"] in ids:
            raise ConfigError("重复 policy_id")
        ids.add(item["policy_id"])
        scope = item["applies_to"]
        if not REQUIRED_SCOPE <= set(scope) or set(scope) - REQUIRED_SCOPE - OPTIONAL_SCOPE:
            raise ConfigError(
                f"applies_to 必须含 {'/'.join(sorted(REQUIRED_SCOPE))}，"
                f"可选 {'/'.join(sorted(OPTIONAL_SCOPE))}"
            )
        months = item["warranty_months"]
        if months not in SPECIAL_TERMS and not (isinstance(months, int) and months > 0):
            raise ConfigError(f"warranty_months 必须为正整数或 {'/'.join(sorted(SPECIAL_TERMS))}")
        source = item.get("source") or {}
        if cited and not all(source.get(f) for f in ("url", "fetched_at", "quote")):
            raise ConfigError(f"{item['policy_id']} 缺 source.url / fetched_at / quote")
        for prior in policies[:index]:
            if _scope_overlap(scope, prior["applies_to"]) and item["priority"] == prior["priority"]:
                raise ConfigError("交叠政策 priority 冲突")
        for rule in item["remedies"] + item.get("exclusions", []) + item.get("cross_region", []):
            if set(rule.get("when", {})) - CONDITIONS:
                raise ConfigError("未知政策条件")
            if any(ref not in clauses for ref in rule.get("clauses", [])):
                raise ConfigError("条款引用不存在")
            if rule.get("auto_allowed") and (
                rule.get("remedy") in {"refund", "paid_repair"}
                or rule.get("cost_bearer") != "company"
            ):
                raise ConfigError("自动办理只允许公司承担的非退款方案")
            if "remedy" in rule and (
                rule["remedy"] not in REMEDY_LADDER or not rule.get("clauses")
            ):
                raise ConfigError("非法方案或方案缺条款")
            if "effect" in rule and rule["effect"] not in {
                "allow",
                "needs_human",
                "no_free_remedy",
            }:
                raise ConfigError("非法 effect")
    if cited:
        missing = [ref for ref in clauses if not clauses[ref].get("source_url")]
        if missing:
            raise ConfigError(f"引用真实来源时条款必须带 source_url：{missing[:3]}")
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
