import pytest
from pydantic import ValidationError

from haike_contracts.actions import ACTION_KINDS, ActionConflict, ActionResult, parse_action
from tests.samples import ACTIONS

CONTRACT_KINDS = {
    "select_product",
    "step_feedback",
    "answer_observation",
    "confirm_receipt",
    "skip_receipt",
    "request_human",
    "new_issue",
    "resume_issue",
    "confirm_context",
    "confirm_proposal",
    "decline_proposal",
    "skip_retake",
    "rate_satisfaction",
}


def test_covers_6_kinds():
    assert set(ACTION_KINDS) == CONTRACT_KINDS and set(ACTIONS) == CONTRACT_KINDS


@pytest.mark.parametrize("kind", sorted(ACTIONS))
def test_valid_action(kind):
    valid, _, _ = ACTIONS[kind]
    assert parse_action(valid).kind == kind


@pytest.mark.parametrize("kind", sorted(ACTIONS))
def test_invalid_action(kind):
    _, invalid, _ = ACTIONS[kind]
    with pytest.raises(ValidationError):
        parse_action(invalid)


def test_card_actions_require_interrupt_and_card_id():
    valid = dict(ACTIONS["select_product"][0])
    valid.pop("input_token")
    with pytest.raises(ValidationError):
        parse_action(valid)


def test_request_human_is_global_and_payload_defaults_empty():
    a = parse_action({"action_id": "x", "expected_version": 3, "kind": "request_human"})
    assert a.input_token is None and a.payload.model_dump() == {}


def test_result_and_conflict_models():
    ActionResult(action_id="a", run_id="r", replayed=True, version_after=18)
    ActionConflict(code="stale_version", message="m", snapshot={"session_id": "s"})
    with pytest.raises(ValidationError):
        ActionConflict(code="unknown", message="m", snapshot={})
