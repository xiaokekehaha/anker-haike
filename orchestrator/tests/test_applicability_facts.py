"""适用性核对用结构化事实（2026-10-09 官方 63 单 I2 / I3：T18 T30 T50 T52 T61）。

模型与知识库均为假；检查的是服务端对候选方案的确定性核对，不是模型自觉。
"""

import pytest

from app.diagnose.synthesize import filter_hypotheses
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


T18 = (
    "Productnaam: Omni E28\nProduct-PN: T2352\nProbleemtype: WARNING\nProbleemcode: 3212-De mop is vastgezet.\n"
    "Probleempush: De mop met rol is verstopt, gelieve schoon te maken.\n"
    "Probleembeschrijving: Nieuw uit de doos. Toch de melding mop obstructed. Hoe los ik dit op?\n"
)


async def test_exact_steps_code_skips_model_applicability(conversation):
    """T18 / T30：同型号同错误码精确命中步骤类 Q&A → 直接发该方案首步，不再让模型判适用性，也不追问错误码。"""
    set_knowledge_adapter(QAHitAdapter("rv-0148"))
    model = conversation.models["diagnose.synthesize"]
    model.script = [{"hypotheses": []}]
    events = await conversation.send(T18, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["Omni E28"],
        "facts": [{"value": "mop obstructed", "quote": "mop obstructed"}],
    })
    card = next(e for e in events if e["type"] == "step_card")
    assert card["step"]["plan_id"] == "qa_rv_0147"
    assert model.calls == []
    state = await conversation.state()
    assert state["plans_ranked"][0]["source"] == "exact_code"
    assert state["error_codes"] == ["3212"]
    assert state["retrieval_trace"][0]["status"] == "exact_code_steps"


def _allowed(*ids):
    return {pid: LIB.get(pid) for pid in ids}


def _hyp(pid, **extra):
    return {"plan_id": pid, "confidence": 0.9, "evidence_ids": ["e1"], "applicability": "supported",
            "supported_symptoms": ["the left one does work"], **extra}


def test_uncertain_polarity_forces_clarification():
    """T50：唯一症状的极性不确定 → 不能 supported，澄清问哪一侧、什么现象。"""
    facts = [{"kind": "symptom", "value": "the left one does work", "quote": "the left one does work",
              "subject": "left pump", "polarity": "uncertain", "status": "active"}]
    kept, dropped, clar = filter_hypotheses(
        [_hyp("qa_bp_0020")], allowed=_allowed("qa_bp_0020"), evidence_ids={"e1"},
        symptoms={"the left one does work"}, facts=facts, error_codes=[], max_n=3,
    )
    assert kept == [] and "polarity_uncertain:qa_bp_0020" in dropped
    assert clar and "Which side or part" in clar[0]["question"] and "the left one does work" in clar[0]["question"]


def test_timing_direction_mismatch_is_not_supported():
    """T61：「提前两小时启动」对「无法按时启动（7051）」是方向矛盾。"""
    facts = [{"kind": "symptom", "value": "starts 2 hours before schedule", "quote": "going off 2 hours before",
              "subject": "schedule", "polarity": "affirmed", "timing": "2 hours before", "status": "active"}]
    kept, dropped, clar = filter_hypotheses(
        [_hyp("qa_rv_0522", supported_symptoms=["starts 2 hours before schedule"], matched_timing="failed to start")],
        allowed=_allowed("qa_rv_0522"), evidence_ids={"e1"}, symptoms={"starts 2 hours before schedule"},
        facts=facts, error_codes=[], max_n=3,
    )
    assert kept == [] and "timing_mismatch:qa_rv_0522" in dropped
    assert "2 hours before" in clar[0]["question"]


def test_subject_level_mismatch_asks_about_the_part_itself():
    """T52：用户说的是盒子自身充不进电，候选讲的是泵在盒子里充不上电。"""
    facts = [{"kind": "symptom", "value": "charging case will not charge", "quote": "My charging case will not charge",
              "subject": "charging case", "polarity": "affirmed", "status": "active"}]
    kept, dropped, clar = filter_hypotheses(
        [_hyp("qa_bp_0067", supported_symptoms=["charging case will not charge"], matched_subject="pump in the case")],
        allowed=_allowed("qa_bp_0067"), evidence_ids={"e1"}, symptoms={"charging case will not charge"},
        facts=facts, error_codes=[], max_n=3,
    )
    assert kept == [] and "charging_recipient_mismatch:qa_bp_0067" in dropped
    assert "charging case itself" in clar[0]["question"]


def test_matching_model_subject_cannot_override_official_recipient():
    facts = [{"kind": "symptom", "value": "charging case will not charge", "quote": "x",
              "subject": "charging case", "polarity": "affirmed", "status": "active"}]
    kept, dropped, _ = filter_hypotheses(
        [_hyp("qa_bp_0067", supported_symptoms=["charging case will not charge"], matched_subject="charging case")],
        allowed=_allowed("qa_bp_0067"), evidence_ids={"e1"}, symptoms={"charging case will not charge"},
        facts=facts, error_codes=[], max_n=3,
    )
    assert kept == [] and "charging_recipient_mismatch:qa_bp_0067" in dropped


def test_different_code_same_model_is_not_applicable():
    facts = [{"kind": "symptom", "value": "mop obstructed", "quote": "x", "polarity": "affirmed", "status": "active"}]
    kept, dropped, clar = filter_hypotheses(
        [_hyp("qa_rv_0522", supported_symptoms=["mop obstructed"], applicability="needs_confirmation",
              clarification_question="Does the app show 7051?")],
        allowed=_allowed("qa_rv_0522"), evidence_ids={"e1"}, symptoms={"mop obstructed"},
        facts=facts, error_codes=["3212"], max_n=3,
    )
    assert kept == [] and "code_mismatch:qa_rv_0522" in dropped and clar == []


def test_clarification_never_asks_a_known_code():
    facts = [{"kind": "symptom", "value": "mop obstructed", "quote": "x", "polarity": "affirmed", "status": "active"}]
    _, _, clar = filter_hypotheses(
        [_hyp("qa_rv_0147", supported_symptoms=["mop obstructed"], applicability="needs_confirmation",
              clarification_question="Does the app show 3212 or 3202?")],
        allowed=_allowed("qa_rv_0147"), evidence_ids={"e1"}, symptoms={"mop obstructed"},
        facts=facts, error_codes=["3212"], max_n=3,
    )
    assert clar == []


# ---- §3 首轮 operation_update 不绕过检索（T31）；§4 no_match 先澄清再交接（T60）----

T31 = (
    "Product Name: S1 Pro\nProduct PN: T2080A\nProblem Type: Ask Us\n"
    "Problem Description: The robot won't charge when it is at the base station despite wiping clean the electrical connections "
    "and the robot can't get past critical low battery\n"
)


async def test_first_turn_operation_phrase_still_retrieves(conversation):
    """T31：模型把「despite wiping clean」读成操作条件变更；从未排障的问题不能因此跳过检索直接 R2。"""
    set_knowledge_adapter(QAHitAdapter("rv-0364"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_rv_0364", "confidence": 0.9, "evidence_ids": ["chunk-rv-0364"],
        "applicability": "supported", "supported_symptoms": ["won't charge at the base station"],
    }]}]
    events = await conversation.send(T31, {
        "primary_intent": "report_problem", "device_relation": "current",
        "facts": [{"value": "won't charge at the base station", "quote": "The robot won't charge when it is at the base station"}],
        "operation_update": {"signal": "device_ready", "quote": "The robot won't charge when it is at the base station"},
    })
    assert any(e["type"] == "step_card" for e in events)
    state = await conversation.state()
    assert state["escalate_reason"] is None
    assert any(t.get("event") == "context_selected" for t in state["retrieval_trace"])


class NoMatch:
    async def hybrid_search(self, kb, query, top_k, allow):
        from app.knowledge.adapter import ToolResult
        return ToolResult("no_match", [], kb=kb, query=query)


async def test_no_match_without_symptom_fact_asks_before_handoff(conversation):
    """T60：只有情绪和「想让它正常清扫」、没有现象也没有错误码，知识库无命中 → 先问现象，两次无效后才交人工。"""
    set_knowledge_adapter(NoMatch())
    text = "This app is shit . I just want my X10 Pro Omni to clean with out all this bullshit"
    meaning = {"primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
               "emotion_level": "angry", "emotion_cues": ["shit"], "facts": []}
    first = await conversation.send(text, meaning)
    assert not any(e["type"] == "escalation_summary" for e in first)
    assert "describe what the device is doing" in "".join(e.get("delta", "") for e in first)
    second = await conversation.send("it just doesn't work", {**meaning, "primary_intent": "answer_pending"})
    assert not any(e["type"] == "escalation_summary" for e in second)
    third = await conversation.send("I told you, it doesn't work", {**meaning, "primary_intent": "answer_pending"})
    assert any(e["type"] == "escalation_summary" for e in third)
    assert (await conversation.state())["escalate_reason"] == "R5"


async def test_no_match_with_a_real_symptom_still_hands_off(conversation):
    set_knowledge_adapter(NoMatch())
    events = await conversation.send("X10 Pro Omni keeps spinning in circles and never docks", {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
        "facts": [{"value": "spins in circles and never docks", "quote": "keeps spinning in circles and never docks"}],
    })
    assert any(e["type"] == "escalation_summary" for e in events)


# ---- 复测 2026-10-09 17:13 回归：设备级主语不算对象冲突（T55 / T36 / T62）----

def test_device_level_subject_does_not_conflict_with_a_part():
    """用户说「my X10 / the pump / stofzuiger」时 subject 是整机或品类词，候选讲具体部件不算层级冲突。"""
    facts = [{"kind": "symptom", "value": "clicks but does not suction", "quote": "x",
              "subject": "left pump", "polarity": "affirmed", "status": "active"}]
    kept, dropped, _ = filter_hypotheses(
        [_hyp("qa_bp_0102", supported_symptoms=["clicks but does not suction"], matched_subject="motor")],
        allowed=_allowed("qa_bp_0102"), evidence_ids={"e1"}, symptoms={"clicks but does not suction"},
        facts=facts, error_codes=[], max_n=3,
    )
    assert [k["plan_id"] for k in kept] == ["qa_bp_0102"] and dropped == []


@pytest.mark.parametrize("subject", ["stofzuiger", "eufy omni c 20", "X10 Pro Omni", "the robot", "my pump", "left one"])
def test_whole_device_subjects_are_ignored(subject):
    facts = [{"kind": "symptom", "value": "loud noise", "quote": "x", "subject": subject, "polarity": "affirmed", "status": "active"}]
    kept, _, _ = filter_hypotheses(
        [_hyp("qa_rv_0341", supported_symptoms=["loud noise"], matched_subject="roller brush and cover")],
        allowed=_allowed("qa_rv_0341"), evidence_ids={"e1"}, symptoms={"loud noise"},
        facts=facts, error_codes=[], max_n=3,
    )
    assert [k["plan_id"] for k in kept] == ["qa_rv_0341"]


def test_part_level_subject_still_conflicts():
    facts = [{"kind": "symptom", "value": "charging case will not charge", "quote": "x",
              "subject": "charging case", "polarity": "affirmed", "status": "active"}]
    kept, dropped, _ = filter_hypotheses(
        [_hyp("qa_bp_0067", supported_symptoms=["charging case will not charge"], matched_subject="pump hub")],
        allowed=_allowed("qa_bp_0067"), evidence_ids={"e1"}, symptoms={"charging case will not charge"},
        facts=facts, error_codes=[], max_n=3,
    )
    assert kept == [] and "charging_recipient_mismatch:qa_bp_0067" in dropped


def test_same_head_noun_is_not_a_subject_conflict():
    """T29 复跑：用户说 Water tray，候选讲 cleaning tray / dirty water tank；同一类部件的不同叫法不是对象冲突。"""
    facts = [{"kind": "symptom", "value": "Water tray will not empty", "quote": "x",
              "subject": "Water tray", "polarity": "affirmed", "status": "active"}]
    kept, dropped, _ = filter_hypotheses(
        [_hyp("qa_rv_0270", supported_symptoms=["Water tray will not empty"], matched_subject="cleaning tray")],
        allowed=_allowed("qa_rv_0270"), evidence_ids={"e1"}, symptoms={"Water tray will not empty"},
        facts=facts, error_codes=[], max_n=3,
    )
    assert [k["plan_id"] for k in kept] == ["qa_rv_0270"] and dropped == []


@pytest.mark.parametrize(("subject", "candidate"), [
    ("Eufy S1 pro breast pump", "duckbill valve and diaphragm"),   # 产品名含 pump，仍是整机（T54）
    ("floor detergent", "cleaning solution bottle"),               # 耗材对它的容器 / 液位（T40）
    ("floor detergent", "clean water tank / clean water level"),
    ("app", "robot"),                                              # App 侧现象对机器人：不是部件层级
])
def test_product_names_and_consumables_do_not_conflict(subject, candidate):
    facts = [{"kind": "symptom", "value": "x", "quote": "x", "subject": subject, "polarity": "affirmed", "status": "active"}]
    kept, dropped, _ = filter_hypotheses(
        [_hyp("qa_rv_0341", supported_symptoms=["x"], matched_subject=candidate)],
        allowed=_allowed("qa_rv_0341"), evidence_ids={"e1"}, symptoms={"x"}, facts=facts, error_codes=[], max_n=3,
    )
    assert [k["plan_id"] for k in kept] == ["qa_rv_0341"], dropped


def test_container_synonyms_are_not_a_subject_conflict():
    """T29 第二批复测：「Water tray」对「dirty water tank」是同一类容器的不同叫法，不是对象不同。"""
    facts = [{"kind": "symptom", "value": "Water tray will not empty", "quote": "x",
              "subject": "Water tray", "polarity": "affirmed", "status": "active"}]
    kept, dropped, _ = filter_hypotheses(
        [_hyp("qa_rv_0254", supported_symptoms=["Water tray will not empty"], matched_subject="dirty water tank")],
        allowed=_allowed("qa_rv_0254"), evidence_ids={"e1"}, symptoms={"Water tray will not empty"},
        facts=facts, error_codes=[], max_n=3,
    )
    assert [k["plan_id"] for k in kept] == ["qa_rv_0254"], dropped
