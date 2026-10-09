"""Constrain request routing using the current quoted request, never symptoms alone."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

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
        meaning.primary_intent in {"warranty_query", "order_query", "complaint", "unknown"}
        and request and request in text and not DECLINES_DIAGNOSIS.search(normalized)
        and any(f.kind == "symptom" and f.quote and f.quote in request for f in meaning.facts)
        and "report_problem" not in meaning.secondary_intents
    ):
        meaning = meaning.model_copy(update={"secondary_intents": [*meaning.secondary_intents, "report_problem"]})
    return meaning
