"""Exercise history target resolution through HTTP, checkpoints and reply context."""

import json

import pytest

from tests.conversation_runtime import conversation as conversation  # noqa: PLC0414


@pytest.mark.parametrize("mode", ["reference", "follow_up"])
async def test_answer_followup_recalls_original_exchange(conversation, mode):
    c = conversation
    await c.send("币圈怎么来支付", {"primary_intent": "new_issue"}, input_id="payment")
    original = next(e for e in (await c.snapshot())["timeline"] if e["kind"] == "assistant_message")
    c.models["reply.stream"].script = [["您刚问的是：币圈怎么来支付。"]]
    await c.send(
        "你知道我刚问了什么吗",
        {
            "primary_intent": "history_query",
            "history_request": {"mode": "reference", "source_entry_ids": ["payment"]},
        },
        input_id="recall-question",
    )
    original_ids = (await c.state())["recall_entry_ids"]
    before = len(c.models["reply.stream"].calls)
    c.models["reply.stream"].script = [[original["text"]]]
    await c.send(
        "你怎么回答呢",
        {
            "primary_intent": "history_query",
            "history_request": {
                "mode": mode,
                "source_entry_ids": ["answer-followup"] if mode == "reference" else [],
            },
        },
        input_id="answer-followup",
    )
    state = await c.state()
    assert state["recall_entry_ids"] == original_ids
    assert "answer-followup" not in state["recall_entry_ids"]
    assert not state["turn_decision"]["clarification"]
    assert len(c.models["reply.stream"].calls) == before + 1
    messages = c.models["reply.stream"].calls[-1]["messages"]
    authority = json.loads(messages[1].content.split("\n", 1)[1])
    assert authority["decision"]["history_selection"]["source_entry_ids"] == original_ids
    assert any(original["text"] in m.content for m in messages)
    last = [e for e in (await c.snapshot())["timeline"] if e["kind"] == "assistant_message"][-1]
    assert last["text"] == original["text"]


@pytest.mark.parametrize("scenario", ["no_target", "ambiguous", "interrupted", "unknown", "mixed"])
async def test_unresolved_reference_clarifies_without_claiming_missing_records(
    conversation, scenario
):
    c = conversation
    c.models["reply.stream"].script = [["第一条回复"], ["第二条回复"], ["回顾内容"], ["好的"]]
    await c.send("你好", {"primary_intent": "social"}, input_id="first")
    await c.send("再聊一句", {"primary_intent": "social"}, input_id="second")
    if scenario != "no_target":
        await c.send(
            "回顾历史",
            {
                "primary_intent": "history_query",
                "history_request": {
                    "mode": "recent" if scenario == "ambiguous" else "reference",
                    "source_entry_ids": ["first"],
                },
            },
            input_id="recall",
        )
    if scenario == "interrupted":
        await c.send("谢谢", {"primary_intent": "social"}, input_id="interruption")
    ids = ["unknown"] if scenario == "unknown" else ["current"]
    if scenario == "mixed":
        ids.append("unknown")
    before = len(c.models["reply.stream"].calls)
    await c.send(
        "你怎么回答呢",
        {
            "primary_intent": "history_query",
            "history_request": {"mode": "reference", "source_entry_ids": ids},
        },
        input_id="current",
    )
    state = await c.state()
    assert state["recall_entry_ids"] == []
    assert (
        state["turn_decision"]["clarification"]
        == "您想回顾哪条问题的回答？请指出那条问题或时间范围。"
    )
    assert len(c.models["reply.stream"].calls) == before
