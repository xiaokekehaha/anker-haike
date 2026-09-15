"""Long-dialogue recall and correction through the real HTTP/model boundary."""
from tests.conversation_runtime import REPORT, REPORT_TEXT
from tests.conversation_runtime import conversation as conversation  # noqa: PLC0414


async def test_recall_and_correct_after_thirty_turns(conversation):
    c = conversation
    await c.send(REPORT_TEXT, REPORT, input_id="first-question")
    pending = (await c.snapshot())["pending_input"]
    for i in range(30):
        c.models["reply.stream"].script.append([f"好的，我们继续交流，第{i + 1}轮。"])
        await c.send(f"先聊一句，第{i + 1}轮", {"primary_intent": "social", "device_relation": "current"})
    assert (await c.snapshot())["pending_input"]["card_id"] == pending["card_id"]
    c.models["reply.stream"].script.append([f"您最初说的是：{REPORT_TEXT}。我当时请您查看排查步骤。"])
    await c.send("最开始我说了什么，你怎么回答的？", {"primary_intent": "history_query",
        "history_request": {"mode": "first"}}, input_id="recall-first")
    reply = "".join(e.get("delta", "") for e in c.outputs[-1])
    assert REPORT_TEXT in reply
    assert not c.models["reply.stream"].calls  # Diagnostic history uses the stored record.
    state = await c.state()
    issue = state["issues"][state["active_issue_id"]]
    old = next(f for f in issue["facts"] if f["value"] == "滚刷缠头发")
    before_count = state["counters"]
    correction = "刚才滚刷缠头发说错了，是滤网堵住了"
    await c.send(correction, {"primary_intent": "correct", "device_relation": "current",
        "corrections": [{"fact_id": old["fact_id"], "value": "滤网堵住", "quote": correction}]})
    final = await c.state()
    assert set(final["symptoms"]) == {"不吸了", "滤网堵住"}
    assert final["counters"] == before_count
    snapshot = await c.snapshot()
    assert snapshot["timeline"][0]["text"] == REPORT_TEXT
    assert snapshot["timeline"][0]["id"] == "first-question"
    assert snapshot["version"] == 33
