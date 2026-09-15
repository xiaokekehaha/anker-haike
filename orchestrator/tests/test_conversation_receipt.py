"""Receipt work remains conversational and uses the same input/issue ledger."""
from uuid import uuid4

from app.images.runtime import set_image_store
from app.images.store import InMemoryImageStore
from tests.conversation_runtime import REPORT, REPORT_TEXT
from tests.conversation_runtime import conversation as conversation  # noqa: PLC0414


async def action(c, kind, payload):
    snapshot = await c.snapshot()
    pending = snapshot["pending_input"]
    return c.check(await c.client.post(f"/sessions/{c.sid}/actions", json={
        "action_id": uuid4().hex, "expected_version": snapshot["version"], "kind": kind,
        "target_issue_id": snapshot["active_issue_id"], "card_id": pending["card_id"],
        "input_token": pending["input_token"], "payload": payload}))


async def reach_receipt(c):
    await c.send(REPORT_TEXT + "，我想申请换货", {**REPORT, "primary_intent": "replacement_request"})
    for _ in range(5):
        snapshot = await c.snapshot()
        if snapshot["pending_input"]["kind"] == "upload_receipt":
            return snapshot
        await action(c, "step_feedback", {"feedback": "not_solved"})
    raise AssertionError("diagnostic limit should lead to receipt collection")


async def test_question_during_receipt_keeps_pending_then_skip(conversation):
    c = conversation
    before = await reach_receipt(c)
    await c.send("为什么需要凭证", {"primary_intent": "explain", "device_relation": "current"})
    after = await c.snapshot()
    assert after["pending_input"]["card_id"] == before["pending_input"]["card_id"]
    await action(c, "skip_receipt", {"reason": "later"})
    final = await c.snapshot()
    assert final["pending_input"] is None
    summary = final["latest_summaries"][0]
    assert summary["handoff_status"] == "prepared"
    assert summary["summary"]["receipt"]["status"] == "not_collected"


async def test_replacing_photo_keeps_old_card_and_confirms_only_new_fields(conversation):
    c = conversation
    images = InMemoryImageStore()
    set_image_store(images)
    try:
        await reach_receipt(c)
        cards = []
        for i in (1, 2):
            c.models["intake"].script.append({"primary_intent": "supplement", "device_relation": "current"})
            c.models["warranty.receipt_ocr"].script.append({"order_no": f"TEST-{i}", "channel": "京东",
                "purchase_date": "2026-09-01", "confidence": {"order_no": 0.9, "channel": 0.9, "purchase_date": 0.9}})
            snap = await c.snapshot()
            output = c.check(await c.client.post(f"/sessions/{c.sid}/messages", data={
                "input_id": f"photo-{i}", "expected_version": snap["version"], "purpose": "receipt"},
                files={"images": ("receipt.png", b"\x89PNG\r\n\x1a\n" + bytes([i]), "image/png")}))
            cards.append(next(e for e in output if e["type"] == "receipt_card"))
        assert cards[0]["card_id"] != cards[1]["card_id"]
        state = await c.state()
        assert len(state["receipt"]["image_ids"]) == 1
        assert state["receipt"]["fields"]["order_no"] == "TEST-2"
        before = await c.snapshot()
        historical = [item for item in before["timeline"] if item["kind"] == "receipt_card"]
        assert [item["fields"]["order_no"] for item in historical] == ["TEST-1", "TEST-2"]
        photos = [item for item in before["timeline"] if item["kind"] == "user_message" and item["images"]]
        assert len(photos) == 2 and photos[0]["images"][0]["purpose"] == "receipt"
        await action(c, "confirm_receipt", {"fields": cards[1]["fields"], "edited": []})
        assert (await c.snapshot())["pending_input"] is None
    finally:
        set_image_store(None)
