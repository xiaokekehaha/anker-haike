"""Portable identity for recorded context; never a live model-response cache.

An offline replay reproduces answers at the recorded time. Runtime clock fields
do not identify the scenario; user-reported dates and text remain exact. Only
structured reference fields are rebound, never arbitrary strings or UUIDs.
"""

from app.context.messages import ContextMessages

REFERENCE_FIELDS = frozenset(
    {
        "session_id",
        "case_id",
        "run_id",
        "input_id",
        "entry_id",
        "issue_id",
        "active_issue_id",
        "target_issue_id",
        "device_ref_id",
        "fact_id",
        "pending_id",
        "card_id",
        "input_token",
        "reply_to_input_id",
        "opened_by_input_id",
        "superseded_by_input_id",
        "supersedes",
        "risk_id",
        "task_id",
        "target_task_id",
        "source_entry_ids",
        "source_event_ids",
        "source_ids",
        "source_refs",
        "selected_entry_ids",
        "last_input_id",
        "references",
    }
)
CLOCK_FIELDS = frozenset(
    {
        "now",
        "ts",  # ExecutedStep timestamp is recorded by the runner, not user fact time.
        "at",
        "recorded_at",
        "received_at",
        "started_at",
        "completed_at",
        "created_at",
        "updated_at",
        "opened_at",
        "requested_at",
        "accepted_at",
    }
)


def _walk(value, replace, *, key="", clocks=False):
    if isinstance(value, dict):
        return {k: _walk(v, replace, key=k, clocks=clocks) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_walk(v, replace, key=key, clocks=clocks) for v in value]
    if isinstance(value, str) and key in REFERENCE_FIELDS:
        return replace(value)
    if clocks and key in CLOCK_FIELDS and value is not None:
        return {"recorded_clock": True}
    return value


def context_identity(messages):
    if not isinstance(messages, ContextMessages):
        return None, {}
    references = {}

    def alias(value):
        if value not in references:
            references[value] = f"ref:{len(references)}"
        return {"context_ref": references[value]}

    sections = []
    for section in messages.sections:
        sections.append(
            {
                key: _walk(value, alias, clocks=True)
                if key in {"authority", "metadata", "payload"}
                else value
                for key, value in section.items()
            }
        )
    return sections, references


def rebind_output(output, recorded_refs, current_refs):
    current_values = {alias: value for value, alias in current_refs.items()}

    def bind(value):
        if value not in recorded_refs:
            return value
        alias = recorded_refs[value]
        if alias not in current_values:
            raise ValueError("recorded context reference is absent in replay")
        return current_values[alias]

    return _walk(output, bind)
