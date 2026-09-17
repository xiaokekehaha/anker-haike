from copy import deepcopy
from datetime import date

import pytest
import yaml
from haike_contracts.common import REMEDY_LADDER

from app.policy.engine import PolicyEngine
from app.policy.loader import ConfigError, PolicyLoader, validate
from app.policy.models import PolicyInput
from app.settings import REPO_ROOT

CASES = yaml.safe_load((REPO_ROOT / "data/eval/policy/cases.yaml").read_text())["cases"]


def _auto(result, remedy: str) -> bool:
    return any(r.remedy == remedy and r.auto_allowed for r in result.remedies)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_decision_table(case):
    engine = PolicyEngine()
    value = PolicyInput.model_validate(case["input"])
    result = engine.decide(value)
    expected = case["expected"]
    assert result == engine.decide(value), "same inputs must replay identically"
    assert result.needs_human == expected["needs_human"]
    assert _auto(result, "replace") == expected["replace_auto"]
    assert _auto(result, "parts") == expected["parts_auto"]
    if expected.get("paid_repair"):
        assert any(r.remedy == "paid_repair" and r.eligible for r in result.remedies)
    if expected.get("missing"):
        assert expected["missing"] in result.missing_inputs
    if expected.get("reason"):
        assert expected["reason"] in result.needs_human_reasons
    if expected.get("policy_id"):
        assert result.policy_id == expected["policy_id"]
    if "within_warranty" in expected:
        assert result.within_warranty == expected["within_warranty"]
    if "warranty_end" in expected:
        end = expected["warranty_end"]
        assert result.warranty_end == (date.fromisoformat(end) if end else None)
    for remedy in result.remedies:
        assert not remedy.auto_allowed or (
            remedy.eligible and remedy.cost_bearer == "company" and not result.needs_human
        )
        assert remedy.clauses


def test_every_catalog_category_resolves_or_says_why():
    """目录里的每个品类要么给出带条款的处置，要么明说为什么给不出——不允许静默落空。"""
    from app.catalog import ProductCatalog
    from app.settings import settings

    catalog = ProductCatalog.from_yaml(settings.catalog_config_path)
    engine = PolicyEngine()
    sample = {}
    for product in catalog.products:
        sample.setdefault(product.category, product.sku)
    assert len(sample) == 20, "目录品类数变了，金标需要同步"
    for category, sku in sample.items():
        result = engine.decide(
            PolicyInput(
                sku=sku,
                category=category,
                region_purchase="US",
                region_use="US",
                channel="official_store",
                purchase_date=date(2026, 8, 1),
                fault_class="quality",
                today=date(2026, 9, 17),
            )
        )
        if result.needs_human:
            assert result.needs_human_reasons, category
        else:
            assert _auto(result, "parts"), f"{category} 在保质量问题应能自动寄配件"


def test_proposal_ladder_puts_parts_first():
    """官方处置阶梯：寄配件在最前，退款在后。propose 按这个顺序出选项。"""
    assert REMEDY_LADDER.index("parts") < REMEDY_LADDER.index("repair")
    assert REMEDY_LADDER.index("repair") < REMEDY_LADDER.index("replace")
    assert REMEDY_LADDER.index("replace") < REMEDY_LADDER.index("refund")


@pytest.mark.parametrize(
    "change", ["clause", "priority", "refund", "condition", "scope", "months", "source"]
)
def test_reject_invalid_policy(change):
    bundle = PolicyLoader().load()
    policy = bundle["policy"]["policies"][0]
    if change == "clause":
        policy["remedies"][0]["clauses"] = ["missing"]
    elif change == "priority":
        other = deepcopy(policy)
        other["policy_id"] = "overlapping"
        bundle["policy"]["policies"].append(other)
    elif change == "refund":
        next(r for r in policy["remedies"] if r["remedy"] == "refund")["auto_allowed"] = True
    elif change == "scope":
        policy["applies_to"]["invented_key"] = "x"
    elif change == "months":
        policy["warranty_months"] = "forever"
    elif change == "source":
        policy["source"].pop("url")
    else:
        policy["remedies"][0]["when"]["invented"] = True
    with pytest.raises(ConfigError):
        validate(bundle)


def test_category_fallback_and_series_override_may_share_scope():
    """品类兜底与系列特例必然交叠，靠 priority 分先后，不该被判成冲突。"""
    bundle = PolicyLoader().load()
    assert validate(bundle) is bundle


def test_month_boundary_and_leap_day():
    value = PolicyInput(
        sku="EUFY-X10-PRO-OMNI",
        category="robot_vacuum",
        region_purchase="US",
        region_use="US",
        channel="official_store",
        purchase_date=date(2024, 2, 29),
        fault_class="quality",
        today=date(2025, 2, 28),
    )
    result = PolicyEngine().decide(value)
    assert result.warranty_end == date(2025, 2, 28)
    assert result.within_warranty
    assert (
        not PolicyEngine()
        .decide(value.model_copy(update={"today": date(2025, 3, 1)}))
        .within_warranty
    )


def test_loader_reloads_and_does_not_publish_invalid_bundle(tmp_path):
    for name in ("warranty_policy.yaml", "clauses.yaml", "regions.yaml"):
        (tmp_path / name).write_text((REPO_ROOT / "config/policy" / name).read_text())
    loader = PolicyLoader(tmp_path)
    bundle = loader.load()
    bundle["policy"]["version"] = "next"
    (tmp_path / "warranty_policy.yaml").write_text(yaml.safe_dump(bundle["policy"]))
    assert loader.load()["policy"]["version"] == "next"
    bundle["policy"]["policies"][0]["remedies"][0]["clauses"] = ["invalid"]
    (tmp_path / "warranty_policy.yaml").write_text(yaml.safe_dump(bundle["policy"]))
    with pytest.raises(ConfigError):
        loader.load()
    assert loader._bundle["policy"]["version"] == "next"
