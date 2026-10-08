"""票 40：凭证识别 warranty.receipt_ocr 与 ReceiptCard 字段确认（后端）。

A3 样本用假 router 回放 OCR 输出；真实订单截图识别留票 42 bake-off（需视觉模型 key）。
"""

from __future__ import annotations

import io
import json
import uuid

from haike_contracts.events import parse_event
from haike_contracts.snapshot import SessionSnapshot
from httpx import ASGITransport, AsyncClient

from app.images import InMemoryImageStore
from app.images.runtime import set_image_store
from app.main import app
from app.models.config import load_models_config
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter
from app.models.runtime import set_model_router
from app.sessions import sse
from app.sessions.receipt import (
    FIELDS,
    LOW_CONFIDENCE,
    card_payload,
    extract_receipt,
    stated_purchase_date,
)
from tests.message_form import action_body, escalate_on_feedback, message_form
from tests.scripted_model import ScriptedSemanticModel as FakeChatModel
from tests.test_images import png_bytes
from tests.test_vision import CONFIG, NO_VISION_CONFIG, _router

INTAKE = {"emotion_level": "calm", "product_hints": [], "symptoms": [], "wants_human": False}
A3_OCR = {
    "order_no": "2024031512345678",
    "seller": "京东 eufy 官方旗舰店",
    "purchase_date": "2024-03-15",
    "amount": None,
    "confidence": {"order_no": 0.95, "seller": 0.55, "purchase_date": 0.9},
    "unreadable": ["amount"],
}


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _cfg(sid: str):
    return {"configurable": {"thread_id": sid}}


async def _to_confirm_card(client, sid: str, n_images: int = 1):
    """一轮正常对话 → 注入 R1 → 进入 collect_receipt → 上传凭证 → OCR → receipt_card。"""
    r = await client.post(f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": "扫地机 X10 不吸了"}))
    assert r.status_code == 200
    await escalate_on_feedback(client, sid, "R6")
    files = [
        ("images", (f"receipt{i}.png", io.BytesIO(png_bytes(700 + i)), "image/png"))
        for i in range(n_images)
    ]
    r = await client.post(
        f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": "订单截图", "purpose": "receipt"}), files=files
    )
    assert r.status_code == 200, r.text
    return sse.parse(r.text)


def _confirm(pending: dict, fields: dict, edited: list[str]) -> dict:
    return {
        "action_id": uuid.uuid4().hex,
        "input_token": pending["input_token"],
        "card_id": pending["card_id"],
        "expected_version": pending["version"],
        "kind": "confirm_receipt",
        "payload": {"fields": fields, "edited": edited},
    }


def _two_fakes_router(tmp_path, config: str, ocr_outputs: list, env=None):
    """文本模型（intake / synthesize / reply）与视觉模型（receipt_ocr）各一个假模型：
    文本侧给足 intake 输出，其余调用抛错走降级，保证 OCR 脚本不被 synthesize / reply 消耗。"""
    p = tmp_path / "models.yaml"
    p.write_text(config, encoding="utf-8")
    cfg = load_models_config(p)
    text_fake = FakeChatModel(
        script=[json.dumps(INTAKE, ensure_ascii=False)] * 3 + [RuntimeError("no text model")] * 12
    )
    ocr_fake = FakeChatModel(
        script=[
            o if isinstance(o, Exception) else json.dumps(o, ensure_ascii=False)
            for o in ocr_outputs
        ]
    )
    reg = ModelRegistry(cfg, env=env if env is not None else {"K1": "x", "K2": "x"})

    def factory(resolved, route):
        return ocr_fake if resolved.alias.startswith("vl_") else text_fake

    return ModelRouter(reg, model_factory=factory), ocr_fake


class _Env:
    def __init__(self, tmp_path, config: str, outputs: list, env=None):
        self.router, self.fake = _two_fakes_router(tmp_path, config, outputs, env=env)
        self.store = InMemoryImageStore()

    def __enter__(self):
        set_model_router(self.router)
        set_image_store(self.store)
        app.state.image_store = self.store
        return self

    def __exit__(self, *exc):
        set_model_router(None)
        set_image_store(None)
        app.state.image_store = None


async def test_a3_sample_recognizes_order_and_seller_with_low_confidence_flag(
    mem_runtime, tmp_path
):
    """A3 样本订单截图 → receipt_card 含订单号与商家；seller 置信 0.55 < 0.7 由前端标黄；country / amount unreadable（验收项 1）。"""
    with _Env(tmp_path, CONFIG, [A3_OCR]) as env:
        async with _client() as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            events = await _to_confirm_card(client, sid)
            snap = SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())
    card = next(e for e in events if e["type"] == "receipt_card")
    parse_event(card)
    assert card["fields"] == {
        "order_no": "2024031512345678",
        "seller": "京东 eufy 官方旗舰店",
        "country": None,
        "purchase_date": "2024-03-15",
        "amount": None,
    }
    assert card["confidence"]["order_no"] == 0.95 and card["confidence"]["seller"] == 0.55
    assert [k for k, v in card["confidence"].items() if v < LOW_CONFIDENCE] == ["seller", "country", "amount"]
    assert card["unreadable"] == ["amount", "country"]
    st = (await app.state.session_graph.aget_state(_cfg(sid))).values
    assert card["issue_id"] == st["active_issue_id"]
    assert card["card_id"] == snap.pending_input.card_id
    tools = [e for e in events if e["type"] == "tool_call" and e["name"] == "warranty.receipt_ocr"]
    assert [t["status"] for t in tools] == ["started", "finished"] and "3 个字段" in tools[1][
        "summary"
    ]
    pending = next(e for e in events if e["type"] == "awaiting_input")
    assert pending["kind"] == "confirm_receipt" and pending["card_id"] == card["card_id"]
    assert pending["version"] == card["version"] == events[-1]["version"]
    # OCR 调用：internal、带凭证图、任务名正确、图片说明包 <data>
    ocr_call = next(c for c in env.fake.calls if c["metadata"]["task"] == "warranty.receipt_ocr")
    assert "internal" in ocr_call["tags"]
    human = next(m.content for m in ocr_call["messages"] if isinstance(m.content, list))
    assert (
        any(p.get("type") == "image_url" for p in human)
        and 'kind="receipt_image"' in human[0]["text"]
    )
    # 快照：receipt_card 折叠一张，尚无 confirmed_fields
    items = [i for i in snap.timeline if i.kind == "receipt_card"]
    assert (
        len(items) == 1
        and items[0].confirmed_fields is None
        and items[0].fields.order_no == ("2024031512345678")
    )
    assert snap.pending_input.kind == "confirm_receipt" and snap.substage == "confirm_fields"


async def test_confirm_with_edited_field_records_edited_and_summarizes(mem_runtime, tmp_path):
    """用户修改一个字段后 edited[] 含该字段名（验收项 2）；确认后完成 lookup 并进入摘要。"""
    with _Env(tmp_path, CONFIG, [A3_OCR]):
        async with _client() as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            events = await _to_confirm_card(client, sid)
            pending = next(e for e in events if e["type"] == "awaiting_input")
            fields = {
                "order_no": "2024031512345678",
                "seller": "京东自营",  # 用户改了低置信的商家
                "country": "CN",
                "purchase_date": "2024-03-15",
                "amount": None,
            }
            resp = await client.post(
                f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", _confirm(pending, fields, ["seller", "country"]))
            )
            assert resp.status_code == 200, resp.text
            resumed = sse.parse(resp.text)
            snap = SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())
    assert resumed[0]["resumed"] is False
    types = [e["type"] for e in resumed]
    assert "receipt_card" not in types  # 已消费的卡片不重新发布
    assert "escalation_summary" in types and resumed[-1]["reason"] == "completed"
    st = (await app.state.session_graph.aget_state(_cfg(sid))).values
    assert (
        st["receipt"]["edited"] == ["seller", "country"] and st["receipt"]["fields"]["seller"] == "京东自营"
    )
    # 订单号不在主办方订单内 → 按商家 + 国家查名录：CN 不在授权名录内
    assert st["receipt"]["status"] == "dealer_unauthorized"
    assert st["card_results"][pending["card_id"]] == {
        "confirmed_fields": st["receipt"]["fields"],
        "edited": ["seller", "country"],
    }
    item = next(i for i in snap.timeline if i.kind == "receipt_card")
    assert item.confirmed_fields.seller == "京东自营" and item.skipped_reason is None
    summary = next(e for e in resumed if e["type"] == "escalation_summary")["summary"]
    assert summary["receipt"]["status"] == "dealer_unauthorized"
    assert summary["receipt"]["next_step"] == "购买商家不在授权经销商名录内，请联系购买商家售后"
    # 重复确认（旧 version）→ 409
    again = await _client().__aenter__()
    r = await again.post(f"/sessions/{sid}/actions", json=await action_body(again, f"/sessions/{sid}/actions", _confirm(pending, fields, [])))
    assert r.status_code == 409 and r.json()["code"] == "stale_version"
    await again.__aexit__(None, None, None)


async def test_all_unreadable_yields_empty_card_for_manual_input(mem_runtime, tmp_path):
    """OCR 全部 unreadable（或识别失败）→ 卡片字段为空、confidence 0、unreadable 全字段，可手输（验收项 3）。"""
    blank = {"confidence": {}, "unreadable": list(FIELDS)}
    with _Env(tmp_path, CONFIG, [blank]):
        async with _client() as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            events = await _to_confirm_card(client, sid)
            card = next(e for e in events if e["type"] == "receipt_card")
            assert card["fields"] == dict.fromkeys(FIELDS) and set(card["unreadable"]) == set(
                FIELDS
            )
            assert all(v == 0.0 for v in card["confidence"].values())
            pending = next(e for e in events if e["type"] == "awaiting_input")
            # 手输订单号
            resp = await client.post(
                f"/sessions/{sid}/actions",
                json=await action_body(client, f"/sessions/{sid}/actions", _confirm(pending, {"order_no": " 2024ABC ", "seller": None}, ["order_no"])),
            )
            assert resp.status_code == 200
            resumed = sse.parse(resp.text)
    st = (await app.state.session_graph.aget_state(_cfg(sid))).values
    assert st["receipt"]["fields"]["order_no"] == "2024ABC" and st["receipt"]["edited"] == [
        "order_no"
    ]
    assert resumed[-1]["reason"] == "completed"


async def test_ocr_failure_and_no_vision_still_emit_card_and_allow_skip(mem_runtime, tmp_path):
    """视觉链失败 / 无视觉模型：tool_call failed、卡片为空仍发出；字段确认阶段跳过 → needs_manual_check（凭证图已在）。"""
    with _Env(tmp_path, NO_VISION_CONFIG, [], env={"K1": "x"}):
        async with _client() as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            events = await _to_confirm_card(client, sid)
            tools = [e for e in events if e["type"] == "tool_call"]
            assert tools[-1]["status"] == "failed" and "手动填写或跳过" in tools[-1]["summary"]
            card = next(e for e in events if e["type"] == "receipt_card")
            assert card["fields"] == dict.fromkeys(FIELDS)
            pending = next(e for e in events if e["type"] == "awaiting_input")
            resp = await client.post(
                f"/sessions/{sid}/actions",
                json=await action_body(client, f"/sessions/{sid}/actions", {
                    "action_id": uuid.uuid4().hex,
                    "input_token": pending["input_token"],
                    "card_id": pending["card_id"],
                    "expected_version": pending["version"],
                    "kind": "skip_receipt",
                    "payload": {"reason": "unreadable"},
                }),
            )
            assert resp.status_code == 200
            resumed = sse.parse(resp.text)
            snap = SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())
    summary = next(e for e in resumed if e["type"] == "escalation_summary")["summary"]
    assert summary["receipt"]["status"] == "needs_manual_check"
    st = (await app.state.session_graph.aget_state(_cfg(sid))).values
    assert (
        st["receipt"]["skipped_reason"] == "unreadable"
        and st["receipt"]["ocr_status"] == "no_vision"
    )
    item = next(i for i in snap.timeline if i.kind == "receipt_card")
    assert item.skipped_reason == "unreadable"


async def test_receipt_card_has_no_warranty_conclusion_fields(mem_runtime, tmp_path):
    """receipt_card 只有 card_id / version / fields / confidence / unreadable（验收项 4）；契约 extra=forbid。"""
    with _Env(tmp_path, CONFIG, [{**A3_OCR, "amount": "¥2999.00"}]):
        async with _client() as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            events = await _to_confirm_card(client, sid)
    card = next(e for e in events if e["type"] == "receipt_card")
    assert set(card) == {
        "event_id", "recorded_at", "issue_id",
        "type",
        "seq",
        "run_id",
        "card_id",
        "version",
        "fields",
        "confidence",
        "unreadable",
    }
    assert set(card["fields"]) == set(FIELDS)
    for forbidden in ("warranty", "eligible", "in_warranty", "status", "verified"):
        assert forbidden not in str(card).lower()


async def test_extract_receipt_module_degrades_without_router_or_images(tmp_path):
    store = InMemoryImageStore()
    out = await extract_receipt(
        None, store, session_id="s", image_ids=["x"], refs=[], lane="domestic"
    )
    assert (
        out.status == "skipped"
        and out.fields == dict.fromkeys(FIELDS)
        and set(out.unreadable) == set(FIELDS)
    )
    router, _ = _router(tmp_path, CONFIG, [])
    out2 = await extract_receipt(
        router, store, session_id="s", image_ids=["gone"], refs=[], lane="domestic"
    )
    assert out2.status == "failed" and "not found" in (out2.reason or "")


def test_card_prefills_a_stated_purchase_date_only_where_ocr_found_none():
    """客户说过的购买日期只在凭证没识别出日期时预填，仍由客户在卡片上确认；不覆盖凭证上的值。"""
    blank = {"fields": {"order_no": "A1"}, "unreadable": ["purchase_date"]}
    payload = card_payload(blank, stated={"purchase_date": "2025-11-11", "region_use": "US"})
    assert payload["fields"]["purchase_date"] == "2025-11-11"
    assert "purchase_date" not in payload["unreadable"]
    assert set(payload["fields"]) == set(FIELDS)
    read = {"fields": {"purchase_date": "2025-11-12"}}
    assert card_payload(read, stated={"purchase_date": "2025-11-11"})["fields"]["purchase_date"] == "2025-11-12"
    assert card_payload(blank)["fields"]["purchase_date"] is None


def test_stated_purchase_date_must_be_a_real_day_not_in_the_future():
    today = "2026-09-25T10:00:00+08:00"
    assert stated_purchase_date("2025-11-11", today)
    assert not stated_purchase_date("2026-10-01", today)
    assert not stated_purchase_date("去年底", today)
    assert not stated_purchase_date("2025-11", today)
