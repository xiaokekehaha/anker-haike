"""情绪规则词的多语言命中（主办方 63 单工单原文，2026-10-08）。"""

import pytest

from app.emotion.policy import evaluate_emotion, term_hit
from app.official.models import OfficialData

TICKETS = {t.id: t.body for t in OfficialData().tickets}


@pytest.mark.parametrize(
    ("ticket", "level"),
    [("T58", "angry"), ("T60", "angry"), ("T56", "angry"), ("T57", "dissatisfied"), ("T59", "dissatisfied"), ("T1", "calm")],
)
def test_ticket_emotion_from_rules(ticket, level):
    assert evaluate_emotion("calm", TICKETS[ticket], [], "x")["emotion"]["level"] == level


def test_latin_terms_are_whole_word_case_insensitive_and_respect_negation():
    assert term_hit("suck", "You SUCK")
    assert not term_hit("scam", "I ordered scampi")
    assert not term_hit("disappointed", "I am not disappointed at all")
    assert not term_hit("不满", "我没有不满")
    assert term_hit("不满", "我很不满")
