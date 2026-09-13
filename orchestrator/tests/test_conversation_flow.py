import json

import httpx

from app.conversation.interpret import TurnInterpretation
from app.main import app


def events(response):
    return [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]


async def test_input_history_and_logical_pending_flow(mem_runtime, monkeypatch):
    meanings = iter(
        [
            TurnInterpretation(
                primary_intent="report_problem",
                device_relation="other",
                product_hints=["耳机"],
                facts=[{"value": "没有声音", "quote": "没有声音"}],
            ),
            TurnInterpretation(primary_intent="history_query", device_relation="current"),
            TurnInterpretation(primary_intent="correct", device_relation="current"),
        ]
    )

    async def interpret(*args, **kwargs):
        return next(meanings), {"source": "test"}

    monkeypatch.setattr("app.conversation.interpret.interpret_turn", interpret)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://t") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        first = await client.post(
            f"/sessions/{sid}/messages",
            data={"input_id": "i1", "expected_version": 0, "text": "耳机没有声音"},
        )
        assert first.status_code == 200
        out = events(first)
        assert not any(e["type"] == "error" for e in out), out
        snap = (await client.get(f"/sessions/{sid}")).json()
        assert snap["timeline"][0]["kind"] == "user_message"
        assert snap["timeline"][0]["id"] == "i1"
        assert snap["active_issue_id"]
        retry = await client.post(
            f"/sessions/{sid}/messages",
            data={"input_id": "i1", "expected_version": 0, "text": "耳机没有声音"},
        )
        assert events(retry) == out
        for iid, text in [("i2", "我之前问了什么问题"), ("i3", "刚说错了")]:
            response = await client.post(
                f"/sessions/{sid}/messages",
                data={"input_id": iid, "expected_version": snap["version"], "text": text},
            )
            assert not any(e["type"] == "error" for e in events(response)), events(response)
            snap = (await client.get(f"/sessions/{sid}")).json()
        assistant = [e for e in snap["timeline"] if e["kind"] == "assistant_message"]
        assert "哪句话说错" in assistant[-1]["text"]
        assert assistant[-1]["reply_to_input_id"] == "i3"
        assert assistant[-1]["first_seq"] < assistant[-1]["last_seq"]
        state = await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})
        assert not state.next and not state.tasks
        assert state.values["symptoms"] == ["没有声音"]
