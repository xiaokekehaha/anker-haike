from app.conversation.commands import resolve_command
from app.conversation.interpret import TurnInterpretation


def state(text):
    return {
        "entry": "message",
        "input_id": "i2",
        "base_version": 1,
        "active_issue_id": "issue",
        "text": text,
        "pending_card": {
            "kind": "step_feedback",
            "card_id": "c1",
            "input_token": "token",
            "payload": {},
        },
        "turn_decision": {"allowed_operations": True, "patches": []},
    }


def test_explicit_feedback_consumes_original_input_and_token():
    meaning = TurnInterpretation(
        primary_intent="step_feedback", feedback="not_solved", feedback_quote="仍然不转"
    )
    command, error = resolve_command(state("清理后仍然不转"), meaning)
    assert error is None
    assert command["action_id"] == "i2" and command["input_token"] == "token"
    assert command["payload"]["feedback"] == "not_solved"


def test_execution_without_result_cannot_be_inferred():
    command, error = resolve_command(
        state("做过了"), TurnInterpretation(primary_intent="step_feedback")
    )
    assert command is None and error


def test_feedback_without_actual_quote_or_after_correction_is_not_applied():
    meaning = TurnInterpretation(
        primary_intent="step_feedback", feedback="solved", feedback_quote="好了"
    )
    assert resolve_command(state("为什么"), meaning)[0] is None
    modified = state("好了")
    modified["turn_decision"]["patches"] = [{"op": "replace"}]
    assert resolve_command(modified, meaning)[0] is None
