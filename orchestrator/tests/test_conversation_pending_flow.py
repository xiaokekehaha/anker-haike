"""A35: real HTTP → guide → explanation → original card feedback → refresh."""

import json

import httpx

from app.main import app
from tests.conversation_runtime import REPORT, REPORT_TEXT
from tests.conversation_runtime import conversation as conversation  # noqa: PLC0414


def events(response):
    return [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]


async def test_explanation_keeps_card_then_feedback_counts_once(conversation):
    session = conversation
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://t") as client:
        sid = session.sid
        await session.send(REPORT_TEXT, REPORT, input_id="question")
        before = (await client.get(f"/sessions/{sid}")).json()
        pending = before["pending_input"]
        assert pending["kind"] == "step_feedback", before
        # Deterministic fallback explains the actual stored step; no extra diagnosis call.
        await session.send(
            "为什么要这样做",
            {"primary_intent": "explain", "device_relation": "current"},
            input_id="why",
        )
        after = (await client.get(f"/sessions/{sid}")).json()
        assert after["version"] == 2
        assert after["stage"] == before["stage"]
        assert [e["stage"] for e in session.outputs[-1] if e["type"] == "progress"][-1] == before["stage"]
        assert after["pending_input"]["card_id"] == pending["card_id"]
        assert after["pending_input"]["input_token"] == pending["input_token"]
        action = {
            "kind": "step_feedback",
            "action_id": "feedback",
            "expected_version": 2,
            "target_issue_id": after["active_issue_id"],
            "card_id": pending["card_id"],
            "input_token": pending["input_token"],
            "payload": {"feedback": "not_solved"},
        }
        feedback = await client.post(f"/sessions/{sid}/actions", json=action)
        assert not any(e["type"] == "error" for e in events(feedback)), events(feedback)
        repeated = await client.post(f"/sessions/{sid}/actions", json=action)
        assert events(feedback) == events(repeated)
        final = (await client.get(f"/sessions/{sid}")).json()
        assert final["version"] == 3
        assert final["pending_input"]["card_id"] != pending["card_id"]
        state = await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})
        assert state.values["counters"]["executed"] == 1
        assert not state.next and not state.tasks
