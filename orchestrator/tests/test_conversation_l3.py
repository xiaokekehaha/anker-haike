"""L3 端到端：主办方 SOP 的物流与质保分支，跑在 data/official 的真实订单上（演示时钟 2026-10-08）。

物流：Anker001 两包裹均送达（T1）、Anker007 退回发件人（T8）、Anker008 预售未发（T9）。
质保：Anker016 保内（主案例 T55）、Anker011 过保（T29）、查不到订单 → Aeroflow 授权经销（T45）。
"""

import asyncio
import json
import uuid
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

import app.conversation.interpret as semantic
from app.actions.runtime import configure
from app.actions.store import ExecutionNeedsReview
from app.catalog import ProductCatalog
from app.conversation.interpret import TurnInterpretation
from app.images import InMemoryImageStore
from app.images.runtime import set_image_store
from app.main import app
from app.sessions.cards import set_catalog
from app.settings import settings


@pytest.fixture
async def l3_runtime(mem_runtime, monkeypatch):
    monkeypatch.setenv("HAIKE_LLM", "off")
    monkeypatch.setattr(settings, "demo_today", date(2026, 10, 8))
    set_catalog(ProductCatalog.from_yaml(settings.catalog_config_path))
    set_image_store(InMemoryImageStore())
    services = configure(memory=True)
    app.state.l3_services = services
    yield services
    await app.state.run_manager.shutdown()
    configure()
    set_catalog(None)
    set_image_store(None)
    app.state.l3_services = None


def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def said(rows):
    return "".join(e.get("delta", "") for e in rows)


async def send(client, sid, text, images=0):
    snap = (await client.get(f"/sessions/{sid}")).json()
    files = [("images", (f"p{i}.png", PNG, "image/png")) for i in range(images)] or None
    return await client.post(
        f"/sessions/{sid}/messages",
        data={"input_id": str(uuid.uuid4()), "expected_version": snap["version"], "text": text,
              **({"purpose": "fault"} if images else {})},
        files=files,
    )


async def act(client, sid, kind, payload):
    snap = (await client.get(f"/sessions/{sid}")).json()
    pending = snap["pending_input"]
    return await client.post(
        f"/sessions/{sid}/actions",
        json={
            "action_id": str(uuid.uuid4()),
            "expected_version": snap["version"],
            "target_issue_id": snap["active_issue_id"],
            "card_id": pending["card_id"],
            "input_token": pending["input_token"],
            "kind": kind,
            "payload": payload,
        },
    )


async def state_of(sid):
    return (await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})).values


def _png():
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (640, 480), (120, 120, 120)).save(buf, "PNG")
    return buf.getvalue()


PNG = _png()


def interpret_as(monkeypatch, mapping):
    """按原话指定意图；未列出的原话走原解析（无模型时的降级解析）。"""
    original = semantic.interpret_turn

    async def interpretation(router, state, **kwargs):
        if state.get("entry") == "message" and state.get("text") in mapping:
            return mapping[state["text"]], {"source": "test"}
        return await original(router, state, **kwargs)

    monkeypatch.setattr(semantic, "interpret_turn", interpretation)


REPLACE = TurnInterpretation(primary_intent="replacement_request", device_relation="current")


async def replacement_ready(client, monkeypatch, order="Anker016"):
    """T55：客户给出订单号要求换货 → 保内 → 缺照片与 SN → 补齐 → 换货单确认卡。"""
    interpret_as(monkeypatch, {
        f"左侧吸奶器没有吸力，订单 {order}，我要换货": REPLACE,
        "SN: T8D04121ABCD": TurnInterpretation(primary_intent="supplement", facts=[
            {"kind": "context", "context_field": "serial_number", "value": "T8D04121ABCD", "quote": "SN: T8D04121ABCD"},
        ]),
    })
    sid = (await client.post("/sessions")).json()["session_id"]
    first = events(await send(client, sid, f"左侧吸奶器没有吸力，订单 {order}，我要换货"))
    return sid, first


async def test_logistics_delivered_offers_carrier_investigation_not_reship(l3_runtime):
    """T1：两包裹都显示送达 → 不补发；按 D3 给承运商调查方案。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, "查物流 Anker001"))
        text = said(rows)
        assert "Anker1234567: delivered on 2026-09-21" in text and "Anker1234567-1: delivered on 2026-09-23" in text
        assert "can't send another shipment" in text
        card = next(e for e in rows if e["type"] == "proposal_card")
        assert [o["type"] for o in card["options"]] == ["carrier_investigation"]
        rows = events(await act(client, sid, "confirm_proposal", {"option_id": "carrier_investigation"}))
        receipt = next(e for e in rows if e["type"] == "execution_card")
        assert receipt["status"] == "succeeded" and "a colleague is handling it" in receipt["receipt"]["next_step"]
        order = await l3_runtime.backend.get_service_order(receipt["receipt"]["service_order_no"])
        assert order.type == "carrier_investigation" and order.order_no == "Anker001"
        state = await state_of(sid)
        case = await l3_runtime.cases.store.get(state["case_id"])
        assert case["status"] == "awaiting_approval"


async def test_logistics_returned_to_sender_offers_reship(l3_runtime):
    """T8：退回发件人 = 未送达 → 可补发。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, "my order Anker007 never arrived, where is it"))
        # 补发理由按包裹状态给（P2-3）：退回发件人就说退回，不再统一说「未显示送达」
        assert "returned to sender" in said(rows) and "arrange a reship for you" in said(rows)
        assert [o["type"] for o in next(e for e in rows if e["type"] == "proposal_card")["options"]] == ["reship"]
        rows = events(await act(client, sid, "confirm_proposal", {"option_id": "reship"}))
        assert any(e["type"] == "execution_card" and e["status"] == "succeeded" for e in rows)
        assert l3_runtime.backend.create_calls == 1


async def test_logistics_presale_only_informs_ship_date(l3_runtime):
    """T9：预售未发 → 告知预计发货日，不出补发方案。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, "查物流 Anker008"))
        assert "pre-order" in said(rows) and "expected to ship on 2026-10-20" in said(rows)
        assert not any(e["type"] == "proposal_card" for e in rows)


async def test_logistics_by_tracking_number(l3_runtime):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, "UPS says label created for Anker1234567-3"))
        assert any(e["type"] == "tool_call" and e["name"] == "logistics.query" and e["status"] == "finished" for e in rows)
        assert "Order Anker002" in said(rows)


async def test_logistics_missing_order_asks_for_number(l3_runtime):
    """T7：客户没给单号。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        assert "order number" in said(events(await send(client, sid, "查物流")))
        assert "delivered" in said(events(await send(client, sid, "Anker003")))


async def test_in_warranty_replacement_collects_sop_evidence_then_submits(l3_runtime, monkeypatch):
    """T55 主案例：订单保内 → 缺照片与 SN → 补齐后出换货单卡 → 提交 → 转人工 → 满意度。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid, rows = await replacement_ready(client, monkeypatch)
        text = said(rows)
        assert "order Anker016 is under warranty until 2027-04-01" in text
        assert "a photo or video of the fault" in text and "serial number (SN)" in text and "shipping address" not in text
        assert not any(e["type"] == "proposal_card" for e in rows)
        state = await state_of(sid)
        assert state["warranty"]["status"] == "in_warranty"
        assert state["product_confirmed"]["sku"] == "T8D04"
        rows = events(await send(client, sid, "照片", images=1))
        assert "serial number (SN)" in said(rows) and not any(e["type"] == "proposal_card" for e in rows)
        rows = events(await send(client, sid, "SN: T8D04121ABCD"))
        card = next(e for e in rows if e["type"] == "proposal_card")
        assert [o["type"] for o in card["options"]] == ["replace"]
        rows = events(await act(client, sid, "confirm_proposal", {"option_id": "replace"}))
        receipt = next(e for e in rows if e["type"] == "execution_card")
        assert receipt["status"] == "succeeded" and "工作日" not in receipt["receipt"]["next_step"]
        created = await l3_runtime.backend.get_service_order(receipt["receipt"]["service_order_no"])
        assert created.type == "replace" and created.sku == "T8D04"
        assert set(created.evidence) == {"order_or_receipt", "address", "photo_or_video", "serial_number"}
        snap = (await client.get(f"/sessions/{sid}")).json()
        assert snap["pending_input"]["kind"] == "rate_satisfaction"
        state = await state_of(sid)
        case = await l3_runtime.cases.store.get(state["case_id"])
        assert case["status"] == "awaiting_approval"
        assert case["external_refs"]["service_order_no"] == created.service_order_no
        await act(client, sid, "rate_satisfaction", {"score": 5})
        assert len(l3_runtime.cases.store.ratings) == 1


async def test_out_of_warranty_is_declined_politely(l3_runtime, monkeypatch):
    """T29：订单 Anker011 质保至 2025-11-30 → 告知过保并委婉拒绝，不提交服务单。"""
    interpret_as(monkeypatch, {"污水盘不排水，订单 Anker011，申请换货": REPLACE})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, "污水盘不排水，订单 Anker011，申请换货"))
        text = said(rows)
        assert "2025-11-30" in text and "warranty has expired" in text and "I'm sorry" in text
        assert not any(e["type"] in {"proposal_card", "execution_card"} for e in rows)
        state = await state_of(sid)
        assert (await l3_runtime.cases.store.get(state["case_id"]))["status"] == "closed_unresolved"
        assert l3_runtime.backend.create_calls == 0


async def test_no_order_goes_through_dealer_directory(l3_runtime, monkeypatch):
    """T45：没有订单号 → 收凭证 → 凭证商家 Aeroflow（US）命中授权名录 → 12 个月保内。"""
    interpret_as(monkeypatch, {"pump not charging, bought from a reseller, want a replacement": REPLACE})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, "pump not charging, bought from a reseller, want a replacement"))
        assert "upload your proof of purchase" in said(rows)
        assert (await client.get(f"/sessions/{sid}")).json()["pending_input"]["kind"] == "upload_receipt"
        snap = (await client.get(f"/sessions/{sid}")).json()
        await client.post(
            f"/sessions/{sid}/messages",
            data={"input_id": str(uuid.uuid4()), "expected_version": snap["version"], "text": "receipt", "purpose": "receipt"},
            files=[("images", ("r.png", PNG, "image/png"))],
        )
        assert (await client.get(f"/sessions/{sid}")).json()["pending_input"]["kind"] == "confirm_receipt"
        rows = events(await act(client, sid, "confirm_receipt", {
            "fields": {"order_no": None, "seller": "Aeroflow", "country": "US", "purchase_date": "2025-12-09", "amount": None},
            "edited": ["seller", "country", "purchase_date"],
        }))
        assert not any(e["type"] == "error" for e in rows), rows
        state = await state_of(sid)
        assert state["receipt"]["status"] == "dealer_authorized"
        assert state["warranty"]["status"] == "in_warranty" and state["warranty"]["basis"] == "dealer"
        assert state["warranty"]["warranty_end"] == "2026-12-09"


async def test_unauthorized_dealer_is_guided_to_seller(l3_runtime, monkeypatch):
    interpret_as(monkeypatch, {"want a replacement, bought it on a marketplace": REPLACE})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await send(client, sid, "want a replacement, bought it on a marketplace")
        snap = (await client.get(f"/sessions/{sid}")).json()
        await client.post(
            f"/sessions/{sid}/messages",
            data={"input_id": str(uuid.uuid4()), "expected_version": snap["version"], "text": "receipt", "purpose": "receipt"},
            files=[("images", ("r.png", PNG, "image/png"))],
        )
        rows = events(await act(client, sid, "confirm_receipt", {
            "fields": {"order_no": None, "seller": "Random Marketplace Seller", "country": "US", "purchase_date": "2026-05-01", "amount": None},
            "edited": ["seller"],
        }))
        assert "authorized dealer" in said(rows) and "contact the seller" in said(rows)
        state = await state_of(sid)
        assert state["warranty"]["status"] == "unauthorized_dealer"
        assert l3_runtime.backend.create_calls == 0


async def test_refund_request_follows_same_warranty_gate(l3_runtime, monkeypatch):
    interpret_as(monkeypatch, {"订单 Anker013 电机异响，我要退款": TurnInterpretation(primary_intent="refund_request", device_relation="current")})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, "订单 Anker013 电机异响，我要退款"))
        assert "under warranty until" in said(rows) and "Before I can submit the refund request, I still need" in said(rows)
        assert (await state_of(sid))["requested_remedy"] == "refund"


async def test_gate_blocks_safety_risk_and_hands_to_human(l3_runtime, monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid, _ = await replacement_ready(client, monkeypatch)
        await send(client, sid, "照片", images=1)
        await send(client, sid, "SN: T8D04121ABCD")
        # 本轮与 card 并行报告烫伤（T45 的情形）：风险写入问题记录后，确认卡被作废，闸门不提交。
        await send(client, sid, "the heating part burned me")
        state = await state_of(sid)
        assert any(r["rule_id"] == "R4" and r["status"] == "reported" for r in state["risk_cases"])
        snap = (await client.get(f"/sessions/{sid}")).json()
        if snap["pending_input"] and snap["pending_input"]["kind"] == "confirm_proposal":
            rows = events(await act(client, sid, "confirm_proposal", {"option_id": "replace"}))
        else:
            rows = []
        assert not any(e["type"] == "execution_card" for e in rows)
        assert l3_runtime.backend.create_calls == 0


async def test_human_approval_submits_held_service_order(l3_runtime, monkeypatch):
    """闸门因安全风险转人工；人工核实后批准 → 按原方案提交服务单。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid, _ = await replacement_ready(client, monkeypatch)
        await send(client, sid, "照片", images=1)
        await send(client, sid, "SN: T8D04121ABCD")
        await act(client, sid, "decline_proposal", {"reason": "request_human"})
        case = next(c for c in (await client.get("/admin/api/cases/queue")).json()["items"] if c["session_id"] == sid)
        response = await client.post(f"/admin/api/cases/{case['case_id']}/decision", json={
            "decision_id": str(uuid.uuid4()), "expected_revision": case["revision"], "decision": "approve",
            "option_id": "replace", "note": "已核实，同意换货",
        })
        assert response.status_code == 200, response.text
        for _ in range(100):
            if not app.state.run_manager.is_live(response.json()["run_id"]):
                break
            await asyncio.sleep(0.01)
        detail = (await client.get(f"/admin/api/cases/{case['case_id']}")).json()
        [execution] = detail["executions"]
        assert execution["action_kind"] == "service_order.create" and execution["status"] == "succeeded"
        assert detail["handoff_summary"]["warranty"]["status"] == "in_warranty"


async def test_transient_failure_retries_without_duplicate(l3_runtime, monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid, _ = await replacement_ready(client, monkeypatch)
        await send(client, sid, "照片", images=1)
        await send(client, sid, "SN: T8D04121ABCD")
        l3_runtime.backend.faults.append({"op": "create_service_order", "key": "Anker016", "mode": "created_then_timeout"})
        failed = events(await act(client, sid, "confirm_proposal", {"option_id": "replace"}))
        assert any(e["type"] == "case_changed" and e["status"] == "executing_failed" for e in failed)
        retry = next(e for e in failed if e["type"] == "proposal_card")
        assert retry["retry"]
        l3_runtime.backend.faults.clear()
        rows = events(await act(client, sid, "confirm_proposal", {"option_id": "replace"}))
        assert next(e for e in rows if e["type"] == "execution_card")["status"] == "succeeded"
        assert l3_runtime.backend.create_calls == 1
        assert not any(e["type"] == "error" for e in [*failed, *rows])


async def test_execution_needing_review_goes_to_human_queue(l3_runtime, monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid, _ = await replacement_ready(client, monkeypatch)
        await send(client, sid, "照片", images=1)
        await send(client, sid, "SN: T8D04121ABCD")

        async def stuck(*args, **kwargs):
            raise ExecutionNeedsReview("执行状态需人工核实")

        monkeypatch.setattr(l3_runtime.executor, "run", stuck)
        rows = events(await act(client, sid, "confirm_proposal", {"option_id": "replace"}))
        assert any(e["type"] == "case_changed" and e["status"] == "awaiting_approval" for e in rows)
        assert "passed it to a colleague to check" in said(rows)


async def test_consult_warranty_reads_order_warranty_end(l3_runtime):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await send(client, sid, "查物流 Anker016")
        rows = events(await send(client, sid, "这个订单还在保修期吗"))
        assert any(e["type"] == "tool_call" and e["name"] == "warranty.check" and e["status"] == "finished" for e in rows), rows
        assert "2027-04-01" in said(rows)


async def test_two_orders_do_not_execute_a_random_query(l3_runtime):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, "查 Anker001 和 Anker003 的物流"))
        assert not any(e["type"] == "tool_call" for e in rows)
        assert "more than one order" in said(rows)
        rows = events(await send(client, sid, "Anker003"))
        assert any(e["type"] == "tool_call" and e["status"] == "finished" for e in rows)


async def test_complaint_marks_existing_case_priority(l3_runtime, monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid, _ = await replacement_ready(client, monkeypatch)
        rows = events(await send(client, sid, "我要投诉，太烂了"))
        row = next(r for r in await l3_runtime.cases.store.queue(status=None) if r["session_id"] == sid)
        assert row["complaint_risk"] and row["priority"] == "high"
        assert "human agent" in said(rows)
        assert l3_runtime.backend.create_calls == 0


async def test_out_of_warranty_continues_pending_troubleshooting(l3_runtime, monkeypatch):
    """T51：过保只是关闭免费换货这一项；同一句里的排障请求仍要处理，不能留 pending 却把会话标成 done（2026-10-09 I6）。"""
    from app.knowledge.runtime import set_knowledge_adapter
    from tests.fake_qa import QAHitAdapter

    text = "I need help with possibly a replacement for my breast pump. It won't hold the battery and keeps cutting off. Order Anker014"
    interpret_as(monkeypatch, {text: TurnInterpretation(
        primary_intent="replacement_request", secondary_intents=["report_problem"], device_relation="current",
        facts=[{"value": "won't hold the battery, keeps cutting off", "quote": "It won't hold the battery and keeps cutting off"}],
    )})
    set_knowledge_adapter(QAHitAdapter("bp-0043"))
    try:
        await _out_of_warranty_then_troubleshoot(client_text=text, l3_runtime=l3_runtime)
    finally:
        set_knowledge_adapter(None)


async def _out_of_warranty_then_troubleshoot(*, client_text, l3_runtime):
    text = client_text
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, text))
        text_out = said(rows)
        assert "2026-07-30" in text_out and "warranty has expired" in text_out
        assert "official checks" in text_out
        assert not any(e["type"] in {"proposal_card", "execution_card"} for e in rows)
        state = await state_of(sid)
        assert (await l3_runtime.cases.store.get(state["case_id"]))["status"] == "closed_unresolved"
        queue = state["task_queue"]
        assert [(t["intent"], t["status"]) for t in queue if t["intent"] == "replacement_request"] == [("replacement_request", "done")]
        assert not [t for t in queue if t["status"] == "pending"]
        # 排障任务被推进到检索 / 出卡，而不是再绕回已关闭的案件说「waiting to be processed」
        assert "waiting to be processed" not in text_out
        assert any(e["type"] == "step_card" for e in rows), [e["type"] for e in rows]
        assert state["requested_remedy"] is None


async def test_handoff_after_closed_case_records_without_requeue(l3_runtime, monkeypatch):
    """过保结案后排障走到交接：案件已关闭，只记录摘要，不再入人工队列（否则 closed_unresolved → awaiting_approval 非法迁移）。"""
    text = "I need help with possibly a replacement for my breast pump. It won't hold the battery and keeps cutting off. Order Anker014"
    interpret_as(monkeypatch, {text: TurnInterpretation(
        primary_intent="replacement_request", secondary_intents=["report_problem"], device_relation="current",
        facts=[{"value": "won't hold the battery, keeps cutting off", "quote": "It won't hold the battery and keeps cutting off"}],
    )})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, text))
        assert not any(e["type"] == "error" for e in rows), rows
        state = await state_of(sid)
        case = await l3_runtime.cases.store.get(state["case_id"])
        assert case["status"] == "closed_unresolved"
        # 无知识库 → R5：摘要只记录进已关闭案件，不入队、不说「已提交审核」
        assert state["stage"] != "awaiting_human" and "submitted" not in said(rows)
        assert any(e["type"] == "handoff_summary" for e in case["events"])


async def test_t9_summary_is_refreshed_with_logistics_after_handoff(l3_runtime, monkeypatch):
    """T9：暂缓诉求先交人工、物流随后查到；交接摘要必须补入后来获得的物流事实，不能停在「产品未确认」（I8）。"""
    text = "I am writing about the shipping of the vacuum, order Anker008. If you have not shipped, don't and let's first talk about your other products."
    interpret_as(monkeypatch, {text: TurnInterpretation(
        primary_intent="order_change", secondary_intents=["logistics_query"], device_relation="current",
    )})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, text))
        assert "pre-order" in said(rows) and "passed your request" in said(rows)
        state = await state_of(sid)
        case = await l3_runtime.cases.store.get(state["case_id"])
        assert case["status"] == "awaiting_approval"
        latest = [e["payload"] for e in case["events"] if e["type"] == "handoff_summary"][-1]
        business = latest["business"]
        assert business["kind"] == "order_change"
        assert "If you have not shipped" in business["known"]["condition"]
        assert "not shipped" in business["known"]["package_status"]
        assert "If you have not shipped" in latest["reason"]["text"]


async def test_t47_hub_query_is_not_answered_with_the_old_main_unit_delivery(l3_runtime):
    """第三批 I8（T47）：客户问 Hub 配件 T8D02181-80 的运单，订单 Anker010 只有整机 T8D04121 的旧包裹。
    旧整机签收照样告知，但要说明没有 Hub 的发货记录并索取配件订单 / 案件号，不给承运商调查方案。"""
    text = "Is there a tracking number for my shipment yet?\nSKU: T8D02181-80 (S1/S1 Pro Pump Hub Brown)\nQuantity: 1\nOrder: Anker010"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, text))
        said_text = said(rows)
        assert "delivered on 2025-12-07" in said_text
        assert "T8D02181-80" in said_text and "don't see a separate shipment" in said_text
        assert "carrier investigation" not in said_text.casefold()
        assert not any(e["type"] == "proposal_card" for e in rows)


async def test_t2_conflicting_package_description_is_flagged_not_swapped(l3_runtime):
    text = ("I am reaching out regarding my order Anker002. I have received one package today with tracking number Anker1234567-2. "
            "The package only contains the replacement accessories kit. I have not received the Eufy S1 robot vacuum yet. "
            "When trying to track Anker1234567-3, UPS says the label has been created.")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        rows = events(await send(client, sid, text))
        said_text = said(rows)
        assert "Anker1234567-2" in said_text and "Anker1234567-3" in said_text
        assert "differs" in said_text and "confirm" in said_text.casefold()
