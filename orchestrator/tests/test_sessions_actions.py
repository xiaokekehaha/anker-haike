"""票 20：三段式等待节点与 /actions 基本通路。"""

import uuid

from haike_contracts.events import parse_event
from haike_contracts.snapshot import SessionSnapshot
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.sessions import sse
from tests.message_form import action_body, message_form

MULTI = "我的 S1 Pro 报错 error E23"  # S1 Pro 同名：扫地机 + 吸奶器 → 多命中；E23 是 T2080 的官方错误码（rv-0063）
SINGLE = "X10 报错 error 6025"  # 单命中 T2351，6025 精确命中 rv-0236


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _cfg(sid):
    return {"configurable": {"thread_id": sid}}


async def _send(client, sid, text):
    resp = await client.post(f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": text}))
    assert resp.status_code == 200, resp.text
    return sse.parse(resp.text)


def _action(pending, sku, **over):
    return {
        "action_id": uuid.uuid4().hex,
        "input_token": pending["input_token"],
        "card_id": pending["card_id"],
        "expected_version": pending["version"],
        "kind": "select_product",
        "payload": {"sku": sku},
        **over,
    }


async def test_multi_hit_emits_card_then_awaiting_and_done_awaiting(mem_runtime):
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events = await _send(client, sid, MULTI)
        snap = SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())

    types = [e["type"] for e in events]
    assert types == [
        "run_started",
        "input_received",
        "progress",
        "progress",
        "issue_changed",
        "pending_changed",
        "product_card",
        "awaiting_input",
        "done",
    ]
    for e in events:
        parse_event(e)
    card, awaiting, done = (next(e for e in events if e["type"] == kind) for kind in ("product_card", "awaiting_input", "done"))
    assert [e["stage"] for e in events if e["type"] == "progress"] == ["intake", "disambiguate"]
    assert {c["sku"] for c in card["candidates"]} == {"T2080", "T8D04"}
    assert [c["in_scope"] for c in card["candidates"]] == [True, True]  # 多品类后两者都在范围内
    # 成对且 version 一致（验收项 2）
    assert done["reason"] == "awaiting_input"
    assert awaiting["version"] == done["version"] == card["version"]
    assert awaiting["kind"] == "select_product"
    assert awaiting["card_id"] == card["card_id"] and awaiting["input_token"]
    # pending_card 在图状态里，且出现在快照 pending_input（验收项 4）
    state = await app.state.session_graph.aget_state(_cfg(sid))
    assert state.values["pending_card"]["card_id"] == card["card_id"]
    assert state.values["prepare_card_calls"] == 1
    assert state.next == ()
    assert snap.pending_input.model_dump() == {
        "kind": "select_product",
        "input_token": awaiting["input_token"],
        "issue_id": snap.active_issue_id,
        "card_id": card["card_id"],
        "version": done["version"],
    }
    assert (
        snap.active_run is None and snap.stage == "disambiguate" and snap.version == done["version"]
    )
    pc = next(i for i in snap.timeline if i.kind == "product_card")
    assert pc.card_id == card["card_id"] and pc.selected_sku is None


async def test_card_id_is_stable_for_same_business_position(mem_runtime):
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        first = next(e for e in await _send(client, sid, MULTI) if e["type"] == "product_card")
    from app.sessions.cards import candidates_key, derive_card_id

    expected = derive_card_id(
        sid, "disambiguate", candidates_key(["T2080", "T8D04"])
    )
    from app.conversation.reduce import stable_id
    state = (await app.state.session_graph.aget_state(_cfg(sid))).values
    assert first["card_id"] == stable_id(state["input_id"], state["active_issue_id"], expected)
    assert len(first["card_id"]) == 32


async def test_select_product_resumes_run_and_completes(mem_runtime):
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events = await _send(client, sid, MULTI)
        pending = next(e for e in events if e["type"] == "awaiting_input")
        resp = await client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", _action(pending, "T2080")))
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("text/event-stream")
        resumed = sse.parse(resp.text)
        snap = SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())

    types = [e["type"] for e in resumed]
    # 恢复 run：resumed=true（验收项 3）；await_input 重跑重发同一 card_id（验收项 1）；不再有 awaiting_input
    assert resumed[0]["type"] == "run_started" and resumed[0]["resumed"] is False
    # 票 28：确认产品后先检索，多出 tool_call 事件与 retrieve 子阶段；这里只看主干顺序
    assert "product_card" not in types
    assert types[-3:] == ["step_card", "awaiting_input", "done"]
    assert any(e["type"] == "pending_changed" and e["pending_id"] == pending["card_id"] and e["status"] == "consumed" for e in resumed)
    assert resumed[-1]["reason"] == "awaiting_input" and resumed[-1]["version"] > pending["version"]
    # seq 接续上一 run
    assert resumed[0]["seq"] == events[-1]["seq"] + 1

    state = await app.state.session_graph.aget_state(_cfg(sid))
    assert state.values["prepare_card_calls"] == 1  # prepare_card 只执行一次（验收项 1）
    # 产品卡已消费；pending_card 现在是 guide 写入的步骤卡（票 34）
    assert state.values["pending_card"]["kind"] == "step_feedback"
    assert state.values["last_action"] is None
    assert state.values["product_confirmed"]["sku"] == "T2080"
    assert state.values["product_state"] == "confirmed_sku"
    assert state.values["card_results"][pending["card_id"]] == {"selected_sku": "T2080"}
    assert state.next == ()  # 票 34：停在步骤卡等待反馈

    assert snap.pending_input.kind == "step_feedback" and snap.stage == "guide"
    cards = [i for i in snap.timeline if i.kind == "product_card"]
    assert len(cards) == 1 and cards[0].selected_sku == "T2080"  # 重发的卡片按 card_id 折叠
    assert snap.version == resumed[-1]["version"]


async def test_select_other_category_candidate_confirms_it(mem_runtime):
    """同名异类卡片里选吸奶器：2026-09-17 多品类后它在范围内，确认 SKU 与品类后继续，不走 R8。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        pending = next(e for e in await _send(client, sid, MULTI) if e["type"] == "awaiting_input")
        resumed = sse.parse(
            (
                await client.post(
                    f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", _action(pending, "T8D04"))
                )
            ).text
        )
    stages = [e["stage"] for e in resumed if e["type"] == "progress"]
    assert "out_of_scope" not in stages
    state = await app.state.session_graph.aget_state(_cfg(sid))
    assert state.values["out_of_scope"] is False and state.values["product_state"] == "confirmed_sku"
    assert state.values["product_confirmed"]["sku"] == "T8D04" and state.values["category"] == "breast_pump"
    assert state.values.get("escalate_reason") != "R8"


async def test_single_hit_and_zero_hit_skip_card(mem_runtime):
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        single = await _send(client, sid, SINGLE)
        sid2 = (await client.post("/sessions")).json()["session_id"]
        zero = await _send(client, sid2, "机器不吸了")
    assert "product_card" not in [e["type"] for e in single]
    assert single[-1]["reason"] == "awaiting_input"  # 单命中直达 guide 步骤卡
    st = await app.state.session_graph.aget_state(_cfg(sid))
    assert (
        st.values["product_confirmed"]["sku"] == "T2351"
        and st.values["product_state"] == "confirmed_sku"
    )
    assert "product_card" not in [e["type"] for e in zero] and zero[-1]["reason"] == "completed"
    st2 = await app.state.session_graph.aget_state(_cfg(sid2))
    assert st2.values["product_state"] == "unknown"


async def test_action_conflicts_and_validation(mem_runtime):
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        # 无 pending → not_allowed_now
        fake = {"kind": "select_product", "input_token": "x", "card_id": "x", "version": 0}
        r = await client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", _action(fake, "T2080")))
        assert r.status_code == 422  # 无问题时卡片动作缺少必填目标

        pending = next(e for e in await _send(client, sid, MULTI) if e["type"] == "awaiting_input")
        # 版本不对
        r = await client.post(
            f"/sessions/{sid}/actions",
            json=await action_body(client, f"/sessions/{sid}/actions", _action(pending, "T2080", expected_version=pending["version"] + 5)),
        )
        assert r.status_code == 409 and r.json()["code"] == "stale_version"
        assert r.json()["snapshot"]["version"] == pending["version"]
        # 卡片不对
        r = await client.post(
            f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", _action(pending, "T2080", card_id="stale"))
        )
        assert r.status_code == 409 and r.json()["code"] == "stale_card"
        # kind 与 pending 不符
        bad_kind = {
            **_action(pending, "x"),
            "kind": "step_feedback",
            "payload": {"feedback": "solved"},
        }
        r = await client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", bad_kind))
        assert r.status_code == 409 and r.json()["code"] == "not_allowed_now"
        # rediagnose（票 37）只在 guide / verify 阶段允许：等待产品卡时 → not_allowed_now（版本正确时）
        r = await client.post(
            f"/sessions/{sid}/actions",
            json=await action_body(client, f"/sessions/{sid}/actions", {"action_id": "a", "expected_version": pending["version"], "kind": "rediagnose",
                  "payload": {"text": "还有异响"}}),
        )
        assert r.status_code == 422  # 外部 rediagnose 已移除
        # 契约校验失败 → 422
        r = await client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", {"kind": "select_product"}))
        assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_action"
        r = await client.post(
            f"/sessions/{sid}/actions",
            json=await action_body(client, f"/sessions/{sid}/actions", _action(pending, "T2080", payload={"sku": "x", "extra": 1})),
        )
        assert r.status_code == 422
        assert (
            await client.post("/sessions/nope/actions", json=await action_body(client, "/sessions/nope/actions", _action(pending, "x", target_issue_id="missing-issue")))
        ).status_code == 404
        # 冲突不改变状态：正确动作仍可通过
        ok = await client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", _action(pending, "T2080")))
        assert ok.status_code == 200 and sse.parse(ok.text)[-1]["reason"] == "awaiting_input"
        # 已消费的 pending 再发（新 action_id）：version 已前进 → stale_version（08 §4 先校 version）
        again = await client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", _action(pending, "T2080")))
        assert again.status_code == 409 and again.json()["code"] == "stale_version"


async def test_message_while_awaiting_is_new_run_not_resume(mem_runtime):
    """等待卡片时用户直接发文本：不是动作，开新 run（rediagnose 语义在票 37 细化），不得撞到 interrupt。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        first = await _send(client, sid, MULTI)
        assert first[-1]["reason"] == "awaiting_input"
        second = await _send(client, sid, "算了，是 X10")
    assert second[0]["resumed"] is False
    assert second[-1]["type"] == "done"
