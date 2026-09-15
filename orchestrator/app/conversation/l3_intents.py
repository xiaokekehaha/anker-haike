import yaml

from app.actions.params import changes_order, extract_params
from app.settings import REPO_ROOT


def symptom_question_answer(state):
    from app.conversation.interpret import TurnInterpretation

    text = state.get("text", "")
    question = (state.get("symptom_interview") or {}).get("question")
    if question:
        response = text.strip().strip("。！!，, ").lower()
        choices = {"yes": {"是", "是的", "对", "能", "可以", "有", "有的", "yes"}, "no": {"不", "不是", "不能", "不可以", "没有", "没", "否", "no"}, "unknown": {"不知道", "不清楚", "没试过", "不确定"}}
        answer = next((key for key, words in choices.items() if response in words), None)
        if answer:
            return TurnInterpretation(primary_intent="answer_pending", device_relation="current", symptom_answer={"question_id": question["question_id"], "answer": answer, "quote": text})


def fallback_interpretation(state):
    from app.actions.runtime import get_services
    from app.conversation.interpret import TurnInterpretation

    if get_services() is None:
        return None
    answer = symptom_question_answer(state)
    if answer:
        return answer
    text = state.get("text", "")
    terms = yaml.safe_load((REPO_ROOT / "config/rules/intent_terms.yaml").read_text())
    intents = [intent for intent, words in terms.items() if any(word in text for word in words)]
    from app.emotion.policy import evaluate_emotion
    from app.rules import get_rules_service

    cp = get_rules_service().check_in(text=text, session_id=state.get("session_id"))
    human_requested = any(hit.rule_id == "R3" for hit in cp.hits)
    if human_requested:
        intents.insert(0, "request_human")
    emotion = evaluate_emotion("calm", text, [], state.get("input_id", "fallback"))["emotion"]["level"]
    from app.conversation.tasks import ordered_intents
    from app.conversation.taxonomy import normalize

    symptoms = normalize(text)
    if symptoms:
        intents = ordered_intents("report_problem", intents)
    if not intents and state.get("consult_intent") and extract_params(text):
        intents = [state["consult_intent"]]
    if not intents and emotion != "calm":
        intents = ["complaint"]
    if not intents:
        return None
    return TurnInterpretation(
        primary_intent=intents[0],
        human_request_quote=text if human_requested else None,
        emotion_level=emotion,
        business_reference={"relation": "other", "quote": text} if changes_order(text) else None,
        secondary_intents=intents[1:],
        device_relation="current",
        facts=[
            {
                "kind": "symptom",
                "value": s["quote"],
                "quote": s["quote"],
                "symptom_code": s["symptom_code"],
            }
            for s in symptoms
        ],
    )
