"""Constrain request routing using the current quoted request, never symptoms alone."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.conversation.quotes import normalize
from app.official.message import LABELS

if TYPE_CHECKING:
    from app.conversation.interpret import TurnInterpretation


TRACKING_FAILURE = re.compile(
    r"(?:(?:my|the|this) )?tracking (?:number|link|page) (?:is not working|isn't working|does not work|doesn't work|is invalid|is not found)"
    r"|I (?:cannot|can't) track (?:my|the) (?:order|package)"
    r"|I(?:'ve| have)? tried to (?:put|enter|use) (?:my|the) tracking number "
    r"(?:in to look for my order|to (?:find|track) my (?:order|package)) and it (?:is not working|doesn't work)",
    re.IGNORECASE,
)
DELIVERY_QUESTION = re.compile(
    r"(?:Do you know )?when (?:will I (?:get|receive)|I will be getting) (?:my|the) (?:order|package)"
    r"|Where is (?:my|the) (?:order|package)",
    re.IGNORECASE,
)
DECLINES_DIAGNOSIS = re.compile(
    r"\b(?:don't|do not|stop|no) (?:start )?troubleshoot(?:ing)?\b"
    r"|\bonly (?:check|tell me about) (?:my |the )?warranty\b"
    r"|(?:不要|先别|不想)排(?:查|障)|只(?:查|问)(?:一下)?保修",
    re.IGNORECASE,
)
ONLY_WARRANTY = re.compile(
    r"\bonly (?:check|tell me about) (?:my |the )?warranty\b|只(?:查|问)(?:一下)?保修",
    re.IGNORECASE,
)
QUERY_INTENTS = frozenset({"order_query", "warranty_query", "logistics_query"})
QUERY_FIELDS = {
    "order_query": frozenset({"order_no", "sku", "purchase_date", "amount", "address", "serial_number", "seller", "country"}),
    "warranty_query": frozenset({"warranty_end"}),
    "logistics_query": frozenset({"tracking_no", "service_order_no", "logistics_status", "carrier", "updated_at"}),
}
METADATA_LABELS = [label for key, labels in LABELS.items() if key not in {"description", "push"} for label in labels]
METADATA_LINE = re.compile(
    r"^\s*(?:" + "|".join([*METADATA_LABELS, "Problem Type", "Probleemtype", "Problemtyp", "Submit Date", "Purchase proof"])
    + r")\s*[:：].*$", re.IGNORECASE | re.MULTILINE,
)


def ground_additional_queries(meaning: TurnInterpretation, text: str) -> tuple[TurnInterpretation, list[dict[str, str]]]:
    """业务排序之后校验并列查询：内部取数或元数据不等于另一个用户请求。"""
    source = normalize(text)
    metadata = [normalize(match.group()) for match in METADATA_LINE.finditer(text)]
    primary_quote = normalize(meaning.request_quotes.get(meaning.primary_intent, ""))
    kept, rejected = [], []
    for intent in meaning.secondary_intents:
        if intent not in QUERY_INTENTS:
            kept.append(intent)
            continue
        quote = normalize(meaning.request_quotes.get(intent, ""))
        reason = (
            "request_quote_missing" if not quote else "request_quote_ungrounded" if quote not in source
            else "metadata_is_not_request" if any(quote in span for span in metadata)
            else "duplicate_request_quote" if quote == primary_quote else None
        )
        if reason is None and intent in {"order_query", "warranty_query"}:
            answer = meaning.answer_request
            answer_quote = normalize(answer.quote) if answer else ""
            if not answer or not QUERY_FIELDS[intent].intersection(answer.fields):
                reason = "query_result_missing"
            elif not answer_quote or answer_quote not in source or not (quote in answer_quote or answer_quote in quote):
                reason = "query_result_ungrounded"
        if reason:
            rejected.append({"intent": intent, "reason": reason})
        else:
            kept.append(intent)
    return meaning.model_copy(update={"secondary_intents": kept}), rejected


def constrain_requests(meaning: TurnInterpretation, text: str) -> TurnInterpretation:
    normalized = text.replace("’", "'").replace("ʼ", "'")
    clauses = [part.strip() for part in re.split(r"[.!?;\n]+", normalized) if part.strip()]
    tracking = [part for part in clauses if TRACKING_FAILURE.fullmatch(part)]
    # Require positive coverage of the entire input. An unrecognized clause may
    # contain another device/request; absence of a device keyword proves nothing.
    if tracking and all(TRACKING_FAILURE.fullmatch(part) or DELIVERY_QUESTION.fullmatch(part) for part in clauses):
        misplaced = [f for f in meaning.facts if f.kind == "symptom" and f.quote and any(
            f.quote.replace("’", "'").replace("ʼ", "'") in part for part in tracking
        )]
        if all(f in misplaced for f in meaning.facts if f.kind == "symptom"):
            primary = "logistics_query" if meaning.primary_intent == "report_problem" else meaning.primary_intent
            meaning = meaning.model_copy(update={
                "primary_intent": primary,
                "secondary_intents": list(dict.fromkeys(
                    i for i in meaning.secondary_intents if i not in {"report_problem", primary}
                )),
                "facts": [f for f in meaning.facts if f not in misplaced],
                "diagnostic_request_quote": None,
            })
    request = meaning.diagnostic_request_quote
    intents = [meaning.primary_intent, *meaning.secondary_intents]
    if (
        ONLY_WARRANTY.search(normalized)
        and "warranty_query" in intents
        and set(intents) <= {"report_problem", "warranty_query", "complaint"}
    ):
        # Explicitly deferred diagnosis is not a pending task. Keep the device
        # facts as warranty context, but never let queue priority override the request.
        return meaning.model_copy(update={
            "primary_intent": "warranty_query",
            "secondary_intents": [i for i in meaning.secondary_intents if i == "complaint"],
            "diagnostic_request_quote": None,
        })
    # A fact may be refund background or a past event. Only a grounded, current
    # request for diagnostic help can repair a missing troubleshooting task.
    if (
        meaning.primary_intent in {"warranty_query", "order_query", "complaint", "unknown", "replacement_request", "refund_request"}
        and request and request in text and not DECLINES_DIAGNOSIS.search(normalized)
        and any(f.kind == "symptom" and f.quote and f.quote in text for f in meaning.facts)
        and "report_problem" not in meaning.secondary_intents
    ):
        meaning = meaning.model_copy(update={"secondary_intents": [*meaning.secondary_intents, "report_problem"]})
    return meaning
