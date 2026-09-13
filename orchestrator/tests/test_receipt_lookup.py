"""票 41：规则全分支、A3 API/SSE/快照与独立 schema seed。"""

from __future__ import annotations

from tests.message_form import action_body

import json
import uuid
from datetime import date

import pytest
from haike_contracts.events import parse_event
from pydantic import ValidationError

from app.main import app
from app.sessions import sse
from app.sessions.receipt import confirmed_receipt
from app.settings import REPO_ROOT
from app.warranty.service import ReceiptLookup, ReferenceData
from tests.test_sessions_receipt_card import CONFIG, _client, _confirm, _Env, _to_confirm_card

X10 = "EUFY-X10-PRO-OMNI"
DEALER = "海科演示授权经销商"


def reference():
    return ReferenceData.from_yaml(REPO_ROOT / "config" / "receipt_reference.yaml")


def receipt(order_no=None, channel=None, confidence=0.95, edited=()):
    return {
        "fields": {"order_no": order_no, "channel": channel},
        "confidence": {"order_no": confidence},
        "edited": list(edited),
    }


ORDER_FACTS = {"channel": DEALER, "purchase_date": "2026-03-15"}


@pytest.mark.parametrize(
    "input,sku,status,facts,conflicts",
    [
        (receipt(), X10, "insufficient", {}, 0),
        (receipt("DEMO-X10-001", "任意 OCR 渠道"), X10, "order_verified", ORDER_FACTS, 0),
        (receipt("DEMO-S1-002"), X10, "order_product_mismatch", {}, 1),
        (receipt("DEMO-X10-001", confidence=0.69), X10, "needs_manual_check", {}, 1),
        (receipt("DEMO-S1-002", confidence=0.69), X10, "needs_manual_check", {}, 2),
        (receipt("DEMO-X10-001", confidence=0.7), X10, "order_verified", ORDER_FACTS, 0),
        (
            receipt("DEMO-X10-001", confidence=0.1, edited=["order_no"]),
            X10,
            "order_verified",
            ORDER_FACTS,
            0,
        ),
        (
            receipt("UNKNOWN", DEALER),
            X10,
            "channel_in_directory",
            {"dealer.name": DEALER, "authorized": "true"},
            0,
        ),
        (
            receipt(None, "海科演示未授权经销商"),
            X10,
            "channel_in_directory",
            {"dealer.name": "海科演示未授权经销商", "authorized": "false"},
            0,
        ),
        (receipt("UNKNOWN", "非名录店铺"), X10, "channel_unknown", {}, 0),
        (receipt(None, DEALER + "假冒店"), X10, "channel_unknown", {}, 0),
        (receipt("DEMO-X10-001"), None, "needs_manual_check", {}, 1),
        (receipt(" ｄｅｍｏ－ｘ１０－００１ "), X10, "order_verified", ORDER_FACTS, 0),
    ],
)
def test_l1_l6(input, sku, status, facts, conflicts):
    before = json.dumps(input)
    out = ReceiptLookup(reference()).lookup(input, {"sku": sku} if sku else None)
    assert out.status == status and out.verified_facts == facts
    assert len(out.conflicts) == conflicts and out.next_step
    assert json.dumps(input) == before
    for term in ("可保", "标准质保", "免费维修", "免费换新"):
        assert term not in out.model_dump_json()


def test_duplicate_reference_and_invalid_date_rejected():
    data = reference().model_dump(mode="json")
    data["orders"].append({**data["orders"][0], "order_no": "demo-x10-001"})
    with pytest.raises(ValidationError, match="duplicate"):
        ReferenceData.model_validate(data)
    data = reference().model_dump(mode="json")
    data["orders"][0]["purchase_date"] = "nonsense"
    with pytest.raises(ValidationError):
        ReferenceData.model_validate(data)


def test_edit_flag_without_change_cannot_bypass_low_confidence():
    state = {"receipt": receipt("DEMO-X10-001", confidence=0.1), "product_confirmed": {"sku": X10}}
    out = confirmed_receipt(state, {"order_no": "DEMO-X10-001"}, ["order_no"])
    assert out["status"] == "needs_manual_check" and out["edited"] == []
    state["receipt"]["fields"]["order_no"] = "wrong OCR"
    out = confirmed_receipt(state, {"order_no": "DEMO-X10-001"}, ["order_no"])
    assert out["status"] == "order_verified" and out["edited"] == ["order_no"]


@pytest.mark.parametrize(
    "order,confidence,status",
    [
        ("UNKNOWN-A3", 0.95, "channel_in_directory"),
        ("DEMO-S1-002", 0.95, "order_product_mismatch"),
        ("DEMO-X10-001", 0.2, "needs_manual_check"),
        ("DEMO-X10-001", 0.95, "order_verified"),
    ],
)
async def test_a3_api_lookup_summary_snapshot_and_replay(
    mem_runtime, tmp_path, order, confidence, status
):
    ocr = {
        "order_no": order,
        "channel": DEALER,
        "confidence": {"order_no": confidence, "channel": 0.9},
    }
    with _Env(tmp_path, CONFIG, [ocr]):
        async with _client() as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            events = await _to_confirm_card(client, sid)
            pending = next(e for e in events if e["type"] == "awaiting_input")
            action = _confirm(pending, {"order_no": order, "channel": DEALER}, [])
            result = await client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", action))
            assert result.status_code == 200, result.text
            events = sse.parse(result.text)
            for event in events:
                parse_event(event)
            summary = next(e["summary"] for e in events if e["type"] == "escalation_summary")
            assert summary["receipt"]["status"] == status
            assert summary["receipt"]["next_step"]
            if status in {"order_product_mismatch", "needs_manual_check"}:
                assert summary["receipt"]["conflicts"]
            if status == "channel_in_directory":
                assert summary["receipt"]["verified_facts"] == {
                    "dealer.name": DEALER,
                    "authorized": "true",
                }
            assert events[-1]["reason"] == "completed"
            snap = (await client.get(f"/sessions/{sid}")).json()
            item = next(x for x in snap["timeline"] if x["kind"] == "escalation_summary")
            assert item["summary"]["receipt"] == summary["receipt"]
            assert snap["pending_input"] is None
            replay = await client.post(f"/sessions/{sid}/actions", json=await action_body(client, f"/sessions/{sid}/actions", action))
            assert replay.status_code == 200 and replay.headers["X-Input-Replayed"] == "true"
            assert sse.parse(replay.text) == events
            st = (
                await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})
            ).values
            assert st["receipt"]["status"] == status
            assert all(
                term not in json.dumps(summary, ensure_ascii=False) for term in ("可保", "标准质保")
            )


async def test_reference_seed_roundtrip_and_update_in_isolated_schema():
    from psycopg_pool import AsyncConnectionPool

    from app.settings import settings
    from app.warranty import store
    from tests.test_catalog import _pool

    pool = await _pool()
    schema = "test_receipts_" + uuid.uuid4().hex
    isolated = AsyncConnectionPool(
        settings.database_url,
        min_size=1,
        max_size=1,
        open=False,
        kwargs={"autocommit": True, "options": f"-c search_path={schema}"},
    )
    async with pool.connection() as conn:
        await conn.execute(f'create schema "{schema}"')
    try:
        await isolated.open(wait=True)
        data = reference()
        assert await store.seed_reference(isolated, data) == await store.seed_reference(
            isolated, data
        )
        loaded = await store.load_from_db(isolated)
        assert loaded.orders == sorted(data.orders, key=lambda o: o.order_no)
        changed = data.model_copy(
            update={
                "orders": [data.orders[0].model_copy(update={"purchase_date": date(2026, 5, 6)})]
            }
        )
        await store.seed_reference(isolated, changed)
        out = ReceiptLookup(await store.load_from_db(isolated)).lookup(
            receipt("DEMO-X10-001"), {"sku": X10}
        )
        assert out.verified_facts["purchase_date"] == "2026-05-06"
    finally:
        await isolated.close()
        async with pool.connection() as conn:
            await conn.execute(f'drop schema "{schema}" cascade')
        await pool.close()
