"""票 39：凭证收集 collect_receipt——常规升级进入 awaiting_input(upload_receipt)、skip_receipt、上传凭证、
非凭证位置上传不进凭证流、R6 标记、安全 / 人工升级不收凭证。

常规升级（R1 / R2…）由 verify（票 35 / 36）触发；这里用 LangGraph aupdate_state 注入 escalate_reason 模拟。
"""

from __future__ import annotations

from tests.message_form import action_body, message_form, escalate_on_feedback

import io
import uuid

from haike_contracts.snapshot import SessionSnapshot
from httpx import ASGITransport, AsyncClient

from app.images import InMemoryImageStore
from app.images.runtime import set_image_store
from app.main import app
from app.rules import RulesService, set_rules_service
from app.sessions import sse
from app.sessions.receipt import DIRECT_SUMMARY_REASONS, receipt_card_id
from app.settings import REPO_ROOT
from tests.test_images import png_bytes

RULES = REPO_ROOT / "config" / "rules" / "safety_terms.yaml"


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _cfg(sid: str):
    return {"configurable": {"thread_id": sid}}


async def _send(client, sid: str, text: str, receipt_images: int = 0, purpose: str = "receipt"):
    files = [
        ("images", (f"r{i}.png", io.BytesIO(png_bytes(300 + i)), "image/png"))
        for i in range(receipt_images)
    ]
    resp = await client.post(
        f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": text, "purpose": purpose}), files=files or None
    )
    assert resp.status_code == 200, resp.text
    return sse.parse(resp.text)


async def _regular_escalation(client, sid: str, reason: str = "R1", text: str = "还是不行"):
    """先跑一轮正常对话（产品已确认），再注入常规升级原因并发下一条消息 → 进入 escalate 子流程。"""
    await _send(client, sid, "扫地机 X10 不吸了")
    return await escalate_on_feedback(client, sid, reason)


def _progress(events):
    return [(e["stage"], e.get("substage")) for e in events if e["type"] == "progress"]


def _summary(events):
    return next(e for e in events if e["type"] == "escalation_summary")["summary"]


async def _snap(client, sid: str) -> SessionSnapshot:
    return SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())


def _skip(pending: dict, reason: str = "later") -> dict:
    return {
        "action_id": uuid.uuid4().hex,
        "input_token": pending["input_token"],
        "card_id": pending["card_id"],
        "expected_version": pending["version"],
        "kind": "skip_receipt",
        "payload": {"reason": reason},
    }


async def test_regular_escalation_enters_collect_receipt_and_awaits_upload(mem_runtime):
    """R1 升级 → progress(escalate, collect_receipt) → awaiting_input(kind=upload_receipt) → done(awaiting_input)（验收项 1）。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events = await _regular_escalation(client, sid, "R1")
        snap = await _snap(client, sid)
    assert ("escalate", "collect_receipt") in _progress(events)
    assert ("escalate", "summarize") not in _progress(events)  # 还没摘要
    pending = next(e for e in events if e["type"] == "awaiting_input")
    assert pending["kind"] == "upload_receipt" and pending["card_id"] == pending["input_token"]
    assert pending["card_id"] == receipt_card_id(sid, "R1")
    assert events[-1]["reason"] == "awaiting_input" and events[-1]["version"] == pending["version"]
    assert "escalation_summary" not in [e["type"] for e in events]
    # 快照：pending_input 指向凭证上传；没有卡片事件（Composer 据 kind 切换为凭证上传态）
    assert snap.pending_input is not None and snap.pending_input.kind == "upload_receipt"
    assert snap.stage == "escalate" and snap.substage == "collect_receipt"
    # 凭证收集位置无卡片事件（首轮的步骤卡是票 34 的历史卡片，不算）
    assert not [i for i in snap.timeline if i.kind in ("product_card", "receipt_card")]
    st = (await app.state.session_graph.aget_state(_cfg(sid))).values
    assert st["pending_card"]["kind"] == "upload_receipt" and st["receipt"]["status"] is None


async def test_skip_receipt_goes_to_summary_not_collected(mem_runtime):
    """跳过 → escalation_summary(receipt.status=not_collected)，skipped_reason 记入卡片结果（验收项 2）。"""
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events = await _regular_escalation(client, sid, "R1")
        pending = next(e for e in events if e["type"] == "awaiting_input")
        resp = await client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", _skip(pending, "later")))
        assert resp.status_code == 200, resp.text
        resumed = sse.parse(resp.text)
        snap = await _snap(client, sid)
    assert resumed[0]["resumed"] is False
    assert _progress(resumed) == [("escalate", "summarize")]  # 不再要求凭证
    summary = _summary(resumed)
    assert summary["reason"]["rule_id"] == "R1"
    assert summary["receipt"]["status"] == "not_collected"
    assert summary["receipt"]["next_step"] == "请准备购买凭证，人工协助核实"
    assert summary["receipt"]["verified_facts"] == {} and summary["receipt"]["conflicts"] == []
    assert summary["product"] == "eufy X10 Pro Omni"  # 已确认产品带进摘要
    assert resumed[-1]["reason"] == "completed"
    st = (await app.state.session_graph.aget_state(_cfg(sid))).values
    assert st["receipt"]["status"] == "not_collected" and st["receipt"]["skipped_reason"] == "later"
    assert st["card_results"][pending["card_id"]] == {"skipped_reason": "later"}
    assert st["pending_card"] is None and snap.pending_input is None and snap.stage == "escalate"


async def test_skip_receipt_wrong_reason_or_kind_rejected(mem_runtime):
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events = await _regular_escalation(client, sid, "R2")
        pending = next(e for e in events if e["type"] == "awaiting_input")
        bad_reason = await client.post(
            f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", {**_skip(pending), "payload": {"reason": "whatever"}})
        )
        assert bad_reason.status_code == 422
        # 等待凭证时点产品选择：kind 不在允许时机
        wrong_kind = await client.post(
            f"/sessions/{sid}/actions",
            json=await action_body(client, f"/sessions/{sid}/actions", {**_skip(pending), "kind": "select_product", "payload": {"sku": "X"}}),
        )
        assert wrong_kind.status_code == 409 and wrong_kind.json()["code"] == "not_allowed_now"
        ok = await client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", _skip(pending, "none")))
    assert ok.status_code == 200 and _summary(sse.parse(ok.text))["receipt"]["status"] == (
        "not_collected"
    )


async def test_upload_receipt_while_awaiting_goes_to_extract_then_confirm_card(mem_runtime):
    """等待凭证时以 purpose=receipt 上传 → receipt.image_ids 记录 → extract（票 40 OCR，此处无模型 → 空字段）
    → receipt_card + awaiting_input(confirm_receipt)；不再直接摘要。"""
    store = InMemoryImageStore()
    set_image_store(store)
    app.state.image_store = store
    try:
        async with _client() as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            await _regular_escalation(client, sid, "R1")
            events = await _send(client, sid, "这是发票", receipt_images=1, purpose="receipt")
            snap = await _snap(client, sid)
    finally:
        set_image_store(None)
        app.state.image_store = None
    assert _progress(events) == [("escalate", "extract")]
    assert events[0]["resumed"] is False  # 新消息 run，不是 Command(resume)
    types = [e["type"] for e in events]
    assert "receipt_card" in types and "escalation_summary" not in types
    pending = next(e for e in events if e["type"] == "awaiting_input")
    assert pending["kind"] == "confirm_receipt" and events[-1]["reason"] == "awaiting_input"
    st = (await app.state.session_graph.aget_state(_cfg(sid))).values
    assert len(st["receipt"]["image_ids"]) == 1 and st["pending_card"]["kind"] == "confirm_receipt"
    ref = next(r for r in st["image_refs"] if r["image_id"] == st["receipt"]["image_ids"][0])
    assert ref["purpose"] == "receipt"
    # 凭证图不进入读图（vision 只看 fault）：没有 diagnose.vision tool_call，只有 receipt_ocr
    assert [e["name"] for e in events if e["type"] == "tool_call"] == ["warranty.receipt_ocr"] * 2
    assert snap.pending_input is not None and snap.pending_input.kind == "confirm_receipt"
    um = [i for i in snap.timeline if i.kind == "user_message"][-1]
    assert um.images[0].purpose == "receipt"


async def test_receipt_image_outside_upload_receipt_is_not_a_receipt(mem_runtime):
    """在非 upload_receipt 位置上传 purpose=receipt 的图片 → 走普通消息（rediagnose 语义），不建立凭证状态（验收项 3）。"""
    store = InMemoryImageStore()
    set_image_store(store)
    app.state.image_store = store
    try:
        async with _client() as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            events = await _send(
                client, sid, "扫地机 X10 不吸了", receipt_images=1, purpose="receipt"
            )
    finally:
        set_image_store(None)
        app.state.image_store = None
    stages = [s for s, _ in _progress(events)]
    assert "escalate" not in stages and "diagnose" in stages
    assert events[-1]["reason"] == "awaiting_input"  # 普通排障轮：步骤卡（票 34）
    st = (await app.state.session_graph.aget_state(_cfg(sid))).values
    assert st.get("receipt") is None and st["image_refs"][0]["purpose"] == "receipt"
    assert not [e for e in events if e["type"] == "tool_call" and e["name"] == "diagnose.vision"]


async def test_r6_mention_enters_receipt_flow_on_regular_escalation(mem_runtime):
    """用户提及退换 / 保修（R6 flag）在常规升级时进入凭证子流程；R6 只是标记，不单独升级（验收项 4）。"""
    set_rules_service(RulesService(RULES, hot_reload=False))
    try:
        async with _client() as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            first = await _send(client, sid, "扫地机 X10 不吸了，我想申请保修")
            assert "escalate" not in [s for s, _ in _progress(first)]  # R6 本身不升级
            st = (await app.state.session_graph.aget_state(_cfg(sid))).values
            assert any(f["rule_id"] == "R6" for f in st["safety_flags"])
            events = await escalate_on_feedback(client, sid, "R2")
            pending = next(e for e in events if e["type"] == "awaiting_input")
            assert pending["kind"] == "upload_receipt"
            resumed = sse.parse(
                (await client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", _skip(pending, "none")))).text
            )
    finally:
        set_rules_service(None)
    summary = _summary(resumed)
    assert summary["reason"]["rule_id"] == "R2" and summary["receipt"]["status"] == "not_collected"
    assert summary["receipt"]["next_step"] == "请准备购买凭证，人工协助核实"


async def test_safety_and_human_escalations_skip_receipt_collection(mem_runtime):
    """R4（安全词）与 request_human（R3）直接摘要，不出现 collect_receipt（09 §5.1）。"""
    set_rules_service(RulesService(RULES, hot_reload=False))
    try:
        async with _client() as client:
            a = (await client.post("/sessions")).json()["session_id"]
            r4 = await _send(client, a, "扫地机充电时冒烟了")
            b = (await client.post("/sessions")).json()["session_id"]
            r3 = sse.parse(
                (
                    await client.post(
                        f"/sessions/{b}/actions",
                        json=await action_body(client, f"/sessions/{b}/actions", {
                            "action_id": uuid.uuid4().hex,
                            "expected_version": 0,
                            "kind": "request_human",
                        }),
                    )
                ).text
            )
    finally:
        set_rules_service(None)
    for events, reason in ((r4, "R4"), (r3, "R3")):
        assert ("escalate", "collect_receipt") not in _progress(events)
        assert "awaiting_input" not in [e["type"] for e in events]
        s = _summary(events)
        assert s["reason"]["rule_id"] == reason and s["receipt"]["status"] == "not_collected"
    assert {"R3", "R4", "R5", "R7", "R8"} == set(DIRECT_SUMMARY_REASONS)
