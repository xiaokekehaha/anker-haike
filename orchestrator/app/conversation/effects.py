"""Persist display effects with the node's business update before delivery.

Text/progress remains streamable. Cards and summaries must survive a process restart
without invoking a model or applying a fact/feedback a second time.
"""

from contextvars import ContextVar
from functools import wraps

from langgraph.config import get_stream_writer

from app.context.runtime import turn_context
from app.conversation.reduce import stable_id

_scope: ContextVar = ContextVar("conversation_effect_scope", default=None)
PERSISTED = {
    "context_card", "proposal_card", "execution_card", "retake_card", "rating_card", "case_changed",
    "product_card",
    "step_card",
    "observation_card",
    "receipt_card",
    "escalation_summary",
    "issue_changed",
    "pending_changed",
    "summary_updated",
    "evidence",
    "message_start",
    "message",
    "message_end",
}


def writer():
    scope = _scope.get()
    if scope is None:
        return get_stream_writer()
    state, node, captured, downstream, offset = scope

    def emit(payload):
        payload = dict(payload)
        if payload["type"] in {"product_card", "step_card", "observation_card", "receipt_card", "context_card", "proposal_card", "execution_card", "retake_card", "rating_card", "case_changed"}:
            payload["issue_id"] = state.get("active_issue_id")
        if payload["type"] == "message_start":
            payload.setdefault("reply_to_input_id", state.get("input_id"))
            payload.setdefault("issue_id", state.get("active_issue_id"))
        if "version" in payload:
            payload["version"] = state.get("base_version", 0) + 1
        if payload["type"] in PERSISTED:
            effect_id = stable_id(state["input_id"], node, offset + len(captured), payload["type"])
            captured.append(
                {"effect_id": effect_id, "input_id": state["input_id"], "node": node, "payload": payload}
            )
        else:
            if payload["type"] == "message_start":
                payload.setdefault("reply_to_input_id", state.get("input_id"))
                payload.setdefault("issue_id", state.get("active_issue_id"))
            downstream(payload)

    return emit


def durable_node(fn):
    @wraps(fn)
    async def run(state):
        captured = []
        # A node can run more than once in a run (consult → advance_tasks → consult →
        # advance_tasks). Number its effects after the ones it already produced in this
        # run, so a second visit is not mistaken for a replay; a replay after a crash
        # starts from a checkpoint without them and gets the same ids again.
        offset = sum(
            1 for e in state.get("pending_effects") or []
            if e.get("node") == fn.__name__ and e.get("input_id") == state.get("input_id")
        )
        context_token = turn_context.set(state)
        token = _scope.set((state, fn.__name__, captured, get_stream_writer(), offset))
        try:
            result = await fn(state)
            if captured:
                old = state.get("pending_effects") or []
                known = {effect["effect_id"] for effect in old}
                result = {
                    **result,
                    "pending_effects": [
                        *old,
                        *[e for e in captured if e["effect_id"] not in known],
                    ],
                }
            return result
        finally:
            _scope.reset(token)
            turn_context.reset(context_token)

    return run
