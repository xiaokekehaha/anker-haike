"""Text answers use the same validated command schema as card actions."""

from haike_contracts.actions import parse_action
from pydantic import ValidationError

from app.conversation.quotes import quoted
from app.guide.verify import step_payload_error

ANSWERED_STEP_KINDS = {"question", "material_request"}


def _step_answer(pending, candidate, meaning):
    """问句 / 材料卡的文字回答 → step_feedback 命令载荷。问句没有「解决 / 没解决」语义：
    模型对这类卡给了 feedback 时，用它引用的原话作文字回答（T46 文字补测）。"""
    step = (pending.get("payload") or {}).get("step") or {}
    if pending.get("kind") != "step_feedback" or step.get("kind") not in ANSWERED_STEP_KINDS:
        return None
    if candidate is not None and candidate.kind == "step_answer":
        raw = candidate.payload
        answer = {"option": raw.get("option"), "text": raw.get("text"), "unavailable": bool(raw.get("unavailable"))}
        return answer, candidate.quote
    if candidate is None and meaning.feedback is not None:
        return {"option": None, "text": meaning.feedback_quote, "unavailable": False}, meaning.feedback_quote
    return None


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
    step_answer = _step_answer(pending, candidate, meaning)
    answers_step = feedback is not None or step_answer is not None
    if not decision["allowed_operations"] and answers_step:
        return None, "This step is paused because of a safety concern. Let's confirm what the device is doing first."
    # 新增现象（add）与回答同句很常见（T22「平地持续报错」），不影响回答指向哪张卡；纠正旧记录才要确认。
    if answers_step and any(p.get("op") in {"replace", "retract"} for p in decision.get("patches") or []):
        return None, "I've noted the new details. Does this feedback refer to the step from before the correction? Please confirm."
    if step_answer is not None:
        kind, (answer, quote) = "step_feedback", step_answer
        payload = {"answer": answer}
    elif candidate is not None and candidate.kind == "step_answer":
        return None, "That answer doesn't match what I asked. Which item would you like to handle?"
    else:
        kind = "step_feedback" if feedback else candidate.kind
        quote = meaning.feedback_quote if feedback else candidate.quote
        payload = {"feedback": feedback} if feedback else candidate.payload
    if not quoted(quote, state.get("text", "")):
        return None, "Please choose an option or tell me the result; I can't submit it for you yet."
    if kind != pending["kind"] and not (
        kind == "skip_receipt" and pending["kind"] in {"upload_receipt", "confirm_receipt"}
    ):
        return None, "That answer doesn't match what I asked. Which item would you like to handle?"
    if kind == "select_product" and payload.get("sku") not in {
        c["sku"] for c in pending["payload"]["candidates"]
    }:
        return None, "That model isn't one of the options. Could you confirm the model again?"
    if kind == "step_feedback" and step_payload_error((pending.get("payload") or {}).get("step") or {}, payload):
        return None, "Please pick one of the options on the card, or describe it in a few words."
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
