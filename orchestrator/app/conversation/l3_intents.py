import yaml

from app.actions.params import changes_order, extract_params
from app.settings import CONFIG_DIR


def product_question_answer(state):
    """A bare category/model answers the last product question, not an order lookup."""
    import re

    from app.conversation.interpret import TurnInterpretation
    from app.sessions.cards import get_catalog

    clar = state.get("clarification") or {}
    if clar.get("reason") != "product" or not clar.get("question"):
        return None
    latest = next((e for e in reversed(state.get("history", []))
                   if e.get("role") == "assistant" and e.get("kind") == "message"), None)
    if latest and latest.get("text") != clar["question"]:
        return None  # A later business question owns its own answer.
    text = state.get("text", "").strip().strip("。！! ")
    category = next((key for key, spec in get_catalog().categories.items()
                     if text.casefold() in {w.casefold() for w in [spec.name, *spec.keywords]}), None)
    identifier = bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,63}", text) and re.search(r"[0-9]", text))
    confirmation = text in {"是", "是的", "对", "不是", "不是的", "不对"}
    if category or identifier or confirmation:
        return TurnInterpretation(primary_intent="supplement", device_relation="current",
                                  device_category=category, product_hints=[text] if identifier else [])


def symptom_question_answer(state):
    from app.conversation.interpret import TurnInterpretation

    text = state.get("text", "")
    question = (state.get("symptom_interview") or {}).get("question")
    if question:
        response = text.strip().strip("。！!，, ").lower()
        if question.get("kind") == "symptom_selection":
            options = question["options"]
            selected = []
            if len(options) == 2 and response in {"都有", "两种都有", "两个都有", "两者都有"}:
                selected = [o["value"] for o in options]
            else:
                # Only exact selections are deterministic. Free-form language
                # goes to the normal interpreter with the stored options.
                import re
                parts = re.split(r"[、,，和及\s]+", response)
                aliases = {str(i): o["value"] for i, o in enumerate(options, 1)}
                aliases.update({o["label"]: o["value"] for o in options})
                aliases.update({o["value"]: o["value"] for o in options})
                if parts and all(p in aliases for p in parts):
                    selected = list(dict.fromkeys(aliases[p] for p in parts))
            if selected:
                return TurnInterpretation(primary_intent="answer_pending", device_relation="current",
                    symptom_answer={"question_id": question["question_id"], "answer": "selection", "quote": text, "selected_families": selected})
            if response not in {"不知道", "不清楚", "没试过", "不确定"}:
                return None
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
    terms = yaml.safe_load((CONFIG_DIR / "rules/intent_terms.yaml").read_text())
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
