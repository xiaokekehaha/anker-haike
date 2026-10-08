"""主办方真实工单首封消息走完整会话图（无模型、无知识库）：错误码精确命中官方 Q&A、硬件故障直进质保、未收录码转人工。"""

import pytest
from httpx import ASGITransport, AsyncClient

import app.conversation.interpret as semantic
from app.conversation.interpret import TurnInterpretation
from app.main import app
from app.official.models import OfficialData
from tests.test_conversation_l3 import act, events, send, state_of
from tests.test_conversation_l3 import l3_runtime as l3_runtime  # noqa: PLC0414

TICKETS = {t.id: t.body for t in OfficialData().tickets}


@pytest.fixture
def report_intent(monkeypatch):
    async def interpret(router, state, **kwargs):
        return TurnInterpretation(primary_intent="report_problem", device_relation="current"), {"source": "test"}

    monkeypatch.setattr(semantic, "interpret_turn", interpret)


async def _first_turn(ticket: str):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, TICKETS[ticket]))
        return rows, await state_of(sid)


@pytest.mark.parametrize(
    ("ticket", "sku", "plan_id"),
    [("T18", "T2352", "qa_rv_0147"), ("T11", "T2080", "qa_rv_0481"), ("T16", "T2351", "qa_rv_0056")],
)
async def test_indexed_error_code_gets_the_official_step(l3_runtime, report_intent, ticket, sku, plan_id):
    rows, state = await _first_turn(ticket)
    assert state["product_confirmed"]["sku"] == sku
    card = next(e for e in rows if e["type"] == "step_card")
    assert card["step"]["plan_id"] == plan_id


async def test_hardware_fault_code_goes_straight_to_warranty(l3_runtime, report_intent):
    # T14：4090 墙边传感器，官方 Q&A 判硬件故障 → 不给排障步骤，进入订单 / 凭证收集
    rows, state = await _first_turn("T14")
    assert not [e for e in rows if e["type"] == "step_card"]
    assert state["escalate_reason"] == "R6"


async def test_unindexed_code_is_handed_off_not_guessed(l3_runtime, report_intent):
    # T13：5116 官方未收录 → R5，不套用相近错误码
    rows, state = await _first_turn("T13")
    assert not [e for e in rows if e["type"] == "step_card"]
    assert state["escalate_reason"] == "R5"


async def test_restart_then_warranty_entry_ends_in_the_warranty_flow(l3_runtime, report_intent):
    # T28：2111 滚刷错误，官方 Q&A 先让重启，仍未解决才走质保（rv-0256 拆成两步）
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, TICKETS["T28"]))
        card = next(e for e in rows if e["type"] == "step_card")
        assert (card["step"]["plan_id"], card["step"]["step_id"]) == ("qa_rv_0256", "s1")
        rows = events(await act(client, sid, "step_feedback", {"feedback": "not_solved"}))
        second = next(e for e in rows if e["type"] == "step_card")
        assert second["step"]["step_id"] == "s2" and "engineering team" in second["step"]["instruction"]
        rows = events(await act(client, sid, "step_feedback", {"feedback": "not_solved"}))
        state = await state_of(sid)
    # 质保步仍未解决 → 计划用尽，按 SOP 进入订单质保判断（先收订单 / 凭证），不再出操作步骤
    assert state["escalate_reason"] == "R6" and state["stage"] == "context"
    assert not [e for e in rows if e["type"] == "step_card"]
    assert any(e["type"] == "awaiting_input" for e in rows)
