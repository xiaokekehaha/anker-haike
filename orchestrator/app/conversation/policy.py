"""Preserve restrictions from accepted but uncommitted hazardous reports."""

from app.conversation.reduce import stable_id


def restrict_operations(state: dict, *, source_kind: str, quote: str) -> dict:
    """Persist a late risk checkpoint with its issue and source, beyond this run."""
    issue_id = state.get("active_issue_id")
    issue = (state.get("issues") or {}).get(issue_id, {})
    risk = {
        "risk_id": stable_id(state.get("input_id"), source_kind, "risk"),
        "rule_id": "R4",
        "status": "reported",
        "source_kind": source_kind,
        "quote": quote,
        "source_input_ids": [state.get("input_id")],
        "reported_at": state.get("at"),
        "issue_id": issue_id,
        "device_ref_id": (issue.get("device_ref") or {}).get("device_ref_id"),
        "restriction": "no_operations",
        "policy_version": "2026-09-13",
        "last_evidence_seq": state.get("input_seq"),
    }
    risks = [r for r in state.get("risk_cases", []) if r["risk_id"] != risk["risk_id"]]
    return {
        "risk_cases": [*risks, risk],
        "turn_decision": {
            **state.get("turn_decision", {}),
            "allowed_operations": False,
            "escalation_trigger": "R4",
        },
        "context_revision": state.get("context_revision", 0) + 1,
    }


def pending_risk_sources(state, rules):
    known = {
        source
        for risk in state.get("risk_cases", [])
        for source in risk.get("source_input_ids", [])
    }
    risks = []
    for entry in state.get("history", []):
        if (
            entry["role"] != "user"
            or entry.get("processing_status") not in {"failed", "cancelled"}
            or entry["entry_id"] in known
        ):
            continue
        check = rules.check_in(text=entry.get("text"), session_id=state.get("session_id"))
        if any(hit.rule_id == "R4" for hit in check.hits):
            risks.append(
                {
                    "risk_id": stable_id(entry["entry_id"], "unprocessed-risk"),
                    "rule_id": "R4",
                    "status": "disputed",
                    "source_input_ids": [entry["entry_id"]],
                    "reported_at": entry.get("received_at"),
                    "issue_id": None,
                    "device_ref_id": None,
                    "restriction": "no_operations",
                    "policy_version": "2026-09-13",
                    "last_evidence_seq": entry["first_seq"],
                }
            )
    return risks
