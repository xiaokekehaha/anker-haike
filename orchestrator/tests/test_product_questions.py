"""产品功能咨询通过真实 HTTP 图确认型号、恢复原问题并检索；外部 I/O 全部替换。"""

import json

import httpx
import pytest

from app.knowledge.adapter import WeKnoraKnowledgeAdapter
from app.knowledge.runtime import set_knowledge_adapter
from app.knowledge.weknora_client import WeKnoraClient
from tests.conversation_runtime import REPORT, REPORT_TEXT, Conversation
from tests.conversation_runtime import conversation as conversation_fixture
from tests.fake_weknora import FakeWeKnora

conversation = conversation_fixture

QUESTION = "如何使用自定义吸奶节奏功能？"
DIRECT = QUESTION + " 型号 T8D04"
ANSWER = "打开 eufy Baby app，连接吸奶器，在设置中选择 Custom Rhythm，设置每段模式和时长，最多保存 5 组。"


@pytest.fixture
async def knowledge(conversation: Conversation):
    server = FakeWeKnora()
    server.kbs["qa"] = {"id": "qa"}
    for kid, sku, category in (("pump", "T8D04", "breast_pump"), ("robot", "T2080", "robot_vacuum")):
        server.knowledge[kid] = {
            "id": kid,
            "knowledge_base_id": "qa",
            "title": "bp-0001" if kid == "pump" else "robot-only",
            "content": f"{QUESTION}\n{DIRECT}\n{ANSWER}" if kid == "pump" else f"{QUESTION}\n不得用于吸奶器的扫地机说明",
            "parse_status": "completed",
            "custom_metadata": {"scope": "sku", "sku_list": sku, "category": category, "doc_id": "bp-0001" if kid == "pump" else "robot-only", "doc_version": "test"},
        }
    searches = []

    def handle(request: httpx.Request):
        if request.url.path.endswith("/hybrid-search"):
            searches.append(json.loads(request.content))
        return server.handle(request)

    async with WeKnoraClient("http://fake", server.api_key, transport=httpx.MockTransport(handle)) as client:
        set_knowledge_adapter(WeKnoraKnowledgeAdapter(client, {"kb_qa": "qa"}))
        conversation.models["reply.stream"].script = [[ANSWER]]
        yield server, searches


async def test_model_supplement_resumes_original_product_question(conversation, knowledge):
    await conversation.send(QUESTION, {"primary_intent": "product_question", "device_relation": "current"})
    first = await conversation.state()
    assert first["product_question"]["question"] == QUESTION
    assert first["product_question"]["status"] == "awaiting_product"
    assert not knowledge[1]
    assert not conversation.models["reply.stream"].calls

    # 重现原会话第二轮仍被归 explain；任务应依据型号补充继续，而不丢失原问题。
    events = await conversation.send("S1 Pro 穿戴式吸奶器，型号 T8D04", {
        "primary_intent": "explain", "device_relation": "current", "product_hints": ["T8D04"],
    })
    state = await conversation.state()
    assert state["product_confirmed"]["sku"] == "T8D04"
    assert state["product_question"]["question"] == QUESTION
    assert state["product_question"]["status"] == "answered"
    assert knowledge[1][0]["query_text"] == QUESTION
    assert knowledge[1][0]["knowledge_ids"] == ["pump"]
    assert any(e["type"] == "evidence" and e["items"][0]["doc_id"] == "bp-0001" for e in events)
    assert not any(e["type"] == "step_card" for e in events)
    assert not conversation.models["diagnose.synthesize"].calls
    assert not state.get("symptoms")
    assert not state.get("steps_executed")
    messages = str(conversation.models["reply.stream"].calls)
    assert QUESTION in messages and ANSWER in messages
    assert "不得用于吸奶器" not in messages


async def test_direct_product_question_uses_knowledge_without_symptom_interview(conversation, knowledge):
    events = await conversation.send(DIRECT, {
        "primary_intent": "product_question", "product_hints": ["T8D04"], "device_relation": "current",
    })
    state = await conversation.state()
    assert state["product_confirmed"]["sku"] == "T8D04"
    assert state["knowledge_status"] == "ok"
    assert any(e["type"] == "message" and ANSWER in e["delta"] for e in events)
    assert not state.get("pending_card")
    assert not state.get("symptom_interview")


async def test_same_name_requires_category_then_resumes_question(conversation, knowledge):
    await conversation.send(QUESTION, {"primary_intent": "product_question"})
    await conversation.send("S1 Pro", {"primary_intent": "supplement", "product_hints": ["S1 Pro"]})
    assert not knowledge[1]
    state = await conversation.state()
    assert state["product_question"]["status"] == "awaiting_product"
    assert state.get("product_confirmed") is None
    await conversation.send("吸奶器", {"primary_intent": "supplement", "device_category": "breast_pump"})
    assert knowledge[1][0]["query_text"] == QUESTION
    assert knowledge[1][0]["knowledge_ids"] == ["pump"]


async def test_explicit_model_number_resolves_shared_product_name(conversation, knowledge):
    await conversation.send(QUESTION, {"primary_intent": "product_question"})
    await conversation.send("S1 Pro，T8D04", {
        "primary_intent": "supplement", "product_hints": ["S1 Pro", "T8D04"],
    })
    assert knowledge[1][0]["knowledge_ids"] == ["pump"]
    assert (await conversation.state())["product_confirmed"]["sku"] == "T8D04"


async def test_unknown_model_does_not_reuse_previous_identity(conversation, knowledge):
    await conversation.send(DIRECT, {"primary_intent": "product_question", "product_hints": ["T8D04"]})
    await conversation.send("T9999 如何设置节奏？", {
        "primary_intent": "product_question", "product_hints": ["T9999"],
    })
    assert len(knowledge[1]) == 1
    assert (await conversation.state())["product_question"]["status"] == "awaiting_product"
    await conversation.send("吸奶器", {"primary_intent": "supplement", "device_category": "breast_pump"})
    assert len(knowledge[1]) == 1
    assert (await conversation.state())["product_question"]["status"] == "awaiting_product"


async def test_new_question_reuses_confirmed_product_without_consuming_diagnostic_card(conversation):
    await conversation.send(REPORT_TEXT, REPORT)
    before = await conversation.state()
    searches = len(conversation.knowledge.calls)
    await conversation.send("如何设置定时清扫？", {"primary_intent": "product_question"})
    after = await conversation.state()
    assert len(conversation.knowledge.calls) == searches + 1
    assert after["product_question"]["question"] == "如何设置定时清扫？"
    assert after["product_confirmed"] == before["product_confirmed"]
    assert after["pending_card"] == before["pending_card"]
    assert after.get("steps_executed") == before.get("steps_executed")


@pytest.mark.parametrize("failure", ["empty", "down"])
async def test_missing_knowledge_does_not_generate_instructions(conversation, knowledge, failure):
    server, _ = knowledge
    if failure == "empty":
        server.knowledge["pump"]["content"] = "无关内容"
    else:
        server.down = True
    events = await conversation.send(DIRECT, {"primary_intent": "product_question", "product_hints": ["T8D04"]})
    text = "".join(e["delta"] for e in events if e["type"] == "message")
    assert ("未找到" if failure == "empty" else "暂不可用") in text
    assert not conversation.models["reply.stream"].calls
    state = await conversation.state()
    assert state["knowledge_status"] == ("no_match" if failure == "empty" else "unavailable")
    assert not state.get("pending_card")


async def test_history_detour_preserves_pending_product_question(conversation, knowledge):
    await conversation.send(QUESTION, {"primary_intent": "product_question"})
    await conversation.send("我刚才问了什么？", {"primary_intent": "history_query"})
    assert not knowledge[1]
    assert (await conversation.state())["product_question"]["question"] == QUESTION
    await conversation.send("T8D04", {"primary_intent": "supplement", "product_hints": ["T8D04"]})
    assert knowledge[1][0]["query_text"] == QUESTION


async def test_step_explanation_keeps_pending_card_and_does_not_search_again(conversation):
    await conversation.send(REPORT_TEXT, REPORT)
    before = await conversation.state()
    searches = len(conversation.knowledge.calls)
    await conversation.send("刚才这一步为什么要做？", {"primary_intent": "explain"})
    after = await conversation.state()
    assert len(conversation.knowledge.calls) == searches
    assert after["pending_card"]["card_id"] == before["pending_card"]["card_id"]
    assert after.get("steps_executed") == before.get("steps_executed")


async def test_new_issue_does_not_inherit_question(conversation, knowledge):
    await conversation.send(QUESTION, {"primary_intent": "product_question"})
    first = (await conversation.state())["active_issue_id"]
    await conversation.send("另外一台扫地机器人有问题", {
        "primary_intent": "new_issue", "device_relation": "other", "device_category": "robot_vacuum",
    })
    state = await conversation.state()
    assert state["active_issue_id"] != first
    assert not state.get("product_question")
    assert state["issues"][first]["product_question"]["question"] == QUESTION
    assert not knowledge[1]
