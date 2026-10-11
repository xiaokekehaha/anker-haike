"""诊断恢复边界：否定观察、候选分页、前提澄清及真实人工交接。"""

import pytest

from app.knowledge.adapter import Hit, ToolResult
from app.knowledge.runtime import set_knowledge_adapter
from app.rules import RulesService
from app.sessions import graph
from app.settings import REPO_ROOT
from tests.conversation_runtime import REPORT, REPORT_TEXT
from tests.conversation_runtime import conversation as base_conversation_fixture
from tests.test_conversation_l3 import l3_runtime as l3_runtime_fixture

base_conversation = base_conversation_fixture
l3_runtime = l3_runtime_fixture


@pytest.fixture
async def conversation(l3_runtime, base_conversation):
    yield base_conversation


@pytest.mark.parametrize(("observation", "risk"), [
    ("未见明显破损或烧焦", False),
    ("没有裂纹、变形和冒烟", False),
    ("未见破损，但滚刷烧焦", True),
    ("未见冒烟，滚刷烧焦", True),
    ("无线充电座冒烟", True),
])
def test_coordinated_negative_observations(observation, risk):
    rules = RulesService(REPO_ROOT / "config/rules/safety_terms.yaml", hot_reload=False)
    assert rules.check_in(observations=[observation]).escalate is risk


class ManyCandidates:
    async def hybrid_search(self, kb, query, top_k, allow):
        hits = [] if kb != "kb_qa" else [
            Hit(f"c{i}", f"k{i}", f"c{i}", "rv-0271" if i == 13 else "rv-0272",
                "v1", kb, "Official robot troubleshooting guidance", 1 - i / 100)
            for i in range(15)
        ]
        return ToolResult("ok" if hits else "no_match", hits, kb=kb, query=query)


async def test_omitted_candidate_gets_second_bounded_pass(conversation):
    set_knowledge_adapter(ManyCandidates())
    model = conversation.models["diagnose.synthesize"]
    model.script = [{"hypotheses": []}, {"hypotheses": [{
        "plan_id": "qa_rv_0271", "confidence": 0.9, "evidence_ids": ["c13"],
        "applicability": "supported", "supported_symptoms": ["El robot está desconectado"],
    }]}]
    events = await conversation.send("X10 Pro Omni: El robot está desconectado", {
        "primary_intent": "report_problem", "device_relation": "current",
        "product_hints": ["X10 Pro Omni"],
        "facts": [{"value": "El robot está desconectado", "quote": "El robot está desconectado"}],
    })
    assert len(model.calls) == 2
    assert any(e["type"] == "step_card" for e in events)
    state = await conversation.state()
    assert "c13" in state["current_evidence_ids"]
    assert any(t.get("event") == "context_recovery" for t in state["retrieval_trace"])
    first_prompt = str(model.calls[0]["messages"])
    second_prompt = str(model.calls[1]["messages"])
    assert "qa_rv_0271" not in first_prompt and "qa_rv_0271" in second_prompt


async def test_first_pass_clarification_is_asked_before_recovery(conversation):
    """T36：首批 rv-0341 待确认（有追问），补查曾把被裁掉的「集尘时异响」rv-0315 判适用并顶掉追问。
    首批已有追问就先问，不再补查。"""
    set_knowledge_adapter(ManyCandidates())
    model = conversation.models["diagnose.synthesize"]
    model.script = [{"hypotheses": [{
        "plan_id": "qa_rv_0272", "confidence": 0.62, "evidence_ids": ["c0"],
        "applicability": "needs_confirmation", "supported_symptoms": [],
        "clarification_question": "Is the hair wrapped around the roller brush?",
    }]}, {"hypotheses": [{
        "plan_id": "qa_rv_0271", "confidence": 0.9, "evidence_ids": ["c13"],
        "applicability": "supported", "supported_symptoms": ["El robot está desconectado"],
    }]}]
    events = await conversation.send("X10 Pro Omni: El robot está desconectado", {
        "primary_intent": "report_problem", "device_relation": "current",
        "product_hints": ["X10 Pro Omni"],
        "facts": [{"value": "El robot está desconectado", "quote": "El robot está desconectado"}],
    })
    assert len(model.calls) == 1
    assert not any(e["type"] == "step_card" for e in events)
    assert "Is the hair wrapped" in "".join(e.get("delta", "") for e in events)
    state = await conversation.state()
    assert not any(t.get("event") == "context_recovery" for t in state["retrieval_trace"])


async def test_supported_first_pass_does_not_retry(conversation):
    set_knowledge_adapter(ManyCandidates())
    conversation.models["diagnose.synthesize"].script[0]["hypotheses"][0]["evidence_ids"] = ["c0"]
    await conversation.send(REPORT_TEXT, REPORT)
    assert len(conversation.models["diagnose.synthesize"].calls) == 1


async def test_recovery_respects_deadline(conversation, monkeypatch):
    set_knowledge_adapter(ManyCandidates())
    monkeypatch.setattr(graph, "_remaining_ms", lambda state: 2500)
    model = conversation.models["diagnose.synthesize"]
    model.script = [{"hypotheses": []}]
    events = await conversation.send(REPORT_TEXT, REPORT)
    assert len(model.calls) == 1
    assert not any(e["type"] == "step_card" for e in events)
    state = await conversation.state()
    assert any(t.get("event") == "context_recovery_skipped" for t in state["retrieval_trace"])


async def test_failed_recovery_does_not_execute_unverified_plan(conversation):
    set_knowledge_adapter(ManyCandidates())
    model = conversation.models["diagnose.synthesize"]
    model.script = [{"hypotheses": []}, RuntimeError("test provider unavailable")]
    events = await conversation.send(REPORT_TEXT, REPORT)
    assert len(model.calls) == 2
    assert not any(e["type"] == "step_card" for e in events)
    assert (await conversation.state())["stage"] == "awaiting_human"


async def test_unknown_conditions_have_bounded_questions(conversation):
    candidate = {"hypotheses": [{
        "plan_id": "qa_rv_0272", "confidence": 0.8, "evidence_ids": ["c12"],
        "applicability": "needs_confirmation", "supported_symptoms": [],
        "clarification_question": "Is the hair wrapped around the roller brush?",
    }]}
    conversation.models["diagnose.synthesize"].script = [candidate] * 3
    first = await conversation.send(REPORT_TEXT, REPORT)
    second = await conversation.send("I am not sure", {"primary_intent": "answer_pending"})
    third = await conversation.send("I still cannot tell", {"primary_intent": "answer_pending"})
    assert not any(e["type"] in {"step_card", "escalation_summary"} for e in first + second)
    assert any(e["type"] == "escalation_summary" for e in third)
    assert not any(e["type"] == "step_card" for e in third)


@pytest.mark.parametrize(("plan_id", "evidence_id"), [("invented", "c12"), ("qa_rv_0272", "invented")])
async def test_ungrounded_confirmation_is_not_asked(conversation, plan_id, evidence_id):
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": plan_id, "confidence": 0.8, "evidence_ids": [evidence_id],
        "applicability": "needs_confirmation", "supported_symptoms": [],
        "clarification_question": "Is the hair wrapped around the roller brush?",
    }]}]
    events = await conversation.send(REPORT_TEXT, REPORT)
    assert "Is the hair wrapped" not in "".join(e.get("delta", "") for e in events)
    assert (await conversation.state())["stage"] == "awaiting_human"
    assert not any(e["type"] == "step_card" for e in events)


async def test_missing_condition_asks_before_operating_and_accepts_answer(conversation):
    model = conversation.models["diagnose.synthesize"]
    supported = model.script[0]
    model.script = [{"hypotheses": [{
        "plan_id": "qa_rv_0272", "confidence": 0.8, "evidence_ids": ["c12"],
        "applicability": "needs_confirmation", "supported_symptoms": [],
        "clarification_question": "Is the hair wrapped around the roller brush?",
    }]}, supported]
    events = await conversation.send(REPORT_TEXT, REPORT)
    assert not any(e["type"] in {"step_card", "escalation_summary"} for e in events)
    assert "Is the hair wrapped" in "".join(e.get("delta", "") for e in events)
    events = await conversation.send("Yes, around the roller brush.", {
        "primary_intent": "answer_pending", "device_relation": "current",
        "facts": [{"kind": "observation", "value": "Hair is wrapped around the roller brush",
                   "quote": "around the roller brush"}],
    })
    assert any(e["type"] == "step_card" for e in events)
    assert len(model.calls) == 2


@pytest.mark.parametrize("reason", ["R4", "R5"])
async def test_generic_escalation_enters_human_queue(conversation, l3_runtime, reason):
    if reason == "R4":
        text = "My X10 Pro Omni is smoking"
        meaning = {"primary_intent": "report_problem", "device_relation": "current",
                   "product_hints": ["X10 Pro Omni"], "device_safety_assertion": "reported",
                   "device_safety_quote": "is smoking",
                   "facts": [{"value": "smoking", "quote": "smoking"}]}
    else:
        text, meaning = REPORT_TEXT, REPORT
        conversation.models["diagnose.synthesize"].script = [{"hypotheses": []}]
    events = await conversation.send(text, meaning)
    state = await conversation.state()
    assert state["stage"] == "awaiting_human"
    case = await l3_runtime.cases.store.get(state["case_id"])
    assert case["status"] == "awaiting_approval"
    assert any(e["type"] == "handoff_summary" for e in case["events"])
    summary = next(e for e in events if e["type"] == "escalation_summary")
    assert summary["handoff_status"] == "requested"
    assert summary["summary"]["case_id"] == case["case_id"]
    assert not any(e["type"] in {"step_card", "execution_card"} for e in events)
    assert l3_runtime.backend.create_calls == 0


async def test_summary_retry_is_idempotent_and_refresh_does_not_requeue(conversation, l3_runtime, monkeypatch):
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": []}]
    await conversation.send(REPORT_TEXT, REPORT)
    state = await conversation.state()
    case_id = state["case_id"]
    before = await l3_runtime.cases.store.get(case_id)
    monkeypatch.setattr(graph, "get_stream_writer", lambda: lambda event: None)
    monkeypatch.setattr(graph, "get_model_router", lambda: None)
    await graph.summarize(state)
    after = await l3_runtime.cases.store.get(case_id)
    assert before["events"] == after["events"]
    await l3_runtime.cases.transition(case_id, "closed", "人工结案", actor="human")
    await graph.summarize({**state, "summary_refresh": True})
    assert (await l3_runtime.cases.store.get(case_id))["status"] == "closed"


async def test_handoff_followup_reports_real_queue_status(conversation):
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": []}]
    await conversation.send(REPORT_TEXT, REPORT)
    events = await conversation.send("Has it been handed over?", {"primary_intent": "handoff_status"})
    reply = "".join(e.get("delta", "") for e in events)
    assert "awaiting review" in reply
    assert "nothing has been handed over" not in reply
    assert not any(e["type"] in {"step_card", "execution_card"} for e in events)


async def test_failed_handoff_cannot_claim_submission(conversation, l3_runtime, monkeypatch):
    await conversation.send(REPORT_TEXT, REPORT)
    state = await conversation.state()
    emitted = []
    monkeypatch.setattr(graph, "get_stream_writer", lambda: emitted.append)
    monkeypatch.setattr(graph, "get_model_router", lambda: None)

    async def unavailable(*args, **kwargs):
        raise RuntimeError("test storage unavailable")

    monkeypatch.setattr(l3_runtime.cases, "hand_off", unavailable)
    with pytest.raises(RuntimeError, match="test storage unavailable"):
        await graph.summarize({**state, "escalate_reason": "R3"})
    assert not any(e["type"] in {"message", "escalation_summary", "case_changed"} for e in emitted)


async def test_t43_one_word_symptom_with_no_applicable_candidate_asks_once_before_handoff(conversation):
    """21:03 续测 T43：西语「El robot está desconectado」→ 症状只有一个词「desconectado」，召回 12 条全是离地 / 被困，
    synthesize 空列表 → 直接 R5。现象太笼统、检索词与英文资料对不上，不是资料没有：先请客户具体说一次，答完仍查不到再交人工。"""
    model = conversation.models["diagnose.synthesize"]
    model.script = [{"hypotheses": []}, {"hypotheses": []}]
    first = await conversation.send("X10 Pro Omni: El robot está desconectado.", {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
        "facts": [{"value": "desconectado", "quote": "El robot está desconectado."}],
    })
    assert not any(e["type"] in {"step_card", "escalation_summary"} for e in first)
    assert "describe it in a bit more detail" in "".join(e.get("delta", "") for e in first)
    assert (await conversation.state())["stage"] != "awaiting_human"
    second = await conversation.send("La app dice que el robot está sin conexión.", {
        "primary_intent": "answer_pending", "device_relation": "current",
        "facts": [{"value": "app shows the robot offline", "quote": "La app dice que el robot está sin conexión."}],
    })
    assert any(e["type"] == "escalation_summary" for e in second)
    assert len(model.calls) == 2
