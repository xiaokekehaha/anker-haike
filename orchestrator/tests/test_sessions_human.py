"""票 25：范围外产品 R8（out_of_scope 子流程）与 request_human 全局动作（08 §4 步骤 4）。"""

from __future__ import annotations

import asyncio
import uuid

from haike_contracts.snapshot import SessionSnapshot
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.sessions import sse
from app.sessions.graph import out_of_scope_text
from tests.message_form import action_body, message_form

MULTI = "我的 S1 Pro 不吸了"


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _send(client, sid: str, text: str) -> list[dict]:
    resp = await client.post(f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": text}))
    assert resp.status_code == 200, resp.text
    return sse.parse(resp.text)


def _human(**over) -> dict:
    return {"action_id": uuid.uuid4().hex, "expected_version": 0, "kind": "request_human", **over}


def _stages(events):
    return [e["stage"] for e in events if e["type"] == "progress"]


def _summary(events) -> dict:
    return next(e for e in events if e["type"] == "escalation_summary")["summary"]


async def _state(sid: str):
    return await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})


async def _snap(client, sid: str) -> SessionSnapshot:
    return SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())


async def test_a2_select_breast_pump_continues_in_scope(mem_runtime):
    """A2 选吸奶器：2026-09-17 多品类后吸奶器在范围内 → 确认 SKU 后进入排障，不再 R8。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        pending = next(e for e in await _send(client, sid, MULTI) if e["type"] == "awaiting_input")
        resp = await client.post(
            f"/sessions/{sid}/actions",
            json=await action_body(client, f"/sessions/{sid}/actions", {
                "action_id": uuid.uuid4().hex,
                "input_token": pending["input_token"],
                "card_id": pending["card_id"],
                "expected_version": pending["version"],
                "kind": "select_product",
                "payload": {"sku": "EUFY-BP-S1-PRO"},
            }),
        )
        assert resp.status_code == 200
        events = sse.parse(resp.text)
    assert "out_of_scope" not in _stages(events) and not any(e["type"] == "escalation_summary" for e in events)
    st = (await _state(sid)).values
    assert st["product_state"] == "confirmed_sku" and st["product_confirmed"]["sku"] == "EUFY-BP-S1-PRO"
    assert st["category"] == "breast_pump" and st["out_of_scope"] is False


async def test_out_of_scope_category_text_names_supported_lines(mem_runtime):
    """范围外说明从目录生成：家用储能（电工安装）→ R8，文案列出支持的产品线而不写死某个品类。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events = await _send(client, sid, "我家的阳台光储充不进电")
    assert _stages(events)[-2:] == ["out_of_scope", "escalate"]
    texts = [
        "".join(e["delta"] for e in events if e["type"] == "message" and e["message_id"] == mid)
        for mid in dict.fromkeys(e["message_id"] for e in events if e["type"] == "message_start")
    ]
    assert texts[0] == out_of_scope_text("家用储能（型号未确认）", "家用储能")
    assert "Anker Charging" in texts[0] and "Anker eufy" in texts[0] and "扫地机器人" not in texts[0]
    summary = _summary(events)
    assert summary["reason"]["rule_id"] == "R8" and summary["product"] == "家用储能（型号未确认）"
    assert summary["receipt"]["status"] == "not_collected"
    assert events[-1]["reason"] == "completed"
    st = (await _state(sid)).values
    assert st["stage"] == "escalate" and st["out_of_scope"] is True and st["escalate_reason"] == "R8"


async def test_catalog_only_category_ends_honestly_with_r5(mem_runtime):
    """目录级品类（拓展坞）：识别得到、没有该品类的排查资料 → 不借用别的品类的判别题，直接 R5 说明原因。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events = await _send(client, sid, "我的拓展坞识别不了硬盘")
    assert "out_of_scope" not in _stages(events) and "clarify" not in _stages(events)
    said = "".join(e["delta"] for e in events if e["type"] == "message")
    assert "启动" not in said and "充电" not in said, said
    summary = _summary(events)
    assert summary["reason"]["rule_id"] == "R5" and "暂无可用的排查资料" in summary["reason"]["text"]
    st = (await _state(sid)).values
    assert st["category"] == "hub" and st["product_state"] == "category_only"


async def test_in_scope_category_without_sku_enters_diagnosis(mem_runtime):
    """只提到品类（充电器）、无具体型号：2026-09-17 多品类后进入该品类的排障问诊，不 R8、不出产品卡。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events = await _send(client, sid, "充电器不亮灯")
    assert "out_of_scope" not in _stages(events) and "product_card" not in [e["type"] for e in events]
    assert not any(e["type"] == "escalation_summary" for e in events)
    st = (await _state(sid)).values
    assert st["product_state"] == "category_only" and st["category"] == "charger"
    # 充电器词表里的判别题，不是扫地机的「按电源后能启动吗」
    said = "".join(e["delta"] for e in events if e["type"] == "message")
    assert "充电" in said and "启动" not in said, said


async def test_request_human_while_awaiting_input_is_not_409(mem_runtime):
    """awaiting_input 中点「请求人工」：忽略 version / pending 校验，不返回 409；卡片作废、R3 升级（验收项 3）。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        first = await _send(client, sid, MULTI)
        assert first[-1]["reason"] == "awaiting_input"
        body = _human(expected_version=0)  # 故意给错版本、不带 card_id
        resp = await client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", body))
        assert resp.status_code == 200 and resp.headers["x-input-replayed"] == "false"
        events = sse.parse(resp.text)
        snap = await _snap(client, sid)
        # 同 action_id 重放
        again = await client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", body))
        assert again.status_code == 200 and again.headers["x-input-replayed"] == "true"
    assert events[0]["resumed"] is False  # 经 interrupt 恢复
    assert _stages(events) == ["escalate"] and "awaiting_input" not in [e["type"] for e in events]
    summary = _summary(events)
    assert summary["reason"]["rule_id"] == "R3"
    assert summary["product"].startswith("未确认")  # 卡片未选，产品仍未确认
    st = (await _state(sid)).values
    assert st["escalate_reason"] == "R3" and st["pending_card"] is None
    assert st["turn_decision"]["escalation_trigger"] == "R3"
    assert st["turn_decision"]["source_refs"] == [body["action_id"]]
    assert snap.pending_input is None and snap.stage == "escalate"
    card = next(i for i in snap.timeline if i.kind == "product_card")
    assert card.selected_sku is None  # 用户没有选


async def test_request_human_during_streaming_cancels_then_escalates(mem_runtime, monkeypatch):
    """streaming 中点「请求人工」→ 当前 run 停止（done cancelled）→ 升级摘要（验收项 2）。"""
    monkeypatch.setenv("PLACEHOLDER_NODE_DELAY_S", "1.5")
    manager = app.state.run_manager
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        running = await manager.start(sid, "扫地机 X10 不吸了")
        for _ in range(200):  # 等 intake 进入 sleep（progress 已落库）
            await asyncio.sleep(0.01)
            if len(await mem_runtime.list_events(sid, run_id=running.run_id)) >= 2:
                break
        monkeypatch.setenv("PLACEHOLDER_NODE_DELAY_S", "0")
        t0 = asyncio.get_event_loop().time()
        resp = await client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", _human()))
        elapsed = asyncio.get_event_loop().time() - t0
        assert resp.status_code == 200, resp.text
        events = sse.parse(resp.text)
        prev = await mem_runtime.list_events(sid, run_id=running.run_id)
        snap = await _snap(client, sid)
    assert elapsed < 1.2, "取消应立刻中止正在 sleep 的节点"
    assert prev[-1]["type"] == "done" and prev[-1]["reason"] == "cancelled"
    assert events[0]["resumed"] is False and events[0]["run_id"] != running.run_id
    assert _stages(events) == ["escalate"] and _summary(events)["reason"]["rule_id"] == "R3"
    assert snap.cancelled_run is not None and snap.cancelled_run.run_id == running.run_id
    assert snap.stage == "escalate" and snap.active_run is None


async def test_request_human_when_idle_starts_from_entry(mem_runtime, monkeypatch):
    """idle 状态（无 interrupt、无 active run）点「请求人工」：从 START 直达 human_request → escalate。"""
    import app.conversation.interpret as semantic

    original = semantic.interpret_turn

    async def with_reported_fact(router, state, **kwargs):
        meaning, context = await original(router, state, **kwargs)
        if state.get("entry") == "message":
            meaning = meaning.model_copy(update={
                "facts": [semantic.FactCandidate(value=state["text"], quote=state["text"])],
            })
        return meaning, context

    monkeypatch.setattr(semantic, "interpret_turn", with_reported_fact)
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        first = await _send(client, sid, "扫地机 X10 不吸了")  # 票 34：一轮后停在步骤卡
        pending = next(e for e in first if e["type"] == "awaiting_input")
        assert pending["kind"] == "step_feedback"
        # 点「解决了」→ verify 结束本 run，回到 idle（票 35）
        solved = await client.post(
            f"/sessions/{sid}/actions",
            json=await action_body(client, f"/sessions/{sid}/actions", {
                "action_id": uuid.uuid4().hex,
                "input_token": pending["input_token"],
                "card_id": pending["card_id"],
                "expected_version": pending["version"],
                "kind": "step_feedback",
                "payload": {"feedback": "solved"},
            }),
        )
        assert solved.status_code == 200 and sse.parse(solved.text)[-1]["reason"] == "completed"
        before = await _snap(client, sid)
        assert before.pending_input is None and before.active_run is None
        resp = await client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", _human(expected_version=999)))
        assert resp.status_code == 200
        events = sse.parse(resp.text)
        after = await _snap(client, sid)
    assert events[0]["resumed"] is False
    assert any(e["type"] == "input_received" and e["input_kind"] == "action" for e in events)
    assert [e["type"] for e in events if e["type"] not in {"ping", "input_received", "issue_changed", "pending_changed", "summary_updated"}] == [
        "run_started",
        "progress",
        "message_start",
        "message",
        "message_end",
        "escalation_summary",
        "done",
    ]
    summary = _summary(events)
    assert summary["reason"]["rule_id"] == "R3" and summary["product"] == "eufy X10 Pro Omni"
    assert summary["problem"] == "扫地机 X10 不吸了"
    st = (await _state(sid)).values
    assert st["product_confirmed"]["sku"] == "EUFY-X10-PRO-OMNI"  # 已确认信息带进摘要、未被清空
    assert after.version == events[-1]["version"] and after.stage == "escalate"


async def test_request_human_on_fresh_session(mem_runtime):
    """会话刚创建、一句话没说就请求人工：同样可用。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        resp = await client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", _human()))
        assert resp.status_code == 200
        events = sse.parse(resp.text)
    summary = _summary(events)
    assert summary["reason"]["rule_id"] == "R3" and summary["problem"] == "（尚未记录具体故障现象）"
