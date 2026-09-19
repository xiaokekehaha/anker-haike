"""通过会话HTTP边界验证充分性补查；只替换模型与知识I/O。"""

from copy import deepcopy
from uuid import uuid4

import pytest

from app.diagnose.config import get_retrieval_config, set_retrieval_config
from app.faultcards.library import FaultCard, FaultCardLibrary, FaultCardsConfig, FaultEntry
from app.faultcards.runtime import set_fault_card_library
from app.images import InMemoryImageStore
from app.images.runtime import set_image_store
from app.knowledge.adapter import Hit, KbName, KnowledgeScope, ToolResult
from app.knowledge.runtime import set_knowledge_adapter
from app.main import app
from tests import conversation_runtime
from tests.conversation_runtime import REPORT, REPORT_TEXT
from tests.message_form import model_task_text
from tests.test_images import png_bytes

conversation = conversation_runtime.conversation


class RoundKnowledge:
    def __init__(self, rounds: dict[str, list[ToolResult]]):
        self.rounds = rounds
        self.calls: list[tuple[str, str, int, KnowledgeScope]] = []

    async def hybrid_search(self, kb: KbName, query: str, top_k: int, allow: KnowledgeScope) -> ToolResult:
        self.calls.append((kb, query, top_k, allow))
        queue = self.rounds.get(kb, [])
        result = deepcopy(queue.pop(0)) if queue else ToolResult("no_match", allowed_count=1)
        result.kb, result.query = kb, query
        return result


def evidence(eid: str, text: str = "滚刷缠绕毛发，清理后试运行") -> Hit:
    return Hit(eid, "manual", eid, "manual_rv_v1", "test", "kb_manual", text, 0.5,
               knowledge_title="当前产品维护说明", content=text)


def diagnosis(ids: list[str]) -> dict:
    return {"hypotheses": [{"plan_id": "rv_suction_hair_wrap", "confidence": 0.9, "evidence_ids": ids}]}


@pytest.fixture(autouse=True)
def rescue_config():
    cfg = get_retrieval_config().model_copy(deep=True)
    cfg.query_rewrite.enabled = True
    set_retrieval_config(cfg)
    try:
        yield cfg
    finally:
        set_retrieval_config(None)
        set_fault_card_library(None)


@pytest.mark.parametrize("coverage", ["insufficient", "none"])
async def test_inadequate_nonempty_results_are_supplemented_and_both_rounds_reach_diagnosis(conversation, coverage):
    first = [evidence(f"old-{i}") for i in range(15)]
    adapter = RoundKnowledge({"kb_manual": [ToolResult("ok", first, allowed_count=1),
                                             ToolResult("ok", [evidence("new-target")], allowed_count=1)]})
    set_knowledge_adapter(adapter)
    conversation.models["retrieve.grade"].script = [{
        "coverage": coverage,
        "items": [{"evidence_id": h.evidence_id, "verdict": "irrelevant" if i == 0 else "relevant"}
                  for i, h in enumerate(first)],
        "missing_symptoms": ["不吸了", "编造的电机损坏"],
    }]
    conversation.models["query.rewrite"].script = [{"query": "扫地机器人 不吸 滚刷缠头发"}]
    conversation.models["diagnose.synthesize"].script = [diagnosis(["old-0", "new-target"])]
    events = await conversation.send(REPORT_TEXT, REPORT)
    state = await conversation.state()
    assert len(adapter.calls) == 4 and all(call[2] == 15 for call in adapter.calls)
    assert {(call[3].product_state, call[3].category, call[3].sku) for call in adapter.calls} == {
        ("confirmed_sku", "robot_vacuum", "EUFY-X9-PRO")
    }
    assert state["knowledge_status"] == "ok" and state["retrieval_rounds"] == 2
    assert state["plans_ranked"][0]["evidence_ids"] == ["old-0", "new-target"]
    assert state["plans_ranked"][0]["source"] == "synthesize"
    selected = next(t for t in state["retrieval_trace"] if t.get("event") == "context_selected")
    assert {"old-0", "new-target"} <= set(selected["selected_ids"]) and len(selected["selected_ids"]) <= 12
    call = conversation.models["diagnose.synthesize"].calls[0]
    assert "[old-0]" in model_task_text(call) and "[new-target]" in model_task_text(call)
    rewrite_text = model_task_text(conversation.models["query.rewrite"].calls[0])
    assert "编造的电机损坏" not in rewrite_text
    assert any(event["type"] == "step_card" for event in events)


async def test_sufficient_evidence_does_not_start_second_round(conversation):
    adapter = RoundKnowledge({"kb_manual": [ToolResult("ok", [evidence("c12")], allowed_count=1)]})
    set_knowledge_adapter(adapter)
    conversation.models["retrieve.grade"].script = [{
        "coverage": "sufficient", "items": [{"evidence_id": "c12", "verdict": "relevant"}],
    }]
    await conversation.send(REPORT_TEXT, REPORT)
    assert len(adapter.calls) == 2 and conversation.models["query.rewrite"].calls == []
    assert (await conversation.state())["retrieval_rounds"] == 1


async def test_failed_assessment_allows_one_conservative_supplement(conversation):
    adapter = RoundKnowledge({"kb_manual": [ToolResult("ok", [evidence("c12")], allowed_count=1),
                                             ToolResult("ok", [evidence("new")], allowed_count=1)]})
    set_knowledge_adapter(adapter)
    conversation.models["retrieve.grade"].script = ["invalid JSON"]
    conversation.models["query.rewrite"].script = [{"query": "扫地机器人 不吸 滚刷缠头发"}]
    conversation.models["diagnose.synthesize"].script = [diagnosis(["c12", "new"])]
    await conversation.send(REPORT_TEXT, REPORT)
    state = await conversation.state()
    assert len(adapter.calls) == 4 and state["plans_ranked"][0]["source"] == "synthesize"
    decision = next(t for t in state["retrieval_trace"] if t.get("event") == "rewrite_decision")
    assert decision["reason"] == "assessment_unknown"


@pytest.mark.parametrize("second_status", ["no_match", "unavailable"])
async def test_failed_supplement_keeps_first_round_evidence(conversation, second_status):
    adapter = RoundKnowledge({"kb_manual": [ToolResult("ok", [evidence("c12")], allowed_count=1),
                                             ToolResult(second_status, allowed_count=1)]})
    set_knowledge_adapter(adapter)
    conversation.models["retrieve.grade"].script = [{
        "coverage": "insufficient", "items": [{"evidence_id": "c12", "verdict": "relevant"}],
    }]
    conversation.models["query.rewrite"].script = [{"query": "扫地机器人 不吸 滚刷缠头发"}]
    await conversation.send(REPORT_TEXT, REPORT)
    state = await conversation.state()
    assert len(adapter.calls) == 4 and state["knowledge_status"] == "ok"
    assert state["plans_ranked"][0]["evidence_ids"] == ["c12"]
    assert state["plans_ranked"][0]["source"] == "synthesize"


@pytest.mark.parametrize(("status", "allowed"), [("no_match", 0), ("unavailable", 1)])
async def test_empty_scope_or_unavailable_is_not_semantic_rescue(conversation, status, allowed):
    adapter = RoundKnowledge({kb: [ToolResult(status, allowed_count=allowed)] for kb in ("kb_manual", "kb_tickets")})
    set_knowledge_adapter(adapter)
    await conversation.send(REPORT_TEXT, REPORT)
    assert len(adapter.calls) == 2 and conversation.models["query.rewrite"].calls == []
    assert conversation.models["retrieve.grade"].calls == []


async def test_fault_card_is_assessed_and_does_not_block_inadequate_evidence_rescue(conversation):
    set_fault_card_library(FaultCardLibrary(FaultCardsConfig(version="test", cards=[FaultCard(
        key="EUFY-X9-PRO", doc_version="test", title="产品故障卡",
        faults=[FaultEntry(fault="吸力下降", plan_id="rv_suction_hair_wrap", keywords=["不吸"],
                           symptom_codes=["suction_low"], first_step="检查滚刷")],
    )])))
    fc_id = "fc:EUFY-X9-PRO:test:rv_suction_hair_wrap"
    adapter = RoundKnowledge({"kb_manual": [ToolResult("no_match", allowed_count=1),
                                             ToolResult("ok", [evidence("new")], allowed_count=1)]})
    set_knowledge_adapter(adapter)
    conversation.models["retrieve.grade"].script = [{
        "coverage": "insufficient", "items": [{"evidence_id": fc_id, "verdict": "relevant"}],
    }]
    conversation.models["query.rewrite"].script = [{"query": "扫地机器人 不吸 滚刷缠头发"}]
    conversation.models["diagnose.synthesize"].script = [diagnosis(["new", fc_id])]
    await conversation.send(REPORT_TEXT, REPORT)
    assert len(adapter.calls) == 4
    assert fc_id in model_task_text(conversation.models["retrieve.grade"].calls[0])
    assert set((await conversation.state())["plans_ranked"][0]["evidence_ids"]) == {"new", fc_id}


@pytest.fixture
def fault_images():
    store = InMemoryImageStore()
    set_image_store(store)
    app.state.image_store = store
    try:
        yield store
    finally:
        set_image_store(None)
        app.state.image_store = None


async def test_image_and_text_share_one_supplement_quota(conversation, fault_images):
    adapter = RoundKnowledge({"kb_manual": [ToolResult("ok", [evidence("c12")], allowed_count=1),
                                             ToolResult("ok", [evidence("photo-hit")], allowed_count=1)]})
    set_knowledge_adapter(adapter)
    conversation.models["intake"].script = [REPORT]
    conversation.models["diagnose.vision"].script = [{
        "observations": ["滚刷缠绕大量毛发"], "visible_parts": ["滚刷"],
    }]
    conversation.models["retrieve.grade"].script = [{
        "coverage": "insufficient", "items": [{"evidence_id": "c12", "verdict": "relevant"}],
    }]
    conversation.models["diagnose.synthesize"].script = [diagnosis(["c12", "photo-hit"])]
    before = await conversation.snapshot()
    response = await conversation.client.post(
        f"/sessions/{conversation.sid}/messages",
        data={"input_id": uuid4().hex, "expected_version": before["version"], "text": REPORT_TEXT, "purpose": "fault"},
        files=[("images", ("fault.png", png_bytes(512), "image/png"))],
    )
    conversation.check(response)
    state = await conversation.state()
    assert len(conversation.models["intake"].calls) == len(conversation.models["diagnose.vision"].calls) == 1
    assert len(adapter.calls) == 4 and "滚刷缠绕大量毛发" in adapter.calls[2][1]
    assert state["retrieval_rounds"] == 2 and state["rewrite_used"]
    assert conversation.models["query.rewrite"].calls == []
    assert state["plans_ranked"][0]["evidence_ids"] == ["c12", "photo-hit"]
    assert next(t for t in state["retrieval_trace"] if t.get("event") == "rewrite_decision")["reason"] == "quota_used"


async def test_assessment_cannot_see_text_outside_diagnosis_budget(conversation, rescue_config):
    rescue_config.retrieval.context_chars = 300
    body = "滚刷维护说明。" * 50 + "不可见尾部结论"
    adapter = RoundKnowledge({"kb_manual": [ToolResult("ok", [evidence("c12", body), evidence("other", body)], allowed_count=1)]})
    set_knowledge_adapter(adapter)
    conversation.models["retrieve.grade"].script = [{
        "coverage": "sufficient", "items": [{"evidence_id": "c12", "verdict": "relevant"}],
    }]
    await conversation.send(REPORT_TEXT, REPORT)
    for task in ("retrieve.grade", "diagnose.synthesize"):
        text = model_task_text(conversation.models[task].calls[0])
        assert "[c12]" in text and "不可见尾部结论" not in text
    selected = next(t for t in (await conversation.state())["retrieval_trace"] if t.get("event") == "context_selected")
    assert selected["context_chars"] <= 300


async def test_local_fault_card_uses_context_budget_when_adapter_disabled(conversation, rescue_config):
    rescue_config.retrieval.context_chars = 200
    set_fault_card_library(FaultCardLibrary(FaultCardsConfig(version="test", cards=[FaultCard(
        key="EUFY-X9-PRO", doc_version="test", title="产品故障卡",
        faults=[FaultEntry(fault="吸力下降", plan_id="rv_suction_hair_wrap", keywords=["不吸"],
                           symptom_codes=["suction_low"], first_step="检查滚刷" * 60 + "不可见尾部结论")],
    )])))
    set_knowledge_adapter(None)
    fc_id = "fc:EUFY-X9-PRO:test:rv_suction_hair_wrap"
    conversation.models["diagnose.synthesize"].script = [diagnosis([fc_id])]
    await conversation.send(REPORT_TEXT, REPORT)
    state = await conversation.state()
    assert state["knowledge_status"] == "unavailable" and fc_id in state["current_evidence_ids"]
    assert state["plans_ranked"][0]["source"] == "synthesize"
    selected = next(t for t in state["retrieval_trace"] if t.get("event") == "context_selected")
    assert selected["selected_ids"] == [fc_id] and selected["context_chars"] <= 200
    assert selected["shortened_ids"] == [fc_id]
    assert "不可见尾部结论" not in model_task_text(conversation.models["diagnose.synthesize"].calls[0])


async def test_second_assessment_does_not_open_a_third_round(conversation, rescue_config):
    rescue_config.grade.second_round = True
    adapter = RoundKnowledge({"kb_manual": [ToolResult("ok", [evidence("c12")], allowed_count=1),
                                             ToolResult("ok", [evidence("new")], allowed_count=1)]})
    set_knowledge_adapter(adapter)
    conversation.models["retrieve.grade"].script = [
        {"coverage": "insufficient", "items": [{"evidence_id": "c12", "verdict": "relevant"}]},
        {"coverage": "insufficient", "items": [{"evidence_id": eid, "verdict": "relevant"} for eid in ("c12", "new")]},
    ]
    conversation.models["query.rewrite"].script = [{"query": "扫地机器人 不吸 滚刷缠头发"}]
    await conversation.send(REPORT_TEXT, REPORT)
    assert len(adapter.calls) == 4 and len(conversation.models["retrieve.grade"].calls) == 2
    second_input = model_task_text(conversation.models["retrieve.grade"].calls[1])
    assert "[c12]" in second_input and "[new]" in second_input
    assert (await conversation.state())["evidence_quality"] == "insufficient"


async def test_unsolved_ticket_alone_cannot_stop_rescue(conversation):
    counter = evidence("counter", "清理滚刷后未解决")
    counter.source, counter.case_outcome, counter.counter_evidence = "kb_tickets", "unsolved", True
    adapter = RoundKnowledge({"kb_tickets": [ToolResult("ok", [counter], allowed_count=1)]})
    set_knowledge_adapter(adapter)
    conversation.models["retrieve.grade"].script = [{
        "coverage": "sufficient", "items": [{"evidence_id": "counter", "verdict": "relevant"}],
    }]
    conversation.models["query.rewrite"].script = [{"query": "扫地机器人 不吸 滚刷缠头发"}]
    await conversation.send(REPORT_TEXT, REPORT)
    state = await conversation.state()
    assert len(adapter.calls) == 4
    assert "未解决工单" in model_task_text(conversation.models["retrieve.grade"].calls[0])
    assert next(t for t in state["retrieval_trace"] if t.get("event") == "rewrite_decision")["reason"] == "insufficient_evidence"
