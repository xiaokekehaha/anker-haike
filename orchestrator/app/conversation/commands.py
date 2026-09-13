"""Text answers use the same validated command schema as card actions."""

from haike_contracts.actions import parse_action
from pydantic import ValidationError


def resolve_command(state, meaning):
    if state.get("entry") == "action":
        return None, None
    candidate = meaning.pending_answer
    feedback = meaning.feedback
    if candidate is None and feedback is None:
        if meaning.primary_intent in {"step_feedback", "answer_pending"}:
            return None, "请确认具体选择，或说明操作后是已解决、仍有问题还是无法操作。"
        return None, None
    pending = state.get("pending_card")
    if not pending:
        return None, "当前没有可提交的待办，请说明这条反馈对应哪一步。"
    decision = state["turn_decision"]
    if not decision["allowed_operations"] and feedback is not None:
        return None, "当前步骤因安全风险暂停，先核实设备现象，再继续排障。"
    if decision.get("patches") and feedback is not None:
        return None, "已记录新的情况；这条反馈对应更正前的步骤吗？请确认后再继续。"
    kind = "step_feedback" if feedback else candidate.kind
    quote = meaning.feedback_quote if feedback else candidate.quote
    if not quote or quote not in state.get("text", ""):
        return None, "请明确选择或操作结果，我还不能代您提交。"
    if kind != pending["kind"] and not (
        kind == "skip_receipt" and pending["kind"] in {"upload_receipt", "confirm_receipt"}
    ):
        return None, "这条回答与当前待办不对应，请确认要处理的项目。"
    payload = {"feedback": feedback} if feedback else candidate.payload
    if kind == "select_product" and payload.get("sku") not in {
        c["sku"] for c in pending["payload"]["candidates"]
    }:
        return None, "这个型号不在当前候选中，请重新确认设备型号。"
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
        return None, "信息还不完整，请确认卡片要求的内容。"
    return action.model_dump(mode="json"), None
