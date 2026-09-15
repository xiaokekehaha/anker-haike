import pytest
from pydantic import ValidationError

from haike_contracts.snapshot import SessionSnapshot
from tests.samples import SNAPSHOT_FULL, mutate

REQUIRED_SECTIONS = {"active_run", "pending_input", "timeline", "last_error", "cancelled_run"}


def test_full_snapshot_roundtrip():
    s = SessionSnapshot.model_validate(SNAPSHOT_FULL)
    assert REQUIRED_SECTIONS <= set(SessionSnapshot.model_fields)
    dumped = s.model_dump(mode="json")
    assert SessionSnapshot.model_validate(dumped) == s
    assert s.pending_input.model_dump(exclude_unset=True) == SNAPSHOT_FULL["pending_input"]
    assert {i.kind for i in s.timeline} == {
        "user_message",
        "assistant_message",
        "tool",
        "product_card",
        "step_card",
        "receipt_card",
        "evidence",
        "escalation_summary",
    }


def test_idle_snapshot_minimal():
    s = SessionSnapshot(session_id="s", version=0, stage="intake")
    assert s.active_run is None and s.pending_input is None and s.timeline == []


def test_pending_input_same_shape_as_awaiting_input():
    from haike_contracts.common import PendingInput
    from haike_contracts.events import AwaitingInput

    ev_fields = set(AwaitingInput.model_fields) - {
        "type",
        "seq",
        "run_id",
        "event_id",
        "recorded_at",
    }
    assert ev_fields == set(PendingInput.model_fields)


@pytest.mark.parametrize(
    "bad",
    [
        {"stage": "thinking"},
        {"version": -1},
        {"pending_input": {"kind": "step_feedback", "card_id": "c"}},
        {"timeline": [{"kind": "banner", "text": "x"}]},
        {"active_run": {"run_id": "r"}},
    ],
)
def test_invalid_snapshots(bad):
    with pytest.raises(ValidationError):
        SessionSnapshot.model_validate(mutate(SNAPSHOT_FULL, **bad))
