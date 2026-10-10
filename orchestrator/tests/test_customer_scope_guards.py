"""官方 63 单 2026-10-10 复测的三处 P0：不替客户加诉求、不替客户选故障对象、排障卡不做售后承诺。

模型与知识库均为假；检查的是服务端对模型输出与官方原文的确定性约束。
"""

import pytest

from app.conversation.interpret import (
    FactCandidate,
    TurnInterpretation,
    logistics_correction,
    normal_operation_is_uncertain,
)
from app.diagnose.synthesize import filter_hypotheses
from app.official.qa_index import get_qa_index
from app.plans.qa import SERVICE_PROMISE, customer_text, plans_config, qa_plan_library

LIB = qa_plan_library()

T53 = (
    "Dear sale-team.Hello!\nOrder No: Anker015\nProduct Name: eufy Wearable Breast Pump S1 Pro\n"
    "Problem Description: One side of the pump stoped working. I tried to charge it over and over again but it stoped "
    "turning on. It’s been 24 months but this happed within 12 months but I had not known I can put in a claim. "
    "I hope I can get a replacement or you can fix it. Thank you\n\nProdcut SN: T8D04121\n"
)


def test_t53_replacement_or_fix_does_not_add_a_refund_task():
    """T53 / B15：「replacement or fix it」被加成 换货 → 退款 → 排障；同一原文的 R05 没有退款。"""
    quote = "I hope I can get a replacement or you can fix it."
    meaning = logistics_correction(TurnInterpretation(
        primary_intent="replacement_request", secondary_intents=["refund_request", "report_problem"],
        request_quotes={"replacement_request": quote, "refund_request": quote},
    ), T53)
    assert [meaning.primary_intent, *meaning.secondary_intents] == ["replacement_request", "report_problem"]
    assert "refund_request" not in meaning.request_quotes


def test_refund_first_without_refund_words_falls_back_to_the_next_request():
    meaning = logistics_correction(TurnInterpretation(
        primary_intent="refund_request", secondary_intents=["replacement_request"],
    ), "The pump stopped working. Please send me a replacement.")
    assert (meaning.primary_intent, meaning.secondary_intents) == ("replacement_request", [])


@pytest.mark.parametrize("text", [
    "The pump stopped working. Replace it or give me a refund.",
    "The pump stopped working. I want my money back or a new one.",
    "De pomp werkt niet meer. Vervanging of terugbetaling graag.",
])
def test_an_explicit_refund_request_is_kept(text):
    meaning = logistics_correction(TurnInterpretation(
        primary_intent="replacement_request", secondary_intents=["refund_request"],
    ), text)
    assert "refund_request" in meaning.secondary_intents


def _fact(quote, polarity="affirmed", kind="symptom"):
    return FactCandidate(kind=kind, value=quote, quote=quote, polarity=polarity)


@pytest.mark.parametrize("quote,expected", [
    ("the left one does work", "uncertain"),      # T50 原文
    ("the left side works fine", "uncertain"),
    ("the left one does not work", "affirmed"),
    ("One side of the pump stoped working", "affirmed"),
    ("it stoped turning on", "affirmed"),
])
def test_a_statement_that_a_part_works_is_not_a_fault(quote, expected):
    assert normal_operation_is_uncertain([_fact(quote)])[0].polarity == expected


def test_t50_model_question_cannot_assume_the_other_side_failed():
    """T50：唯一「现象」是左侧正常。模型不列 supported_symptoms、改用 needs_confirmation 自拟「右侧有没有吸力」，
    B10 甚至问成「右侧有吸力而左侧没有？」。只剩开放问题：哪一侧、什么现象。"""
    facts = [{"kind": "symptom", "value": "left one does work", "quote": "the left one does work",
              "subject": "left one", "polarity": "uncertain", "status": "active"}]
    hyp = {"plan_id": "qa_bp_0020", "confidence": 0.55, "evidence_ids": ["e1"], "applicability": "needs_confirmation",
           "supported_symptoms": [], "missing_fact": "pump hub suction",
           "clarification_question": "Does the right pump hub produce any suction or motor movement at all?"}
    kept, dropped, clar = filter_hypotheses(
        [hyp], allowed={"qa_bp_0020": LIB.get("qa_bp_0020")}, evidence_ids={"e1"},
        symptoms={"left one does work"}, facts=facts, error_codes=[], max_n=3,
    )
    assert kept == [] and "polarity_uncertain:qa_bp_0020" in dropped
    assert "right" not in clar[0]["question"] and "Which side or part" in clar[0]["question"]


def test_a_concrete_fault_beside_a_working_part_still_uses_the_model_question():
    facts = [{"kind": "symptom", "value": "left one does work", "quote": "x", "polarity": "uncertain", "status": "active"},
             {"kind": "symptom", "value": "right pump will not turn on", "quote": "y", "polarity": "affirmed", "status": "active"}]
    hyp = {"plan_id": "qa_bp_0025", "confidence": 0.8, "evidence_ids": ["e1"], "applicability": "needs_confirmation",
           "supported_symptoms": ["right pump will not turn on"], "missing_fact": "charging light",
           "clarification_question": "Is the light inside the charging case on?"}
    _, _, clar = filter_hypotheses(
        [hyp], allowed={"qa_bp_0025": LIB.get("qa_bp_0025")}, evidence_ids={"e1"},
        symptoms={"left one does work", "right pump will not turn on"}, facts=facts, error_codes=[], max_n=3,
    )
    assert clar[0]["question"] == "Is the light inside the charging case on?"


def test_t36_noise_card_keeps_the_checks_but_not_the_replacement_promise():
    """T36：噪声卡在核保之前写「we will send you a suitable replacement unit」。
    rv-0341 已由 qa_overrides.yaml 拆成诊断问句 + 各分支步骤，检查合在一起看。"""
    texts = [customer_text(LIB.evidence_snippet(s.instruction_src)) for s in LIB.get("qa_rv_0341").steps]
    joined = "\n".join(texts)
    assert "removing the roller brush and cover" in joined and "mopping mode" in joined
    assert "replacement unit" not in joined and "by sending you" not in joined
    handoffs = [t for s, t in zip(LIB.get("qa_rv_0341").steps, texts, strict=True) if s.kind == "handoff"]
    assert handoffs and all(t.strip() == "Whether a replacement or part can be sent depends on a warranty check." for t in handoffs)


def test_t53_out_of_warranty_card_does_not_ask_for_a_shipping_address():
    """T53：已按过保拒绝，第五卡仍写「Please provide your shipping address so that we can replace the device」。"""
    plan = LIB.get("qa_bp_0114")
    texts = [customer_text(LIB.evidence_snippet(s.instruction_src)) for s in plan.steps]
    joined = "\n".join(texts)
    assert "shipping address" not in joined and "replace the device" not in joined
    assert "Damaged button" in joined and "magnetic charging cable" in joined


def test_no_official_step_renders_a_service_promise():
    offenders = [key for key, ev in plans_config(get_qa_index()).evidence.items()
                 if SERVICE_PROMISE.search(customer_text(ev.snippet))]
    assert not offenders, offenders
