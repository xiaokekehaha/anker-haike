"""票 33：故障卡配置 / token 上限 / 命中；WeKnora 不可用仍进 guide；无计划 → R5；改写失败路径；命中故障卡不伪造改写。"""

from __future__ import annotations

import json

import pytest

from app.faultcards import (
    FaultCardLibrary,
    FaultCardsError,
    estimate_tokens,
    fit_prompt_budget,
    set_fault_card_library,
)
from app.faultcards.library import MAX_CARD_TOKENS, MAX_PROMPT_TOKENS
from app.plans import PlanLibrary
from app.plans.runtime import set_plan_library
from app.settings import REPO_ROOT
from tests.message_form import model_task_text
from tests.test_diagnose import (
    INTAKE_X9,
    NO_MATCH,
    UNAVAILABLE,
    ScriptedAdapter,
    _rcfg,
    make_router,
)
from tests.test_diagnose import run_text as _run_text

RULES = REPO_ROOT / "config" / "rules" / "safety_terms.yaml"
PLANS = PlanLibrary.from_yaml(REPO_ROOT / "config" / "plans.yaml")
CARDS = FaultCardLibrary.from_yaml(
    REPO_ROOT / "config" / "fault_cards.yaml", plan_ids=set(PLANS.plan_ids)
)


@pytest.fixture
def cards():
    set_fault_card_library(CARDS)
    yield CARDS
    set_fault_card_library(None)


# ---- 配置与预算 ----


def test_cards_within_800_tokens_and_plan_ids_valid(cards):
    assert len(cards.cards) >= 5
    for c in cards.cards:
        assert 0 < c.tokens() <= MAX_CARD_TOKENS
        assert all(f.plan_id in PLANS.plan_ids for f in c.faults)
    assert cards.for_scope(sku="EUFY-X9-PRO", category="robot_vacuum").key == "EUFY-X9-PRO"
    assert (
        cards.for_scope(sku="EUFY-25C", category="robot_vacuum").key == "category:robot_vacuum"
    )  # 无 SKU 卡退回品类卡
    # 深度品类有品类卡；目录级品类（如拓展坞）没有
    assert cards.for_scope(sku=None, category="breast_pump").key == "category:breast_pump"
    assert cards.for_scope(sku=None, category="hub") is None


def test_card_match_and_evidence_items(cards):
    card = cards.for_scope(sku="EUFY-X9-PRO", category="robot_vacuum")
    hits = card.match(["不吸了", "滚刷缠头发"])
    assert [h.plan_id for h in hits] == ["rv_suction_hair_wrap"]
    items = card.evidence_items(hits)
    assert (
        items[0]["source"] == "fault_card"
        and items[0]["evidence_id"] == "fc:EUFY-X9-PRO:2026-09-12.1:rv_suction_hair_wrap"
    )
    assert card.match(["找不到基站"]) == []


def test_config_rejects_oversized_or_unknown_plan(tmp_path):
    big = "很" * 900
    (tmp_path / "c.yaml").write_text(
        f"version: t\ncards:\n  - key: X\n    doc_version: '1'\n    title: t\n    faults:\n      - {{fault: f, plan_id: rv_suction_hair_wrap, keywords: [k], first_step: {big}}}\n",
        encoding="utf-8",
    )
    with pytest.raises(FaultCardsError, match="tokens > 800"):
        FaultCardLibrary.from_yaml(tmp_path / "c.yaml")
    (tmp_path / "d.yaml").write_text(
        "version: t\ncards:\n  - {key: X, doc_version: '1', title: t, faults: [{fault: f, plan_id: nope_plan, keywords: [k], first_step: s}]}\n",
        encoding="utf-8",
    )
    with pytest.raises(FaultCardsError, match="unknown plan_id"):
        FaultCardLibrary.from_yaml(tmp_path / "d.yaml", plan_ids={"rv_suction_hair_wrap"})


def test_token_estimate_and_prompt_budget():
    assert estimate_tokens("滚刷缠绕") == 4 and estimate_tokens("eufy X9 Pro") <= 4
    parts = ["中" * 3000, "文" * 3000, "字" * 3000]
    kept, truncated = fit_prompt_budget(parts, budget=MAX_PROMPT_TOKENS)
    assert len(kept) == 2 and truncated is True and MAX_PROMPT_TOKENS == 8000
    card_text = CARDS.for_scope(sku="EUFY-X9-PRO", category=None).render()
    assert estimate_tokens(card_text) + sum(estimate_tokens(p) for p in kept) <= 8000 + 800


# ---- 图内 ----


async def run(router, adapter, text, **kw):
    return await _run_text(router, adapter, text, **kw)


async def test_weknora_down_a1_still_reaches_guide_with_standard_flow_note(
    mem_runtime, tmp_path, cards
):
    router, fakes = make_router(
        tmp_path,
        fast=[INTAKE_X9],
        main=[
            json.dumps(
                {
                    "hypotheses": [
                        {
                            "plan_id": "rv_suction_hair_wrap",
                            "confidence": 0.8,
                            "evidence_ids": ["fc:EUFY-X9-PRO:2026-09-12.1:rv_suction_hair_wrap"],
                        }
                    ]
                }
            ),
        ],
    )
    adapter = ScriptedAdapter({"kb_manual": [UNAVAILABLE()], "kb_tickets": [UNAVAILABLE()]})
    events, values = await run(router, adapter, "eufy X9 Pro 扫地机不吸了，滚刷缠了很多头发")
    tools = [e for e in events if e["type"] == "tool_call"]
    assert (
        tools[-1]["status"] == "failed" and tools[-1]["summary"] == "知识库暂不可用，按标准排障流程"
    )
    stages = [e["stage"] for e in events if e["type"] == "progress"]
    assert stages[-1] == "guide" and values["stage"] == "guide"  # A1 仍进入 guide
    assert values["knowledge_status"] == "unavailable"
    assert values["fault_card"]["key"] == "EUFY-X9-PRO" and values["fault_card_hits"] == [
        "rv_suction_hair_wrap"
    ]
    assert values["plan_cursor"] == {
        "plan_id": "rv_suction_hair_wrap",
        "version": 1,
        "step_id": "s1",
        "source": "synthesize",
    }
    assert values["diagnose_outcome"]["mode"] == "fault_card"
    # 故障卡驱动假设，其证据进 synthesize 上下文；票 19 起本轮不再有自由回复
    synth_call = next(c for c in fakes["main"].calls if c["metadata"]["task"] == "diagnose.synthesize")
    assert "fc:EUFY-X9-PRO" in model_task_text(synth_call)
    assert [c["metadata"]["task"] for c in fakes["main"].calls] == ["diagnose.synthesize"]
    assert events[-1]["reason"] == "awaiting_input"  # 票 34：guide 发出首张步骤卡


async def test_no_match_and_no_applicable_plan_hands_off_instead_of_unrelated_steps(
    mem_runtime, tmp_path, cards
):
    """票 19：降级计划按症状过滤。找不到基站属 navigation_failure，无预写计划 → R5 人工交接，
    不再拿吸力计划顶替。"""
    intake = json.dumps(
        {
            "emotion_level": "calm",
            "product_hints": ["X9 Pro"],
            "symptoms": ["找不到基站"],
            "wants_human": False,
        },
        ensure_ascii=False,
    )
    router, fakes = make_router(tmp_path, fast=[intake], main=[["先检查基站位置。"]])
    adapter = ScriptedAdapter({"kb_manual": [NO_MATCH()], "kb_tickets": [NO_MATCH()]})
    events, values = await run(router, adapter, "eufy X9 Pro 找不到基站")
    assert values["fault_card_hits"] == [] and values["knowledge_status"] == "no_match"
    assert values["symptom_codes"] == ["navigation_failure"]
    assert values["diagnose_outcome"] == {
        "mode": "escalate",
        "reason": "R5",
        "knowledge_status": "no_match",
    }
    assert values["plans_ranked"] == [] and values["stage"] == "escalate"
    # 无证据不调 synthesize，也不出步骤卡：模型不得凭常识给假设
    assert [c["metadata"]["task"] for c in fakes["main"].calls] == []
    assert "step_card" not in [e["type"] for e in events]
    assert [e for e in events if e["type"] == "tool_call"][-1][
        "summary"
    ] == "未找到匹配知识，按标准排障流程"


async def test_category_only_without_plans_escalates_r5(mem_runtime, tmp_path, cards):
    """把计划库替换成只有 sku 专属计划：category_only 无适用计划 → R5。"""
    sku_only = PLANS.__class__.__new__(PLANS.__class__)
    sku_only.__dict__.update(PLANS.__dict__)
    from app.plans.models import AppliesTo

    sku_only._plans = {
        pid: p.model_copy(
            update={
                "applies_to": AppliesTo(
                    scope="sku", category="robot_vacuum", sku_list=["EUFY-X10-PRO-OMNI"]
                )
            }
        )
        for pid, p in PLANS._plans.items()
    }
    set_plan_library(sku_only)
    intake = json.dumps(
        {
            "emotion_level": "calm",
            "product_hints": ["扫地机"],
            "symptoms": ["不吸了"],
            "wants_human": False,
        },
        ensure_ascii=False,
    )
    router, _ = make_router(tmp_path, fast=[intake], main=[["x"]])
    adapter = ScriptedAdapter({"kb_manual": [NO_MATCH()], "kb_tickets": [NO_MATCH()]})
    try:
        events, values = await run(router, adapter, "扫地机不吸了")
    finally:
        set_plan_library(None)
    if values.get("product_state") != "category_only":
        pytest.skip("票 24 的消歧未把「扫地机」判为 category_only")
    assert values["escalate_reason"] == "R5" and values["stage"] == "escalate"
    summ = next(e for e in events if e["type"] == "escalation_summary")["summary"]
    assert summ["reason"]["rule_id"] == "R5"


async def test_rewrite_failure_paths_with_and_without_plans(mem_runtime, tmp_path, cards, monkeypatch):
    # The coded symptom also matches the local fault card. Isolate external
    # retrieval failure by making this scenario's local card unavailable.
    monkeypatch.setattr(cards, "for_scope", lambda **kwargs: None)
    intake = json.dumps(
        {
            "emotion_level": "calm",
            "product_hints": ["X9 Pro"],
            "primary_intent": "report_problem",
            "device_relation": "current",
            "facts": [{"value": "跑完了地上还是一堆渣", "quote": "地上还是一堆渣", "symptom_code": "suction_low"}],
        },
        ensure_ascii=False,
    )
    # 1) 改写模型不可用（脚本抛错）→ 有计划：standard_flow，plans_ranked 不含改写文本
    router, _fakes = make_router(
        tmp_path, fast=[intake, RuntimeError("boom"), RuntimeError("boom")], main=[["x"]]
    )
    adapter = ScriptedAdapter({"kb_manual": [NO_MATCH()], "kb_tickets": [NO_MATCH()]})
    _events, values = await run(
        router, adapter, "eufy X9 Pro 它跑完了，地上还是一堆渣", rcfg=_rcfg()
    )
    rw = next(t for t in values["retrieval_trace"] if t.get("event") == "rewrite_result")
    assert rw["accepted"] is False and rw["rejected_reason"].startswith("model:")
    assert values["diagnose_outcome"]["mode"] == "standard_flow" and values["stage"] == "guide"
    assert all(p["evidence_ids"] == [] for p in values["plans_ranked"])
    # 2) 二次 no_match → 同样 standard_flow；两轮 trace 都在
    router2, _ = make_router(
        tmp_path,
        fast=[intake, json.dumps({"query": "扫地机器人 清扫后残留碎屑"}, ensure_ascii=False)],
        main=[["x"]],
    )
    adapter2 = ScriptedAdapter(
        {"kb_manual": [NO_MATCH(), NO_MATCH()], "kb_tickets": [NO_MATCH(), NO_MATCH()]}
    )
    _, values2 = await run(router2, adapter2, "eufy X9 Pro 它跑完了，地上还是一堆渣", rcfg=_rcfg())
    assert (
        values2["retrieval_rounds"] == 2 and values2["diagnose_outcome"]["mode"] == "standard_flow"
    )
    assert "清扫后残留碎屑" not in json.dumps(
        values2["plans_ranked"], ensure_ascii=False
    )  # 改写文本不是证据
    # 3) 二次 unavailable → 知识状态反映实际，仍 standard_flow
    router3, _ = make_router(
        tmp_path,
        fast=[intake, json.dumps({"query": "扫地机器人 清扫后残留碎屑"}, ensure_ascii=False)],
        main=[["x"]],
    )
    adapter3 = ScriptedAdapter(
        {"kb_manual": [NO_MATCH(), UNAVAILABLE()], "kb_tickets": [NO_MATCH(), UNAVAILABLE()]}
    )
    _, values3 = await run(router3, adapter3, "eufy X9 Pro 它跑完了，地上还是一堆渣", rcfg=_rcfg())
    assert (
        values3["retrieval_rounds"] == 2 and values3["knowledge_status"] == "no_match"
    )  # 第二轮失败保留首轮真实结果
    assert values3["diagnose_outcome"]["mode"] == "standard_flow"


async def test_sufficient_fault_card_without_kb_hits_does_not_trigger_rewrite(
    mem_runtime, tmp_path, cards
):
    router, fakes = make_router(
        tmp_path,
        fast=[INTAKE_X9, json.dumps({
            "coverage": "sufficient", "items": [{
                "evidence_id": "fc:EUFY-X9-PRO:2026-09-12.1:rv_suction_hair_wrap", "verdict": "relevant",
            }],
        })],
        main=[
            json.dumps(
                {
                    "hypotheses": [
                        {
                            "plan_id": "rv_suction_hair_wrap",
                            "confidence": 0.7,
                            "evidence_ids": ["fc:EUFY-X9-PRO:2026-09-12.1:rv_suction_hair_wrap"],
                        }
                    ]
                }
            ),
            ["x"],
        ],
    )
    adapter = ScriptedAdapter({"kb_manual": [NO_MATCH()], "kb_tickets": [NO_MATCH()]})
    _, values = await run(router, adapter, "eufy X9 Pro 不吸了 滚刷缠头发", rcfg=_rcfg())
    dec = next(t for t in values["retrieval_trace"] if t.get("event") == "rewrite_decision")
    assert dec["triggered"] is False and dec["reason"] == "sufficient"
    assert [c["metadata"]["task"] for c in fakes["fast"].calls] == ["intake", "retrieve.grade"]
    assert values["retrieval_rounds"] == 1
    assert values["plans_ranked"][0]["evidence_ids"] == [
        "fc:EUFY-X9-PRO:2026-09-12.1:rv_suction_hair_wrap"
    ]


def test_no_common_sense_hypothesis_path():
    """代码审查项：synthesize 无证据 / 无路由时不调模型，直接 standard_flow。"""
    import importlib
    import inspect

    mod = importlib.import_module("app.diagnose.synthesize")
    src = inspect.getsource(mod.synthesize)
    assert "if not evidence or router is None" in src and "default_plans_ranked(allowed" in src
