"""Bounded, numeric context diagnostics attached to each node execution."""

from collections.abc import Mapping

_events: dict[str, dict[str, list[dict[str, object]]]] = {}


def observe_context(event: str, data: Mapping[str, object], node: str | None) -> None:
    run_id = data.get("run_id")
    if not isinstance(run_id, str) or not node:
        return
    metric: dict[str, object] = {"event": event, "task": data.get("task")}
    if event in {"context_built", "context_budget"}:
        for key in ("tokens", "required_tokens", "max_tokens", "omitted_entries"):
            value = data.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                metric[key] = value
        for key in ("token_breakdown", "authority_tokens"):
            value = data.get(key)
            if isinstance(value, dict):
                metric[key] = {k: v for k, v in value.items() if isinstance(v, int)}
        metric["truncated"] = bool(data.get("truncation"))
        metric["cache_dropped"] = "historical_excerpts_cache" in (data.get("omitted_sections") or [])
    elif event == "model_call":
        metric["model"] = data.get("model_used")
        usage = data.get("usage")
        if isinstance(usage, dict) and isinstance(usage.get("input_tokens"), int):
            metric["actual_input_tokens"] = usage["input_tokens"]
        attempts = data.get("attempts")
        if isinstance(attempts, list):
            metric["attempts"] = [
                {k: a[k] for k in ("alias", "outcome", "estimated_input_tokens", "input_budget") if k in a}
                for a in attempts if isinstance(a, dict)
            ]
    else:
        return
    if run_id not in _events and len(_events) >= 500:
        _events.clear()
    bucket = _events.setdefault(run_id, {}).setdefault(node, [])
    if len(bucket) < 40:
        bucket.append(metric)


def take_context_events(run_id: str, node: str) -> list[dict[str, object]]:
    return _events.get(run_id, {}).pop(node, [])


def clear_context_events(run_id: str) -> None:
    _events.pop(run_id, None)
