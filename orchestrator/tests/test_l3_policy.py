from copy import deepcopy
from datetime import date

import pytest
import yaml

from app.policy.engine import PolicyEngine
from app.policy.loader import ConfigError, PolicyLoader, validate
from app.policy.models import PolicyInput
from app.settings import REPO_ROOT

CASES = yaml.safe_load((REPO_ROOT / "data/eval/policy/cases.yaml").read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_decision_table(case):
    engine = PolicyEngine()
    value = PolicyInput.model_validate(case["input"])
    result = engine.decide(value)
    expected = case["expected"]
    assert result == engine.decide(value), "same inputs must replay identically"
    assert result.needs_human == expected["needs_human"]
    assert (
        any(r.remedy == "replace" and r.auto_allowed for r in result.remedies)
        == expected["replace_auto"]
    )
    if expected.get("paid_repair"):
        assert any(
            r.remedy == "repair" and r.eligible and r.cost_bearer == "customer"
            for r in result.remedies
        )
    if expected.get("missing"):
        assert expected["missing"] in result.missing_inputs
    for remedy in result.remedies:
        assert not remedy.auto_allowed or (
            remedy.eligible and remedy.cost_bearer == "company" and not result.needs_human
        )
        assert remedy.clauses


@pytest.mark.parametrize("change", ["clause", "priority", "refund", "condition"])
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
        policy["remedies"][2]["auto_allowed"] = True
    else:
        policy["remedies"][0]["when"]["invented"] = True
    with pytest.raises(ConfigError):
        validate(bundle)


def test_month_boundary_and_leap_day():
    value = PolicyInput.model_validate(CASES[0]["input"]).model_copy(
        update={"purchase_date": date(2024, 2, 29), "today": date(2025, 2, 28)}
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
