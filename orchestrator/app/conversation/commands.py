"""Text answers use the same validated command schema as card actions."""

from haike_contracts.actions import parse_action
from pydantic import ValidationError

from app.conversation.quotes import quoted


def resolve_command(state, meaning):
    if state.get("entry") == "action":
        return None, None
    candidate = meaning.pending_answer
    feedback = meaning.feedback
    if candidate is None and feedback is None:
        # 没有待办卡时这句话无从谈起：既没有「选择」也没有可反馈的步骤。此时多半是模型把
        # 判别问题的回答标成了 answer_pending 却没解析出结构化答案，交回排障路径重问那个问题，
        # 比让用户在这里「确认具体选择」有用（2026-09-16 实测复现）。
        if meaning.primary_intent in {"step_feedback", "answer_pending"} and state.get("pending_card"):
            return None, "Please pick an option, or tell me whether the step solved it, didn't help, or couldn't be done."
        return None, None
    pending = state.get("pending_card")
    if not pending:
        return None, "There's nothing waiting for an answer right now. Which step is this about?"
    decision = state["turn_decision"]
    if not decision["allowed_operations"] and feedback is not None:
        return None, "This step is paused because of a safety concern. Let's confirm what the device is doing first."
    if decision.get("patches") and feedback is not None:
        return None, "I've noted the new details. Does this feedback refer to the step from before the correction? Please confirm."
    kind = "step_feedback" if feedback else candidate.kind
    quote = meaning.feedback_quote if feedback else candidate.quote
    if not quoted(quote, state.get("text", "")):
        return None, "Please choose an option or tell me the result; I can't submit it for you yet."
    if kind != pending["kind"] and not (
        kind == "skip_receipt" and pending["kind"] in {"upload_receipt", "confirm_receipt"}
    ):
        return None, "That answer doesn't match what I asked. Which item would you like to handle?"
    payload = {"feedback": feedback} if feedback else candidate.payload
    if kind == "select_product" and payload.get("sku") not in {
        c["sku"] for c in pending["payload"]["candidates"]
    }:
        return None, "That model isn't one of the options. Could you confirm the model again?"
    try:
        action = parse_action(
            {
                "kind": kind,
                "payload": payload,
                "action_id": state["input_id"],
                "expected_version": state["base_version"],
                "target_issue_id": state["active_issue_id"],
                "card_id": pending["card_id"],
                "input_token": pending.get("input_token") or pending["card_id"],
            }
        )
    except ValidationError:
        return None, "Some information is still missing. Please check what the card asks for."
    return action.model_dump(mode="json"), None
