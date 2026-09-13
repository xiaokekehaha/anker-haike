"""Read exact history by sequence, source reference or server-time interval."""

from datetime import datetime


def read_history_for_turn(state: dict, request: dict) -> dict:
    """Resolve a follow-up against the immediately preceding successful recall.

    A model's self-reference is a target-resolution error, not missing storage.
    Only a single prior exchange can repair it; never relax the sequence cutoff.
    """
    entries = state.get("history", [])
    before_seq = state["input_seq"]
    mode = request.get("mode", "recent")
    ids = request.get("source_entry_ids") or []
    self_reference = mode == "reference" and set(ids) == {state["input_id"]}
    unresolved = {
        "source_entry_ids": [],
        "error": "您想回顾哪条问题的回答？请指出那条问题或时间范围。",
        "error_code": "history_target_unresolved",
    }
    if mode == "follow_up" and ids:
        return unresolved
    effective_request = request
    if mode == "follow_up" or self_reference:
        previous = state.get("turn_decision") or {}
        prior_inputs = [
            e
            for e in entries
            if e["first_seq"] < before_seq
            and e["role"] == "user"
            and e["kind"] in {"message", "action"}
        ]
        last_input = max(prior_inputs, key=lambda e: e["first_seq"], default=None)
        if (
            not last_input
            or previous.get("input_id") != last_input["entry_id"]
            or previous.get("primary_intent") != "history_query"
            or previous.get("clarification")
            or not state.get("recall_entry_ids")
        ):
            return unresolved
        effective_request = {"mode": "reference", "source_entry_ids": state["recall_entry_ids"]}
        prior = select_history(entries, effective_request, before_seq=last_input["first_seq"])
        runs = {e["run_id"] for e in entries if e["entry_id"] in prior["source_entry_ids"]}
        if prior["error"] or len(runs) != 1:
            return unresolved
    selection = select_history(entries, effective_request, before_seq=before_seq)
    if effective_request.get("mode") == "reference" and (
        selection.get("missing_ids") or not effective_request.get("source_entry_ids")
    ):
        return unresolved
    return {
        **selection,
        "resolved_request": effective_request,
        "resolution": "previous_recall" if mode == "follow_up" or self_reference else "explicit",
    }


def select_history(
    entries: list[dict], request: dict, *, before_seq: int, max_entries: int = 48
) -> dict:
    candidates = [e for e in entries if e["first_seq"] < before_seq]
    mode = request.get("mode", "recent")
    missing = []
    if mode == "first":
        first = next(
            (e for e in candidates if e["role"] == "user" and e["kind"] == "message"), None
        )
        selected = [e for e in candidates if first and e["run_id"] == first["run_id"]]
    elif mode == "reference":
        ids = request.get("source_entry_ids") or []
        found = [e for e in candidates if e["entry_id"] in ids]
        runs = {e["run_id"] for e in found}
        selected = [e for e in candidates if e["run_id"] in runs]
        missing = [iid for iid in ids if not any(e["entry_id"] == iid for e in found)]
    elif mode == "time_range":
        try:
            start, end = (datetime.fromisoformat(request[key]) for key in ("from_time", "to_time"))
            if start.tzinfo is None or end.tzinfo is None or start > end:
                raise ValueError("ambiguous time")
            selected = [
                e
                for e in candidates
                if e.get("recorded_at") and start <= datetime.fromisoformat(e["recorded_at"]) <= end
            ]
        except (ValueError, TypeError, KeyError):
            return {"source_entry_ids": [], "error": "请说明要回顾的日期或时间范围。"}
    else:
        runs = list(dict.fromkeys(e["run_id"] for e in candidates))[-6:]
        selected = [e for e in candidates if e["run_id"] in runs]
    if len(selected) > max_entries:
        return {"source_entry_ids": [], "error": "这段历史较长，请缩小要回顾的问题或时间范围。"}
    return {
        "source_entry_ids": [e["entry_id"] for e in selected],
        "missing_ids": missing,
        "error": "这部分原始记录目前不可用，无法确认当时的原话。"
        if not selected or missing
        else None,
    }
