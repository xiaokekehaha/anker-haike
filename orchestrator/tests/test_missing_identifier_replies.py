"""客户说手上没有单号 / 凭证时不逐字重复索取（2026-10-10 官方 63 单复测 B12 / B17）。

资料仍是必需的：说明现在查不了 / 不会提交、去哪找，等客户补上再继续。模型为假，后端为内存实现。
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.conversation.interpret import TurnInterpretation
from app.main import app
from app.sessions.l3 import LACKS_IDENTIFIER, PROOF_LATER, PROOF_REQUEST, TRACKING_LATER
from tests.test_conversation_l3 import events, interpret_as, said, send, state_of
from tests.test_conversation_l3 import l3_runtime as l3_runtime_fixture

l3_runtime = l3_runtime_fixture

B12_FIRST = ("I’ve tried to put my tracking number in to look for my order and it is not working. "
             "Do you know when I will be getting my order?")
B12_SECOND = "I don't have the order number or tracking number with me right now."
B17_FIRST = ("My 2 SoloCam S340 are always loosing connection and nit reliable junk but . My other ones solo cam c20 "
             "which I paid less for has been working pretty good. I wish you could just send me those for the 2 that is junk")
B17_SECOND = "I don't have my receipt right now. Do not submit any replacement request yet."


@pytest.mark.parametrize("text,expected", [
    (B12_SECOND, True),
    (B17_SECOND, True),
    ("I lost the receipt.", True),
    ("Ik heb het ordernummer niet bij de hand.", True),
    ("Here is my order number Anker003.", False),
    ("The tracking number is not working.", False),
])
def test_lacks_identifier(text, expected):
    assert bool(LACKS_IDENTIFIER.search(text.replace("’", "'"))) is expected


async def test_b12_no_tracking_number_is_not_asked_again_verbatim(l3_runtime, monkeypatch):
    interpret_as(monkeypatch, {
        B12_FIRST: TurnInterpretation(primary_intent="logistics_query", device_relation="current"),
        B12_SECOND: TurnInterpretation(primary_intent="supplement", device_relation="current"),
    })
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        assert "Please share your order number or tracking number" in said(events(await send(client, sid, B12_FIRST)))
        second = said(events(await send(client, sid, B12_SECOND)))
        assert second == TRACKING_LATER
        assert "Anker" not in second


async def test_b17_no_receipt_explains_nothing_is_submitted(l3_runtime, monkeypatch):
    interpret_as(monkeypatch, {
        B17_FIRST: TurnInterpretation(primary_intent="replacement_request", device_relation="current",
                                      product_hints=["SoloCam S340"]),
        B17_SECOND: TurnInterpretation(primary_intent="supplement", device_relation="current"),
    })
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        assert PROOF_REQUEST in said(events(await send(client, sid, B17_FIRST)))
        rows = events(await send(client, sid, B17_SECOND))
        assert said(rows) == PROOF_LATER
        assert not any(e["type"] == "proposal_card" or e["type"] == "execution_card" for e in rows)
        state = await state_of(sid)
        assert state["case_status"] not in {"awaiting_approval", "submitted"}
