"""从原文识别明确的充电关系；不接受选方案模型自报的部件名称作为证据。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

ENTITY_TEXT = (
    r"(?:charging\s+|storage\s+|travel\s+)?cases?"
    r"|(?:breast\s+)?pumps?(?:\s+(?:motors?|hubs?))?"
    r"|motors?|earbuds?|earphones?|headphones?|phones?"
    r"|(?:base\s+)?stations?|docks?|robots?|cameras?"
)
ENTITY = re.compile(rf"\b(?:{ENTITY_TEXT})\b", re.IGNORECASE)
CHARGING_FAILURE = re.compile(
    r"\b(?:not|never|cannot|can't|won't|doesn't|don't|isn't|aren't|unable to|fails? to|failed to)"
    r"\s+(?:re)?charg(?:e|es|ing)\b", re.IGNORECASE,
)
OBJECT = re.compile(rf"^\s+(?:(?:the|my|its|your|both)\s+)?({ENTITY_TEXT})\b", re.IGNORECASE)
LOCATION = re.compile(rf"^\s+(?:in|inside|on|from|with)\s+(?:(?:the|my|its|your)\s+)?({ENTITY_TEXT})\b", re.IGNORECASE)


@dataclass(frozen=True)
class ChargingRelation:
    recipient: str
    provider: str | None = None


def endpoint(text: str) -> str | None:
    parts = list(ENTITY.finditer(text))
    if not parts:
        return None
    part = parts[-1].group().lower()
    if "case" in part:
        return "charging case"
    if "pump" in part or "motor" in part:
        return "pump"
    if "station" in part or "dock" in part:
        return "base station"
    return part.rstrip("s")


def charging_relation(text: str) -> ChargingRelation | None:
    """受电失败和不能给另一设备供电不同；只读取第一个明确失败子句。"""
    text = text.replace("’", "'")
    match = CHARGING_FAILURE.search(text)
    if match is None:
        return None
    subject = endpoint(re.split(r"[.;!?\n]", text[:match.start()])[-1])
    tail = text[match.end():]
    if obj := OBJECT.match(tail):
        recipient = endpoint(obj.group(1))
        return ChargingRelation(recipient, subject) if recipient else None
    if subject is None:
        return None
    location = LOCATION.match(tail)
    return ChargingRelation(subject, endpoint(location.group(1)) if location else None)


def check_charging_recipient(title: str, covered_facts: list[dict], facts: list[dict]) -> tuple[Literal["unrelated", "matched", "mismatch", "unknown"], str | None]:
    """返回（关系核验结果，冲突时应围绕哪个对象澄清）。

    官方标题无明确关系时留给其他适用性规则。存在供电方故障时先处理它，不用下游症状绕开。
    """
    candidate = charging_relation(title)
    if candidate is None:
        return "unrelated", None

    def relation(fact):
        if fact.get("kind") != "symptom" or fact.get("status", "active") != "active" or fact.get("polarity", "affirmed") != "affirmed":
            return None
        return charging_relation(fact.get("quote") or "") or charging_relation(
            f"{fact.get('subject') or ''} {fact.get('value') or ''}"
        )

    for fact in facts:
        known = relation(fact)
        if known and candidate.provider == known.recipient and candidate.recipient != known.recipient:
            return "mismatch", known.recipient
    known_relations = [known for fact in covered_facts if (known := relation(fact))]
    for known in known_relations:
        if known.recipient != candidate.recipient:
            return "mismatch", known.recipient
    return ("matched" if known_relations else "unknown"), None


def charging_question(recipient: str | None) -> str:
    return (f"When the {recipient} itself is connected to power, what does its charging indicator show?"
            if recipient else "Which part is not charging, and what is it connected to?")
