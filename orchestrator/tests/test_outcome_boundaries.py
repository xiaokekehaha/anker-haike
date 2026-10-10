"""Closure, a prepared summary and a real human decision are different facts."""

from datetime import UTC, datetime, timedelta

import pytest

from app.analytics.derive import classify, session_facts
from app.analytics.l3 import episode, metrics
from app.analytics.queries import _rates
from app.cases.service import CaseService
from app.cases.store import PostgresCaseStore
from app.conversation.reply import fallback_reply
from app.escalation.summary import reassurance_text
from tests.test_l3_postgres import l3_pool as l3_pool_fixture

l3_pool = l3_pool_fixture


@pytest.mark.parametrize("status,outcome", [
    ("closed_unresolved", "closed_unresolved"), ("escalated_summary", "escalated"),
    ("awaiting_approval", "awaiting_human"), ("closed", "executed_closed"),
])
def test_case_state_overrides_stale_answer_closing_and_summary(status, outcome):
    state = {"session_id": "s", "active_issue_id": "i", "case_status": status, "stage": "done",
             "consult_answered": True, "visible_messages": [{"kind": "closing"}], "escalation_summary": {"old": True}}
    assert classify(state, done_reason="completed")[0] == outcome
    result = episode(state, {"status": status})
    assert result["outcome"] == outcome and not result["human_involved"]
    now = datetime.now(UTC)
    facts = session_facts("s", state, lane=None, done_reason="completed", error_code=None,
                          pending=False, runs=1, created_at=now, last_run_at=now)
    assert (facts.outcome_at is not None) is (outcome != "awaiting_human")


def test_unresolved_closure_counts_as_terminal_but_never_managed():
    result = metrics([{"outcome": "resolved"}, {"outcome": "closed_unresolved"}, {"outcome": "awaiting_human"}])
    assert result["terminal"] == 2 and result["managed"] == 1 and result["managed_rate"] == 0.5
    assert _rates({"resolved": 1, "closed_unresolved": 1}) == {"self_service": 0.5, "closure": 0.5, "escalation": 0.0}
    assert episode({"session_id": "s", "active_issue_id": "i"}, {
        "status": "closed_unresolved", "events": [{"actor": "agent:reviewer"}],
    })["human_involved"]


@pytest.mark.parametrize("status,outcome", [
    ("closed_unresolved", "closed_unresolved"), ("escalated_summary", "escalated"),
    ("awaiting_approval", "awaiting_human"), ("closed", "executed_closed"),
])
async def test_real_metric_sql_uses_current_case_not_stale_episode(l3_pool, status, outcome):
    service = CaseService(PostgresCaseStore(l3_pool))
    row = await service.open("projection-session", "issue", {})
    value = {"session_id": "projection-session", "active_issue_id": "issue", "case_id": row["case_id"]}
    await service.store.record_episode(episode(value, row))
    # Only a fixture row in the isolated project test schema is changed here.
    async with l3_pool.connection() as conn:
        await conn.execute("update cases set status=%s where case_id=%s", (status, row["case_id"]))
    projected = (await service.store.metric_rows(datetime.now(UTC) - timedelta(days=1)))[0]
    assert projected["outcome"] == outcome and not projected["human_involved"]
    assert projected["outcome"] == episode(value, {"status": status})["outcome"]


def test_reply_distinguishes_prepared_and_submitted_without_claiming_capability():
    base = {"active_issue_id": "i", "turn_decision": {"primary_intent": "handoff_status"},
            "issues": {"i": {"handoff": {"status": "prepared"}}}}
    prepared = fallback_reply(base)
    queued = fallback_reply({**base, "case_id": "c", "case_status": "awaiting_approval"})
    assert "don't have confirmation" in prepared and "does not mean an agent" in prepared
    assert "submitted" in queued and "awaiting review" in queued and "can't confirm" in queued
    complaint = fallback_reply({"turn_decision": {"primary_intent": "complaint"}})
    for text in [prepared, queued, complaint, reassurance_text("R3"), reassurance_text("R2", {
        "next_action": {"kind": "handoff_offer", "reason": "no_supported_followup", "compat_rule": "R2"},
    })]:
        assert "connected yet" not in text
