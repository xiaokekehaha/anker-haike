from datetime import datetime, timedelta
from pathlib import Path

import httpx
import yaml

from app.conversation.interpret import TurnInterpretation
from app.main import app
from app.models.runtime import set_model_router
from tests.test_conversation_flow import events


async def test_original_seven_turns_are_semantically_separated(mem_runtime, monkeypatch):
    case = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "data/eval/conversation/cases.yaml").read_text()
    )["cases"][0]
    scripted = {
        i["input_id"]: TurnInterpretation.model_validate(m)
        for i, m in zip(case["inputs"], case["interpretations"], strict=True)
    }

    async def interpret(router, state, **kw):
        return scripted[state["input_id"]], {"source": "recorded-scenario-gold"}

    monkeypatch.setattr("app.conversation.interpret.interpret_turn", interpret)
    set_model_router(None)
    observed = {}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://t") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        snapshot = {"version": 0, "active_issue_id": None}
        for item in case["inputs"]:
            if item.get("action"):
                response = await client.post(
                    f"/sessions/{sid}/actions",
                    json={
                        "kind": item["action"],
                        "action_id": item["input_id"],
                        "target_issue_id": snapshot["active_issue_id"],
                        "expected_version": snapshot["version"],
                        "payload": {},
                    },
                )
            else:
                response = await client.post(
                    f"/sessions/{sid}/messages",
                    data={
                        "input_id": item["input_id"],
                        "expected_version": snapshot["version"],
                        "text": item["text"],
                    },
                )
            assert response.status_code == 200, response.text
            observed[item["input_id"]] = events(response)
            assert not any(e["type"] == "error" for e in events(response)), response.text
            snapshot = (await client.get(f"/sessions/{sid}")).json()
        state = (
            await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})
        ).values
    assert len(state["issues"]) == 3
    assert state["issues"][state["active_issue_id"]]["status"] == "draft"
    symptoms = [issue["symptoms"] for issue in state["issues"].values()]
    assert ["没有声音"] in symptoms and ["冒烟"] in symptoms
    assert state["risk_cases"] and not state["turn_decision"]["allowed_operations"]
    assert state["turn_decision"]["clarification"]
    for iid in case["expected_events"]["no_repeat_summary_for_control_turns"]:
        assert not any(e["type"] == "escalation_summary" for e in observed[iid]), iid
    for output in observed.values():
        text = "".join(e.get("delta", "") for e in output)
        assert "已转接" not in text and "稍后会有专人" not in text
        for event in output:
            if event["type"] == "escalation_summary":
                assert "新问题" not in str(event["summary"]["observations"])
                assert "刚说错了" not in str(event["summary"]["observations"])
    assert snapshot["version"] == 7
    assert sum(e["type"] == "input_received" for output in observed.values() for e in output) == 7
    # Fixture's relative timeline remains ordered, independent of local wall clock.
    origin = datetime.fromisoformat(case["clock"].replace("Z", "+00:00"))
    times = [origin + timedelta(seconds=i["after_seconds"]) for i in case["inputs"]]
    assert times == sorted(times)
