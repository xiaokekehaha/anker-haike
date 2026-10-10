"""Issue-grain metrics. Missing observations remain null; submissions are not closures."""

from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

SELF_MANAGED = {"resolved", "executed_closed", "consult_answered"}
TERMINAL = SELF_MANAGED | {"escalated", "closed_unresolved", "abandoned", "human_executed"}

# The live dashboard and retention snapshot use the same final metric projection.
METRIC_ROWS_SQL = """select e.episode_id,e.session_id,e.issue_id,e.case_id,e.source,e.updated_at,
    coalesce(r.score,e.rating) as rating,
    coalesce((select case when 'intent_wrong'=any(a.reason_tags) then false
        when 'intent_correct'=any(a.reason_tags) then true end
        from analytics.cases a where a.session_id=e.session_id order by a.labeled_at desc limit 1),e.intent_correct) as intent_correct,
    h.human_involved,
    case when c.status='closed' then case when h.human_involved then 'human_executed' else 'executed_closed' end
        when c.status='closed_unresolved' then 'closed_unresolved'
        when c.status='escalated_summary' then 'escalated'
        when c.status in ('awaiting_approval','approved','rejected') then 'awaiting_human'
        when c.case_id is not null then 'in_progress' else e.outcome end as outcome
    from service_episodes e left join satisfaction_ratings r using(session_id,issue_id)
    left join cases c on c.case_id=e.case_id
    cross join lateral (select e.human_involved
        or exists(select 1 from case_events ce where ce.case_id=c.case_id and ce.actor like 'agent:%%')
        or exists(select 1 from human_decisions hd where hd.case_id=c.case_id) as human_involved) h
"""


def episode(values, case=None):
    from app.analytics.derive import classify

    outcome, _ = classify(values, done_reason="completed", pending=bool(values.get("pending_card")))
    human = bool(case and case.get("decisions")) or values.get("human_involved", False)
    if case:
        human = human or any(e.get("actor", "").startswith("agent:") for e in case.get("events", []))
        if case["status"] == "closed":
            outcome = "human_executed" if human else "executed_closed"
        elif case["status"] == "closed_unresolved":
            outcome = "closed_unresolved"
        elif case["status"] == "escalated_summary":
            outcome = "escalated"
        elif case["status"] in {"awaiting_approval", "approved", "rejected"}:
            outcome = "awaiting_human"
        else:
            outcome = "in_progress"
    sid, iid = values["session_id"], values["active_issue_id"]
    return {
        "episode_id": str(uuid5(NAMESPACE_URL, f"{sid}:{iid}:episode")),
        "session_id": sid,
        "issue_id": iid,
        "case_id": values.get("case_id"),
        "outcome": outcome,
        "human_involved": human,
        "source": values.get("evaluation_source", "live"),
        "updated_at": datetime.now(UTC).isoformat(),
    }


def metrics(rows, *, now=None, abandoned_hours=24):
    now = now or datetime.now(UTC)
    live = [dict(r) for r in rows if r.get("source", "live") == "live"]
    for row in live:
        at = row.get("updated_at")
        at = datetime.fromisoformat(at) if isinstance(at, str) else at
        if (
            row["outcome"] in {"in_progress", "awaiting_user", "clarifying"}
            and not row.get("case_id")
            and at
            and now - at > timedelta(hours=abandoned_hours)
        ):
            row["outcome"] = "abandoned"
    terminal = [r for r in live if r["outcome"] in TERMINAL]
    managed = sum(r["outcome"] in SELF_MANAGED and not r.get("human_involved") for r in terminal)
    rated = [r for r in live if r.get("rating") is not None]
    labeled = [r for r in live if r.get("intent_correct") is not None]
    return {
        "episodes": len(live),
        "terminal": len(terminal),
        "managed": managed,
        "managed_rate": managed / len(terminal) if terminal else None,
        "rated": len(rated),
        "rating_coverage": len(rated) / len(live) if live else None,
        "nss": (sum(r["rating"] >= 4 for r in rated) - sum(r["rating"] <= 2 for r in rated))
        / len(rated)
        if rated
        else None,
        "intent_labeled": len(labeled),
        "intent_accuracy": sum(r["intent_correct"] for r in labeled) / len(labeled)
        if labeled
        else None,
    }
