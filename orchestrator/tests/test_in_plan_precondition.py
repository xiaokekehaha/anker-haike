"""计划内检查不是入口前提（T29，2026-10-12 复测）。

rv-0254 第 1 步就是「检查污水箱门扣是否扣紧」，模型把它填成 needs_confirmation 的 missing_fact，
先发一句「门扣扣紧了吗」，客户答 yes 后才出卡并跳过第 1 步；3 次复测 2 次走问句、1 次直接出卡。
服务端核对：missing_fact 被计划内某个「检查 / 核实」步骤的首句覆盖 → 按 supported 继续，由步骤卡按官方顺序查。
场景前提（In multi-floor tasks …）仍先问。
"""

from __future__ import annotations

import pytest

from app.diagnose.synthesize import filter_hypotheses, in_plan_check
from app.knowledge.runtime import set_knowledge_adapter
from app.plans.runtime import get_plan_library
from tests.conversation_runtime import conversation as base_conversation_fixture
from tests.fake_qa import QAHitAdapter
from tests.test_conversation_l3 import l3_runtime as l3_runtime_fixture

base_conversation = base_conversation_fixture
l3_runtime = l3_runtime_fixture

LATCH = "Check whether the door latch of the dirty water tank is fastened"
QUESTION = "Is the door latch of the dirty water tank fastened securely?"
SYMPTOM = "Water tray will not empty"


@pytest.fixture
async def conversation(l3_runtime, base_conversation):
    yield base_conversation


def _hyp(pid="qa_rv_0254", **extra):
    return {"plan_id": pid, "confidence": 0.62, "evidence_ids": ["e1"], "applicability": "needs_confirmation",
            "supported_symptoms": [SYMPTOM], "clarification_question": QUESTION, "missing_fact": LATCH, **extra}


def _run(hyps, facts=(), symptoms=(SYMPTOM,)):
    lib = get_plan_library()
    allowed = {pid: lib.get(pid) for pid in ("qa_rv_0254", "qa_rv_0050")}
    return filter_hypotheses(hyps, allowed=allowed, evidence_ids={"e1"}, symptoms=set(symptoms), facts=list(facts), max_n=3)


@pytest.mark.parametrize("plan_id, missing, expected", [
    ("qa_rv_0254", LATCH, "s1"),
    ("qa_rv_0254", "the door latch of the dirty water tank is fastened", "s1"),
    ("qa_rv_0254", "the cleaning tray grille is blocked", "s2"),
    # 场景说明不是检查步骤：多楼层任务与否仍要先问
    ("qa_rv_0050", "In multi-floor tasks, the mop cannot be used without cleaning the mop", None),
    # 只覆盖一部分内容词不算同一件事
    ("qa_rv_0254", "the door latch of the clean water tank is broken", None),
    ("qa_rv_0254", None, None),
])
def test_in_plan_check(plan_id, missing, expected):
    assert in_plan_check(get_plan_library().get(plan_id), missing) == expected


def test_t29_in_plan_check_is_supported_without_asking():
    kept, dropped, clar = _run([_hyp()])
    assert [k["plan_id"] for k in kept] == ["qa_rv_0254"] and clar == []
    assert "precondition_in_plan:qa_rv_0254:s1" in dropped


def test_t29_latch_not_fastened_keeps_the_plan():
    """客户说门扣没扣紧：原先按「前提被否定」丢掉 rv-0254，可这正是第 1 步要处理的原因。"""
    loose = {"kind": "observation", "value": "the door latch of the dirty water tank is not fastened",
             "quote": "the latch is not fastened", "subject": "door latch of the dirty water tank",
             "polarity": "negated", "status": "active"}
    kept, dropped, clar = _run([_hyp()], facts=[loose])
    assert [k["plan_id"] for k in kept] == ["qa_rv_0254"] and clar == []
    assert not any(d.startswith("precondition_negated") for d in dropped)


def test_in_plan_check_without_covered_symptom_still_asks():
    kept, dropped, clar = _run([_hyp(supported_symptoms=[])])
    assert kept == [] and clar[0]["question"] == QUESTION
    assert "not_supported:qa_rv_0254" in dropped


def test_scene_precondition_still_asks():
    hyp = _hyp("qa_rv_0050", missing_fact="In multi-floor tasks",
               clarification_question="Was the robot running a multi-floor task?")
    kept, _, clar = _run([hyp])
    assert kept == [] and clar[0]["plan_id"] == "qa_rv_0050"


def test_not_applicable_is_still_dropped():
    kept, dropped, clar = _run([_hyp(applicability="not_applicable")])
    assert kept == [] and clar == [] and "not_supported:qa_rv_0254" in dropped


T29 = ("Product Name: eufy X10 Pro Omni Robot Vacuum and Mop Combo\nProblem Description: Water tray will not empty. "
       "I have already cleaned it, insured the hose is not pinched and insured that the connector under the dirty water "
       "tank is not pushed down. The dirty water tank is also empty. What else can I do?")


async def test_t29_first_turn_sends_the_latch_card(conversation):
    set_knowledge_adapter(QAHitAdapter("rv-0254"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        **_hyp(), "evidence_ids": ["chunk-rv-0254"]}]}]
    events = await conversation.send(T29, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
        "facts": [{"value": SYMPTOM, "quote": "Water tray will not empty.", "subject": "Water tray"}],
    })
    card = next(e["step"] for e in events if e["type"] == "step_card")
    assert card["plan_id"] == "qa_rv_0254" and card["step_id"] == "s1"
    assert QUESTION not in "".join(e.get("delta", "") for e in events)
    state = await conversation.state()
    assert not state.get("precondition_answers")
