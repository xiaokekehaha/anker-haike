import json

import pytest

from app.conversation.interpret import TurnInterpretation
from app.evaluation.semantic import SemanticCase, judge, load_cases, scenario


@pytest.mark.parametrize("kind,minimum", [("intent", 40), ("emotion", 40), ("routing", 20)])
def test_independent_semantic_gold_has_required_coverage(kind, minimum):
    cases, fingerprint = load_cases(kind)
    assert len(cases) >= minimum and len(fingerprint) == 64
    if kind == "intent":
        assert len({c.family for c in cases}) == 8
    for case in cases:
        assert "expected" not in json.dumps(scenario(case))


def test_semantic_eval_cannot_pass_with_wrong_intent_or_rule_fallback():
    case = SemanticCase(id="i", family="intent", text="查物流", expected={"primary_intent": "logistics_query"})
    _, errors = judge(case, TurnInterpretation(primary_intent="history_query"), source="model")
    assert errors == ["primary_intent"]
    _, errors = judge(case, TurnInterpretation(primary_intent="logistics_query"), source="l3_rules")
    assert errors == ["model_unavailable"]
