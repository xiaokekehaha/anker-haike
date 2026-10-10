"""An unavailable referenced instruction is a coverage gap, not a complete answer."""

import pytest

from app.guide.steps import prepare_step
from app.knowledge.runtime import set_knowledge_adapter
from app.official.models import QAEntry
from app.official.qa_index import QAIndex, build_guide
from app.plans.qa import qa_plan_library
from app.rules import RulesService
from app.settings import REPO_ROOT
from tests.conversation_runtime import conversation as conversation_fixture
from tests.fake_qa import QAHitAdapter

conversation = conversation_fixture


@pytest.mark.parametrize("content,gap", [
    ("Suggested troubleshooting steps can be found at:", True),
    ("The instructions are available at:", True),
    ("The instructions are listed below:", True),
    ("The instructions are available at:\nhttps://example.test/guide", False),
    ("The instructions are listed below:\nRestart the device.", False),
    ("The device will return to the station when power is low.", False),
])
def test_only_explicitly_dangling_source_references_are_marked(content, gap):
    guide = build_guide(QAEntry(id="test-1", sheet="test", directory=["QA", "Robot"], title="Example",
                               content=content, visible=True, pn=["T2080"], pdt=""), {})
    assert guide.steps[0].source_gap is gap
    assert guide.answer == content.replace("https://example.test/guide", "").strip()


@pytest.mark.parametrize("lead", ["", "1. The device may consume fluid gradually.\n2. ", "1. Check the tank.\n2. "])
async def test_source_gap_preserves_evidence_without_an_operation(lead):
    guide = build_guide(QAEntry(id="test-1", sheet="test", directory=["QA", "Robot"], title="Example",
        content=lead + "Further instructions can be found at:", visible=True, pn=["T2080"], pdt=""), {})
    step_id = "s2" if "Check" in lead else "s1"
    result = await prepare_step(
        state={"plan_cursor": {"plan_id": guide.plan_id, "step_id": step_id},
               "category": "robot_vacuum", "product_confirmed": {"sku": "T2080"}},
        library=qa_plan_library(QAIndex(guides={guide.qa_id: guide}, version="test")),
        rules=RulesService(REPO_ROOT / "config/rules/safety_terms.yaml", hot_reload=False),
        router=None, lane="domestic", session_id="source-gap",
    )
    assert result.outcome == "source_gap" and result.step is None and result.card_id is None
    assert "does not include them or a link" in result.explanation and result.evidence
    assert result.dropped[-1]["reason"] == "source_reference_missing"


async def test_http_incomplete_official_source_is_not_marked_answered(conversation):
    set_knowledge_adapter(QAHitAdapter("rv-0371"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_rv_0371", "confidence": 0.9, "evidence_ids": ["chunk-rv-0371"],
        "applicability": "supported", "supported_symptoms": ["cleaning solution stays at 660ml"],
    }]}]
    events = await conversation.send("Product PN: T2080\nProblem Description: cleaning solution stays at 660ml", {
        "primary_intent": "report_problem", "device_relation": "current",
        "facts": [{"value": "cleaning solution stays at 660ml", "quote": "cleaning solution stays at 660ml"}],
    })
    state = await conversation.state()
    assert not state["consult_answered"] and not state["steps_executed"]
    assert state["escalate_reason"] == "R5"
    assert any(t["event"] == "knowledge_source_gap" for t in state["guide_trace"])
    text = "".join(e.get("delta", "") for e in events)
    assert "does not include them or a link" in text and "found at:" not in text
    assert not any(e["type"] == "step_card" for e in events)
