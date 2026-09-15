"""One-time import of checkpoints written before BusinessContext existed."""

from app.actions.params import changes_order, extract_params


def restore_legacy_params(state: dict) -> dict:
    """Resolve one issue's current business subject without asking the model to copy IDs.

    An explicit identifier replaces the previous subject as a whole. Short follow-ups
    inherit it; a new subject without an identifier deliberately clears that reference.
    History is only a recovery source for checkpoints created before subject persistence.
    """
    text = state.get("text", "")
    explicit = extract_params(text)
    if explicit:
        return explicit
    if changes_order(text):
        return {}
    for source in (state.get("consult_params"), state.get("last_consult_params")):
        if source:
            return dict(source)
    # Do not resurrect a previous subject after the user asked for another order.
    history = sorted(state.get("history", []), key=lambda e: e.get("first_seq", 0), reverse=True)
    historical = {}
    for entry in history:
        if (
            entry.get("entry_id") == state.get("input_id")
            or entry.get("issue_id") != state.get("active_issue_id")
            or entry.get("role") != "user"
            or entry.get("kind") != "message"
            or entry.get("processing_status") in {"failed", "cancelled"}
        ):
            continue
        prior = entry.get("text", "")
        historical = extract_params(prior)
        if historical:
            break
        if changes_order(prior):
            return {}
    receipt = state.get("receipt") or {}
    execution = (state.get("execution") or {}).get("receipt") or {}
    if execution.get("service_order_no"):
        return {k: execution[k] for k in ("order_no", "service_order_no") if execution.get(k)}
    if receipt.get("status") == "order_verified" and (receipt.get("fields") or {}).get("order_no"):
        return {"order_no": receipt["fields"]["order_no"]}
    return historical
