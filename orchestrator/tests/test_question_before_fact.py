"""问句先对事实（2026-10-10 第 3 项）。

- T53 第十轮：用户已说「stoped turning on」，bp-0114 仍让在「无法开机 / 加热故障」里二选一。
  模型核实现象属于哪个小节（matched_section），服务端校验它逐字等于首问的选项后替用户记一条回答，直接发该小节首步。
- T41 第十轮：用户已说「we have not run mop cycles」，模型 needs_confirmation 还问「不跑拖地是否也报错」。
  模型给出要确认的前提（missing_fact），服务端与事实比对：否定事实覆盖 → 不适用也不问；肯定的已做 / 已观察 → 当作成立。
不加同义词表，不按 QA 编号判断。
"""

from __future__ import annotations

import pytest

from app.diagnose.synthesize import filter_hypotheses, precondition_status
from app.knowledge.runtime import set_knowledge_adapter
from app.plans.qa import qa_plan_library
from tests.conversation_runtime import conversation as base_conversation_fixture
from tests.fake_qa import QAHitAdapter
from tests.test_conversation_l3 import l3_runtime as l3_runtime_fixture

base_conversation = base_conversation_fixture
l3_runtime = l3_runtime_fixture
LIB = qa_plan_library()


@pytest.fixture
async def conversation(l3_runtime, base_conversation):
    yield base_conversation


def _hyp(pid, **extra):
    return {"plan_id": pid, "confidence": 0.9, "evidence_ids": ["e1"], "applicability": "supported",
            "supported_symptoms": ["stoped turning on"], **extra}


def _run(hyps, facts=(), symptoms=("stoped turning on",)):
    return filter_hypotheses(hyps, allowed={"qa_bp_0114": LIB.get("qa_bp_0114"), "qa_rv_0146": LIB.get("qa_rv_0146")},
                             evidence_ids={"e1"}, symptoms=set(symptoms), facts=list(facts), max_n=3)


# ---- matched_section ----

def test_verified_section_is_kept_and_unverified_is_dropped():
    kept, dropped, _ = _run([_hyp("qa_bp_0114", matched_section="Breast pump cannot be turned on")])
    assert kept[0]["matched_section"] == "Breast pump cannot be turned on"
    kept, dropped, _ = _run([_hyp("qa_bp_0114", matched_section="cannot be turned on")])  # 不逐字
    assert "matched_section" not in kept[0] and "section_unverified:qa_bp_0114" in dropped


def test_section_on_a_plan_without_branches_is_ignored():
    kept, dropped, _ = _run([_hyp("qa_rv_0146", matched_section="Anything")])
    assert "matched_section" not in kept[0] and "section_unverified:qa_rv_0146" in dropped


# ---- missing_fact vs facts ----

NOT_RUN_MOP = {"kind": "symptom", "value": "have not run mop cycles", "quote": "we have not run mop cycles",
               "subject": "mop cycles", "polarity": "negated", "status": "active"}


@pytest.mark.parametrize("missing, facts, expected", [
    ("perform a new mopping task", [NOT_RUN_MOP], "negated"),
    ("perform a new mopping task", [{"kind": "action_taken", "value": "ran a mop cycle", "quote": "ran a mop cycle", "polarity": "affirmed"}], "affirmed"),
    # 症状词面相近不算已知：前提仍要问
    ("perform a new mopping task", [{"kind": "symptom", "value": "mop not dried", "quote": "mop not dried", "polarity": "affirmed"}], "unknown"),
    ("the error appears", [NOT_RUN_MOP], "unknown"),  # 只有泛词，不算覆盖
    ("firmware updated to the latest version", [NOT_RUN_MOP], "unknown"),
    (None, [NOT_RUN_MOP], "unknown"),
    # 只共享一个内容词不是同一前提（T37：「水管正常」不能证明「App 显示水量不准」，讲 App 估算的 rv-0163 被当成前提已知）
    ("water volume displayed in the app is inaccurate",
     [{"kind": "observation", "value": "Slang in tank is in orde", "quote": "Slang in tank is in orde.", "polarity": "affirmed"}], "unknown"),
])
def test_precondition_status(missing, facts, expected):
    assert precondition_status(missing, facts)[0] == expected


def test_negated_precondition_drops_without_asking():
    hyp = _hyp("qa_rv_0146", applicability="needs_confirmation", supported_symptoms=["failed drying"],
               clarification_question="Does the drying error appear even when no mop cycle has been run?",
               missing_fact="perform a new mopping task")
    kept, dropped, clar = _run([hyp], facts=[NOT_RUN_MOP], symptoms=("failed drying",))
    assert kept == [] and clar == [] and "precondition_negated:qa_rv_0146" in dropped


def test_known_precondition_promotes_to_supported():
    hyp = _hyp("qa_rv_0146", applicability="needs_confirmation", supported_symptoms=["mop still damp"],
               clarification_question="Have you run a mopping task?", missing_fact="perform a new mopping task")
    done = {"kind": "action_taken", "value": "ran a mop cycle", "quote": "ran a mop cycle", "polarity": "affirmed"}
    kept, dropped, clar = _run([hyp], facts=[done], symptoms=("mop still damp",))
    assert [k["plan_id"] for k in kept] == ["qa_rv_0146"] and clar == []
    assert "precondition_known:qa_rv_0146" in dropped


def test_unknown_precondition_still_asks():
    hyp = _hyp("qa_rv_0146", applicability="needs_confirmation", supported_symptoms=["mop still damp"],
               clarification_question="Have you run a mopping task since the update?", missing_fact="perform a new mopping task")
    kept, _, clar = _run([hyp], facts=[], symptoms=("mop still damp",))
    assert kept == [] and clar[0]["question"].startswith("Have you run")


# ---- HTTP：T53 直落小节首步 ----

T53 = ("Order No: Anker015\nProduct Name: eufy Wearable Breast Pump S1 Pro\nProblem Description: One side of the pump "
       "stoped working. I tried to charge it over and over again but it stoped turning on. I hope you can fix it.")


async def test_t53_known_fault_skips_the_section_question(conversation):
    set_knowledge_adapter(QAHitAdapter("bp-0114"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_bp_0114", "confidence": 0.9, "evidence_ids": ["chunk-bp-0114"],
        "applicability": "supported", "supported_symptoms": ["stoped turning on"],
        "matched_section": "Breast pump cannot be turned on",
    }]}]
    events = await conversation.send(T53, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["S1 Pro breast pump"],
        "facts": [{"value": "stoped turning on", "quote": "it stoped turning on", "subject": "it"}],
    })
    card = next(e["step"] for e in events if e["type"] == "step_card")
    assert card["plan_id"] == "qa_bp_0114" and card["step_id"] == "s2" and card["kind"] == "action"
    state = await conversation.state()
    recorded = [s for s in state["step_attempts"] if s["step_id"] == "select_scope"]
    assert recorded and recorded[0]["answer"] == {"option": "Breast pump cannot be turned on", "source": "fact"}
    assert (state.get("counters") or {}).get("executed", 0) == 0
    assert any(t.get("event") == "question_answered_from_facts" for t in state["guide_trace"])


async def test_t53_without_verified_section_still_asks(conversation):
    set_knowledge_adapter(QAHitAdapter("bp-0114"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_bp_0114", "confidence": 0.9, "evidence_ids": ["chunk-bp-0114"],
        "applicability": "supported", "supported_symptoms": ["stoped working"],
    }]}]
    events = await conversation.send("My S1 Pro breast pump stoped working", {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["S1 Pro breast pump"],
        "facts": [{"value": "stoped working", "quote": "stoped working"}],
    })
    card = next(e["step"] for e in events if e["type"] == "step_card")
    assert card["step_id"] == "select_scope" and card["kind"] == "question"
