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
    """True when `quote` is a non-empty span of `text` up to whitespace / apostrophe form.

    The model also silently fixes a typo at the edge of what it copies (T34: "siscovered i had lost the maps"
    came back as "discovered …"), and a whole symptom was lost for one letter. A quote of at least four words
    still counts when it is verbatim after dropping its first or last word; short quotes get no such slack.
    """
    if not quote or not quote.strip() or not text:
        return False
    norm_quote, norm_text = normalize(quote), normalize(text)
    if norm_quote in norm_text:
        return True
    words = norm_quote.split(" ")
    if len(words) < 4:
        return False
    return " ".join(words[1:]) in norm_text or " ".join(words[:-1]) in norm_text
