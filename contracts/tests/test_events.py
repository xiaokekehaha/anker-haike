import pytest
from pydantic import ValidationError

from haike_contracts import EVENT_TYPES
from haike_contracts.events import ServerEventAdapter, parse_event
from tests.samples import EVENTS

CONTRACT_TYPES = {
    "run_started",
    "input_received",
    "issue_changed",
    "pending_changed",
    "summary_updated",
    "ping",
    "progress",
    "tool_call",
    "message_start",
    "message",
    "message_end",
    "product_card",
    "step_card",
    "evidence",
    "receipt_card",
    "awaiting_input",
    "escalation_summary",
    "error",
    "done",
}


def test_covers_all_15_types_from_contract_section_5():
    assert set(EVENT_TYPES) == CONTRACT_TYPES
    assert len(EVENT_TYPES) == 19
    assert set(EVENTS) == CONTRACT_TYPES, "每种 type 都要有样例"


@pytest.mark.parametrize("type_", sorted(EVENTS))
def test_valid_sample_roundtrips(type_):
    valid, _, _ = EVENTS[type_]
    obj = parse_event(valid)
    assert obj.type == type_
    assert ServerEventAdapter.dump_python(obj, mode="json") == valid


@pytest.mark.parametrize("type_", sorted(EVENTS))
def test_invalid_sample_rejected(type_):
    _, invalid, _why = EVENTS[type_]
    with pytest.raises(ValidationError):
        parse_event(invalid)


def test_unknown_type_rejected():
    with pytest.raises(ValidationError):
        parse_event({"seq": 1, "run_id": "r", "type": "thinking"})


def test_seq_must_be_positive():
    with pytest.raises(ValidationError):
        parse_event({"seq": 0, "run_id": "r", "type": "ping"})


def test_step_card_step_object_nesting_and_summary_object_nesting():
    step = parse_event(EVENTS["step_card"][0])
    assert step.step.step_id == "s1" and step.step.evidence_ids == ["e1"]
    summ = parse_event(EVENTS["escalation_summary"][0])
    assert summ.summary.reason.rule_id == "R2"
    assert summ.summary.steps[0].feedback == "not_solved"
    assert summ.summary.receipt.status == "not_collected"
