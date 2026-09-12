import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from haike_contracts.snapshot import SessionSnapshot
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.sessions.snapshot import fold_timeline, rebuild_projection
from app.sessions.store import EventRecord, SessionNotFound


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


T0 = datetime(2026, 9, 12, 10, 0, 0, tzinfo=UTC)


def _recs(run_id: str, events: list[dict], start_seq: int = 1) -> list[EventRecord]:
    out = []
    for i, e in enumerate(events):
        seq = start_seq + i
        out.append(
            EventRecord(seq, run_id, T0 + timedelta(seconds=i), {**e, "seq": seq, "run_id": run_id})
        )
    return out


STEP = {
    "step_id": "s1",
    "plan_id": "p1",
    "plan_version": 1,
    "step_no": 1,
    "title": "重启",
    "instruction": "长按",
    "expected_result": "亮灯",
    "caution": None,
    "evidence_ids": ["e1"],
}


def test_fold_messages_tools_cards_and_pending():
    recs = _recs(
        "r1",
        [
            {"type": "run_started", "resumed": False, "deadline_ms": 25000},
            {"type": "progress", "stage": "intake"},
            {"type": "message_start", "message_id": "m1"},
            {"type": "message", "message_id": "m1", "delta": "别"},
            {"type": "message", "message_id": "m1", "delta": "担心"},
            {
                "type": "message_end",
                "message_id": "m1",
                "status": "aborted",
                "model_tier": "primary",
            },
            {"type": "message_start", "message_id": "m2", "replaces": "m1"},
            {"type": "message", "message_id": "m2", "delta": "我来帮您"},
            {
                "type": "message_end",
                "message_id": "m2",
                "status": "completed",
                "model_tier": "fallback",
            },
            {"type": "tool_call", "tool_id": "t1", "name": "knowledge.search", "status": "started"},
            {
                "type": "tool_call",
                "tool_id": "t1",
                "name": "knowledge.search",
                "status": "finished",
                "summary": "3 条",
            },
            {
                "type": "evidence",
                "items": [
                    {
                        "evidence_id": "e1",
                        "source": "kb",
                        "doc_id": "d",
                        "doc_version": "1",
                        "chunk_id": "c",
                        "snippet": "…",
                        "score": 0.5,
                        "status": "ok",
                    }
                ],
            },
            {
                "type": "product_card",
                "card_id": "pc1",
                "version": 2,
                "candidates": [
                    {
                        "sku": "A1",
                        "name": "充电器",
                        "category": "charger",
                        "image": None,
                        "in_scope": True,
                    }
                ],
            },
            {"type": "step_card", "card_id": "sc1", "version": 3, "step": STEP},
            {
                "type": "step_card",
                "card_id": "sc1",
                "version": 3,
                "step": STEP,
            },  # 重跑重发：按 card_id 幂等
            {
                "type": "receipt_card",
                "card_id": "rc1",
                "version": 4,
                "fields": {"order_no": "1"},
                "confidence": {"order_no": 0.9},
                "unreadable": [],
            },
            {
                "type": "awaiting_input",
                "kind": "step_feedback",
                "interrupt_id": "sc1",
                "card_id": "sc1",
                "version": 3,
            },
            {"type": "done", "reason": "awaiting_input", "version": 3},
        ],
    )
    values = {
        "messages": [
            {
                "role": "user",
                "text": "充不上电",
                "image_ids": ["img1"],
                "run_id": "r1",
                "at": "2026-09-12T09:59:00Z",
            }
        ],
        "card_results": {
            "pc1": {"selected_sku": "A1"},
            "sc1": {"feedback": "not_solved", "note": "还是不亮"},
            "rc1": {"skipped_reason": "later"},
        },
    }
    f = fold_timeline(recs, values)
    kinds = [i["kind"] for i in f["timeline"]]
    assert kinds == [
        "user_message",
        "assistant_message",
        "tool",
        "evidence",
        "product_card",
        "step_card",
        "receipt_card",
    ]
    um, am, tool, _ev, pc, sc, rc = f["timeline"]
    assert (
        um["text"] == "充不上电"
        and um["image_ids"] == ["img1"]
        and um["at"] == "2026-09-12T09:59:00Z"
    )
    # 被替换的 m1 消失，m2 合并为完整文本
    assert am["message_id"] == "m2" and am["text"] == "我来帮您" and am["status"] == "completed"
    assert am["model_tier"] == "fallback" and am["replaces"] == "m1"
    assert tool["status"] == "finished" and tool["summary"] == "3 条"
    assert pc["selected_sku"] == "A1"
    assert (
        sc["feedback"] == "not_solved"
        and sc["note"] == "还是不亮"
        and kinds.count("step_card") == 1
    )
    assert rc["skipped_reason"] == "later" and rc["confirmed_fields"] is None
    assert f["active_run"] is None
    assert f["pending_input"] == {
        "kind": "step_feedback",
        "interrupt_id": "sc1",
        "card_id": "sc1",
        "version": 3,
    }
    assert f["last_error"] is None and f["cancelled_run"] is None
    # 整体能过契约
    SessionSnapshot.model_validate({"session_id": "s", "version": 3, "stage": "guide", **f})


def test_fold_active_run_error_and_cancel():
    r1 = _recs(
        "r1",
        [
            {"type": "run_started", "resumed": False, "deadline_ms": 25000},
            {
                "type": "awaiting_input",
                "kind": "select_product",
                "interrupt_id": "c",
                "card_id": "c",
                "version": 1,
            },
            {"type": "done", "reason": "awaiting_input", "version": 1},
        ],
    )
    r2 = _recs(
        "r2",
        [
            {"type": "run_started", "resumed": False, "deadline_ms": 40000},
            {
                "type": "error",
                "code": "model_unavailable",
                "message": "x",
                "recoverable": True,
                "retry_with_same_action": False,
            },
            {"type": "done", "reason": "cancelled", "version": 2},
        ],
        start_seq=4,
    )
    r3 = _recs("r3", [{"type": "run_started", "resumed": True, "deadline_ms": 30000}], start_seq=7)

    f = fold_timeline(r1 + r2, {})
    assert f["last_error"] == {"code": "model_unavailable", "at": "2026-09-12T10:00:01Z"}
    assert f["cancelled_run"] == {"run_id": "r2", "at": "2026-09-12T10:00:02Z"}
    # 取消后 pending_input 保持取消前的值（08 §7）
    assert f["pending_input"]["kind"] == "select_product"
    assert f["active_run"] is None

    f = fold_timeline(r1 + r2 + r3, {})
    assert f["active_run"] == {
        "run_id": "r3",
        "started_at": "2026-09-12T10:00:00Z",
        "deadline_at": "2026-09-12T10:00:30Z",
    }
    assert f["pending_input"] is None  # 有 active run 时不给 pending


async def test_get_snapshot_idle_after_turn(mem_runtime):
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        empty = await client.get(f"/sessions/{sid}")
        assert empty.status_code == 200
        assert empty.json() == {
            "session_id": sid,
            "version": 0,
            "stage": "intake",
            "substage": None,
            "active_run": None,
            "pending_input": None,
            "timeline": [],
            "last_error": None,
            "cancelled_run": None,
        }
        await client.post(f"/sessions/{sid}/messages", data={"text": "充不上电"})
        resp = await client.get(f"/sessions/{sid}")
    snap = SessionSnapshot.model_validate(resp.json())
    assert snap.version == 3 and snap.stage == "diagnose"
    assert snap.active_run is None and snap.pending_input is None and snap.last_error is None
    assert [i.kind for i in snap.timeline] == ["user_message"]
    assert snap.timeline[0].text == "充不上电"
    # 投影行与快照一致（业务逻辑不读投影，但两者必须相等）
    row = await mem_runtime.get_session(sid)
    assert (row.version, row.stage) == (snap.version, snap.stage)


async def test_get_snapshot_during_active_run_and_409_body(mem_runtime, monkeypatch):
    monkeypatch.setenv("PLACEHOLDER_NODE_DELAY_S", "0.5")
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        task = asyncio.create_task(client.post(f"/sessions/{sid}/messages", data={"text": "a"}))
        for _ in range(50):
            await asyncio.sleep(0.01)
            if (await mem_runtime.get_session(sid)).active_run_id:
                break
        snap = SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())
        assert snap.active_run is not None
        started = datetime.fromisoformat(snap.active_run.started_at)
        deadline = datetime.fromisoformat(snap.active_run.deadline_at)
        assert deadline - started == timedelta(seconds=25)
        conflict = await client.post(f"/sessions/{sid}/messages", data={"text": "b"})
        assert conflict.status_code == 409
        body = conflict.json()
        assert body["code"] == "run_active"
        assert (
            SessionSnapshot.model_validate(body["snapshot"]).active_run.run_id
            == snap.active_run.run_id
        )
        await task
        final = SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())
    assert final.active_run is None and final.version == 3


async def test_get_snapshot_after_error_run(mem_runtime):
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await client.post(f"/sessions/{sid}/messages", data={"text": "__raise__"})
        snap = SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())
    assert snap.last_error is not None and snap.last_error.code == "node_failed"
    assert snap.active_run is None
    # 失败 run 只写了输入 checkpoint：version 1
    assert snap.version == 1 and snap.stage == "intake"


async def test_delete_projection_then_rebuild_matches(mem_runtime):
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await client.post(f"/sessions/{sid}/messages", data={"text": "第一句"})
        await client.post(f"/sessions/{sid}/messages", data={"text": "第二句"})
        before = (await client.get(f"/sessions/{sid}")).json()
        before_row = await mem_runtime.get_session(sid)

        await mem_runtime.delete_projection(sid)
        # 投影没了，快照照常可读（不依赖投影表）
        during = (await client.get(f"/sessions/{sid}")).json()
        assert during == before
        with pytest.raises(SessionNotFound):
            await mem_runtime.get_session(sid)

        await rebuild_projection(mem_runtime, app.state.session_graph, sid)
        after = (await client.get(f"/sessions/{sid}")).json()
    assert after == before
    row = await mem_runtime.get_session(sid)
    assert (row.version, row.stage, row.active_run_id, row.pending_input) == (
        before_row.version,
        before_row.stage,
        None,
        None,
    )
    assert row.version == 7 and [i["kind"] for i in after["timeline"]] == [
        "user_message",
        "user_message",
    ]


async def test_get_snapshot_unknown_404(mem_runtime):
    async with _client() as client:
        assert (await client.get("/sessions/nope")).status_code == 404
