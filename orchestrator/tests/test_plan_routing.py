"""路由观察必须在声明计划的每个产品范围内有显式承接者。"""

import copy

import pytest
import yaml

from app.plans import PlanLibrary, PlansError, load_plans_config
from app.settings import REPO_ROOT


@pytest.fixture
def config():
    return yaml.safe_load((REPO_ROOT / "config/plans.yaml").read_text())


def load(tmp_path, config):
    path = tmp_path / "plans.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True))
    return load_plans_config(path)


def plan(config, plan_id):
    return next(p for p in config["plans"] if p["plan_id"] == plan_id)


def test_actual_routes_accept_cross_symptom_observations_and_record_only_questions(tmp_path, config):
    library = PlanLibrary(load(tmp_path, config))
    assert "pb_no_input" not in library.get("pb_737_laptop_uvp").symptom_codes
    assert "dock_power_light" in library.observation_definitions()


@pytest.mark.parametrize("failure", ["missing", "wrong_sku", "excluded_sku", "latest_version", "unrelated"])
def test_route_without_an_applicable_explicit_consumer_is_rejected(tmp_path, config, failure):
    consumer = plan(config, "pb_737_laptop_uvp")
    if failure == "missing":
        config["plans"].remove(consumer)
    elif failure == "wrong_sku":
        consumer["applies_to"]["sku_list"] = ["OTHER-MODEL"]
    elif failure == "excluded_sku":
        consumer["applies_to"] = {"scope": "category_generic", "category": "power_bank", "excluded_skus": ["ANKER-A1289"]}
    elif failure == "latest_version":
        newer = copy.deepcopy(consumer)
        newer["version"] += 1
        newer["requires_observations"][0]["option_ids"] = ["normal"]
        config["plans"].append(newer)
    else:
        consumer["requires_observations"] = []
    with pytest.raises(PlansError, match="pb_737_display=laptop_uvp"):
        load(tmp_path, config)


def test_sku_intersection_is_not_enough_to_cover_every_model(tmp_path, config):
    plan(config, "pb_737_output_check")["applies_to"]["sku_list"].append("OTHER-MODEL")
    with pytest.raises(PlansError, match="OTHER-MODEL"):
        load(tmp_path, config)


def test_multiple_consumers_can_jointly_cover_the_declared_skus(tmp_path, config):
    for pid in ["pb_737_output_check", "pb_737_display_reset", "pb_737_laptop_uvp"]:
        other = copy.deepcopy(plan(config, pid))
        other["plan_id"] += "_other"
        other["applies_to"]["sku_list"] = ["OTHER-MODEL"]
        config["plans"].append(other)
    plan(config, "pb_737_output_check")["applies_to"]["sku_list"].append("OTHER-MODEL")
    load(tmp_path, config)


def test_generic_question_needs_a_route_for_unconfirmed_models(tmp_path, config):
    plan(config, "pb_737_output_check")["applies_to"] = {"scope": "category_generic", "category": "power_bank"}
    with pytest.raises(PlansError, match="category_only"):
        load(tmp_path, config)


def test_generic_consumers_cannot_hide_a_gap_at_an_excluded_sku(tmp_path, config):
    for pid in ["pb_737_output_check", "pb_737_display_reset", "pb_737_laptop_uvp"]:
        plan(config, pid)["applies_to"] = {"scope": "category_generic", "category": "power_bank"}
    plan(config, "pb_737_laptop_uvp")["applies_to"]["excluded_skus"] = ["OTHER-MODEL"]
    with pytest.raises(PlansError, match="OTHER-MODEL"):
        load(tmp_path, config)
