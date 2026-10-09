"""Quote-to-source matching for every fact, request and command the interpreter proposes.

The model must cite the user's own words, but it normalizes what it copies: runs of
whitespace collapse to one space and curly apostrophes become straight ones. Official
tickets pasted from spreadsheets carry double spaces and ’ (T61: "omni c20  isn’t").
Exact substring matching therefore silently dropped whole facts; the handoff summary
then read "no symptom recorded". Match on the normalized form of both sides instead.
Nothing else is relaxed: the quote still has to be a verbatim span of this input.
"""

from __future__ import annotations

import re

_WS = re.compile(r"[\s　]+")


def normalize(text: str) -> str:
    return _WS.sub(" ", text.replace("’", "'").replace("ʼ", "'")).strip()


def quoted(quote: str | None, text: str | None) -> bool:
    """True when `quote` is a non-empty span of `text` up to whitespace / apostrophe form."""
    if not quote or not quote.strip() or not text:
        return False
    return normalize(quote) in normalize(text)
