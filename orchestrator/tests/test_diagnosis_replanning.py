"""候选重选的边界与可观测性。"""

from app.analytics.derive import node_summary
from app.diagnose.decision import decide_next
from tests.test_conversation_observation_deadlock import LIB, supplement
from tests.test_conversation_observation_revision import input_charging_state
from tests.test_diagnostic_loop import base_state


def test_observation_reselection_records_the_old_constraint_and_the_successful_level():
    state = supplement(input_charging_state(), "连接笔记本时显示 UVP", "uvp")
    state["diagnostic_decision"] = {"constrain_plans": True, "allowed_plans": []}
    state["plans_ranked"] = [{"plan_id": "pb_737_laptop_uvp", "confidence": 0.9}]
    action = decide_next(state, library=LIB)
    assert action.kind == "step"
    assert action.trace["relaxed_level"] == "observation"
    assert {"plan_id": "pb_737_laptop_uvp", "level": "strict", "reason": "diagnostic_plan_constraint"} in action.trace["skipped"]
    summary = node_summary({"next_action": action.snapshot(state)})
    assert summary["relaxed_level"] == "observation"
    assert summary["candidate_rejection_counts"]["diagnostic_plan_constraint"] == 1


def test_low_confidence_without_new_observation_does_not_authorize_an_operation():
    state = base_state(plans_ranked=[{"plan_id": "rv_power_supply", "confidence": 0.2}])
    action = decide_next(state, library=LIB)
    assert action.kind == "handoff_offer"
    assert action.reason == "knowledge_coverage_missing"
    assert action.trace["evaluated_levels"] == ["strict", "observation"]
    assert {"plan_id": "rv_power_supply", "level": "strict", "reason": "confidence_below_threshold"} in action.trace["skipped"]


def test_generic_fallback_never_bypasses_explicit_model_exclusions():
    state = input_charging_state()
    state["plans_ranked"] = [{"plan_id": "pb_input_check", "confidence": 0.9}]
    action = decide_next(state, library=LIB)
    assert action.kind != "step"
    assert {"plan_id": "pb_input_check", "level": "strict", "reason": "plan_model_mismatch"} in action.trace["skipped"]


def test_no_category_coverage_reports_the_last_evaluated_level():
    state = base_state(category="hub", product_confirmed=None, plans_ranked=[])
    action = decide_next(state, library=LIB)
    assert action.kind == "handoff_offer" and action.reason == "knowledge_coverage_missing"
    assert action.trace["relaxed_level"] == "observation"


def test_resource_constraints_remain_in_force_after_reselection():
    state = supplement(input_charging_state(), "连接笔记本时显示 UVP", "uvp")
    state = supplement(state, "设备不在身边", "missing")
    action = decide_next(state, library=LIB)
    assert action.kind == "pause"
    assert any(item["reason"] == "resource_unavailable" for item in action.trace["skipped"])


def test_admin_reselection_summary_only_stores_enumerated_reasons():
    result = node_summary({"next_action": {"trace": {
        "relaxed_level": "observation",
        "known_observations": {"private": "用户原话"},
        "skipped": [{"reason": "resource_unavailable", "quote": "用户原话"},
                    {"reason": "用户原话"}, {"reason": ["malformed"]}, "malformed"],
    }}})
    assert result == {"relaxed_level": "observation", "candidate_rejection_counts": {"resource_unavailable": 1}}
    assert node_summary({"next_action": {"trace": {"relaxed_level": "用户原话"}}}) is None
