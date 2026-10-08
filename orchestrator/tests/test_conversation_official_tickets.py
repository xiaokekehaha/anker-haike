"""主办方真实工单首封消息走完整会话图（无模型、无知识库）：错误码精确命中官方 Q&A、硬件故障直进质保、未收录码转人工。"""

import pytest
from httpx import ASGITransport, AsyncClient

import app.conversation.interpret as semantic
from app.conversation.interpret import TurnInterpretation
from app.knowledge.runtime import set_knowledge_adapter
from app.main import app
from app.official.models import OfficialData
from tests.fake_qa import QAHitAdapter
from tests.test_conversation_l3 import act, events, said, send, state_of
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


async def _feedback_until_no_card(client, sid, limit=8):
    rows = []
    for _ in range(limit):
        rows = events(await act(client, sid, "step_feedback", {"feedback": "not_solved"}))
        if not any(e["type"] == "step_card" for e in rows):
            break
    return rows


async def test_t55_main_case_troubleshoots_then_checks_order_warranty(l3_runtime, report_intent):
    # T55：RMA 表单「S1 Pro Wearable Breast Pump」同名型号由品类词消歧 → 官方 Q&A 排障 → 未解决 → 订单 Anker016 保内 → 收 SOP 证据
    set_knowledge_adapter(QAHitAdapter("bp-0102"))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            rows = events(await send(client, sid, TICKETS["T55"]))
            assert not any(e["type"] == "product_card" for e in rows)
            assert next(e for e in rows if e["type"] == "step_card")["step"]["plan_id"] == "qa_bp_0102"
            rows = await _feedback_until_no_card(client, sid)
            state = await state_of(sid)
    finally:
        set_knowledge_adapter(None)
    assert state["product_confirmed"]["sku"] == "T8D04"
    assert state["case_order_no"] == "Anker016" and state["warranty"]["status"] == "in_warranty"
    assert set(state["awaiting_evidence"]) == {"photo_or_video", "serial_number"}


async def test_t29_out_of_warranty_order_is_declined_after_troubleshooting(l3_runtime, report_intent):
    set_knowledge_adapter(QAHitAdapter("rv-0236"))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            events(await send(client, sid, TICKETS["T29"]))
            rows = await _feedback_until_no_card(client, sid)
            state = await state_of(sid)
    finally:
        set_knowledge_adapter(None)
    assert state["warranty"]["status"] == "out_of_warranty" and state["stage"] == "done"
    assert "warranty has expired" in said(rows)


@pytest.fixture
def logistics_intent(monkeypatch):
    async def interpret(router, state, **kwargs):
        return TurnInterpretation(primary_intent="logistics_query", device_relation="current"), {"source": "test"}

    monkeypatch.setattr(semantic, "interpret_turn", interpret)


async def test_t2_one_order_with_two_tracking_numbers_is_not_ambiguous(l3_runtime, logistics_intent):
    # T2：一个订单号 + 两个运单号（配件包与主机分开发）是同一订单的两个包裹，不应追问「哪个订单」
    rows, state = await _first_turn("T2")
    assert state["case_order_no"] == "Anker002"
    card = next(e for e in rows if e["type"] == "proposal_card")
    assert [o["type"] for o in card["options"]] == ["carrier_investigation"]


async def test_t45_safety_handoff_keeps_dealer_and_serial_facts(l3_runtime, report_intent):
    rows, state = await _first_turn("T45")
    assert state["escalate_reason"] == "R4"
    observations = next(e for e in rows if e["type"] == "escalation_summary")["summary"]["observations"]
    assert "客户填写的 SN：ANKER1234567E" in observations
    assert any("Aeroflow" in o and "authorized dealer" in o for o in observations)


@pytest.mark.parametrize("ticket", ["T42", "T44"])
async def test_physical_damage_skips_troubleshooting(l3_runtime, report_intent, ticket):
    # 部件断裂 / 脱落：排障步骤修不好，直接进质保判断（2026-10-08 Fable 5.1 裁定，63 单回放 T42 先跑了 4 张排障卡）
    rows, state = await _first_turn(ticket)
    assert not [e for e in rows if e["type"] == "step_card"]
    assert state["escalate_reason"] == "R6" or state.get("stage") == "context"


def test_crack_sound_is_not_physical_damage():
    from app.official.damage import physical_damage

    assert physical_damage("When it starts there is a crack sound from the brush") is None
    assert physical_damage("The roller brush came off") is None
    assert physical_damage("The lid of the tank snapped") == "The lid of the tank snapped"
