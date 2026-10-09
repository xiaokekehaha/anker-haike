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


def fallback_interpretation(state):
    from app.actions.runtime import get_services
    from app.conversation.interpret import TurnInterpretation

    if get_services() is None:
        return None
    text = state.get("text", "")
    terms = yaml.safe_load((CONFIG_DIR / "rules/intent_terms.yaml").read_text())
    folded = text.casefold()
    intents = [intent for intent, words in terms.items() if any(word.casefold() in folded for word in words)]
    from app.conversation.reduce import device_message_spans, quote_source
    from app.emotion.policy import evaluate_emotion
    from app.rules import get_rules_service

    cp = get_rules_service().check_in(text=text, session_id=state.get("session_id"))
    spans = device_message_spans(text)
    # 命中词只出现在设备推送 / 问题描述字段里（T11 的「contact customer service」）时，是设备在说话。
    human_requested = any(
        hit.rule_id == "R3" and quote_source(hit.term, spans) == "user_statement" for hit in cp.hits
    )
    if human_requested:
        intents.insert(0, "request_human")
    emotion = evaluate_emotion("calm", text, [], state.get("input_id", "fallback"))["emotion"]["level"]
    if not intents and state.get("consult_intent") and extract_params(text):
        intents = [state["consult_intent"]]
    if not intents and "tracking_no" in extract_params(text):
        # 只给了运单号，没有别的诉求：就是在问物流。
        intents = ["logistics_query"]
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
    )
