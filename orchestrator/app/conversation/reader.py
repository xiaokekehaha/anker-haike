"""Read exact history by sequence, source reference or server-time interval."""

from datetime import datetime


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
