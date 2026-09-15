"""会话快照（08 §6）：由 checkpoint（权威业务状态）与 session_events（事件日志）派生。

sessions 固定已发布 checkpoint 与事件水位，历史问答统一由 fold_history 折叠。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from haike_contracts.snapshot import SessionSnapshot
from langgraph.graph.state import CompiledStateGraph

from app.conversation.history import fold_history
from app.sessions.store import EventRecord, SessionNotFound, SessionStore

log = logging.getLogger("sessions.snapshot")


class SnapshotRecovering(RuntimeError):
    pass


async def build_snapshot(
    store: SessionStore, graph: CompiledStateGraph, session_id: str
) -> SessionSnapshot:
    try:
        await store.get_session(session_id)
    except SessionNotFound:
        return await rebuild_projection(store, graph, session_id)
    async with store.snapshot_view(session_id) as (row, records):
        if row.active_run_id and any(
            r.run_id == row.active_run_id and r.event.get("type") == "state_committed"
            for r in records
        ):
            raise SnapshotRecovering("committed output is still publishing")
        if row.published_checkpoint_id:
            state = await graph.aget_state(
                {
                    "configurable": {
                        "thread_id": session_id,
                        "checkpoint_id": row.published_checkpoint_id,
                    }
                }
            )
            values: dict[str, Any] = state.values or {}
        else:
            values = {}
    version = row.version

    folded = fold_timeline(records, values)
    pending = values.get("pending_card")
    folded["pending_input"] = (
        {
            "kind": pending["kind"],
            "card_id": pending["card_id"],
            "issue_id": values.get("active_issue_id"),
            "input_token": pending.get("input_token") or pending["card_id"],
            "version": version,
        }
        if pending
        else None
    )
    last_progress = next(
        (r.event["stage"] for r in reversed(records) if r.event["type"] == "progress"), None
    )
    stage = values.get("stage") or last_progress or "intake"

    return SessionSnapshot.model_validate(
        {
            "session_id": session_id,
            "version": version,
            "active_issue_id": values.get("active_issue_id"),
            "issues": [
                {
                    "issue_id": k,
                    "status": v.get("status", "open"),
                    "title": v.get("title", "新问题"),
                    "task_queue": v.get("task_queue", []),
                }
                for k, v in (values.get("issues") or {}).items()
            ],
            "last_event_seq": max((r.seq for r in records), default=0),
            "latest_summaries": [
                dict(kind="escalation_summary", **i["latest_summary"])
                for i in (values.get("issues") or {}).values()
                if i.get("latest_summary")
            ],
            "stage": stage,
            "substage": values.get("substage"),
            "active_run": folded["active_run"],
            "pending_input": folded["pending_input"],
            "timeline": folded["timeline"],
            "last_error": folded["last_error"],
            "cancelled_run": folded["cancelled_run"],
        }
    )


def fold_timeline(records: list[EventRecord], values: dict[str, Any]) -> dict[str, Any]:
    """按 seq 重放：消息合并为完整文本、卡片带用户已选结果、工具行保留（票 07 验收项 2）。"""
    card_results: dict[str, dict[str, Any]] = values.get("card_results") or {}

    timeline: list[dict[str, Any]] = []
    index: dict[tuple[str, str], dict[str, Any]] = {}  # (kind, id) -> item，供原地更新
    runs: dict[str, dict[str, Any]] = {}  # run_id -> {started_at, deadline_ms, done, awaiting}
    run_order: list[str] = []
    last_error = None
    cancelled_run = None

    def put(kind: str, key: str, item: dict[str, Any]) -> None:
        k = (kind, key)
        if k in index:
            index[k].update(item)
        else:
            index[k] = item
            timeline.append(item)

    for r in records:
        e = r.event
        t = e["type"]
        run = runs.setdefault(
            r.run_id, {"started_at": None, "deadline_ms": None, "done": None, "error": None}
        )
        if t == "run_started":
            if r.run_id not in run_order:
                run_order.append(r.run_id)
            run["started_at"] = r.created_at
            run["deadline_ms"] = e["deadline_ms"]
        elif t == "product_card":
            res = card_results.get(e["card_id"], {})
            put(
                "product_card",
                e["card_id"],
                {
                    "kind": "product_card",
                    "card_id": e["card_id"],
                    "version": e["version"],
                    "candidates": e["candidates"],
                    "selected_sku": res.get("selected_sku"),
                },
            )
        elif t == "step_card":
            res = card_results.get(e["card_id"], {})
            put(
                "step_card",
                e["card_id"],
                {
                    "kind": "step_card",
                    "card_id": e["card_id"],
                    "version": e["version"],
                    "step": e["step"],
                    "feedback": res.get("feedback"),
                    "note": res.get("note"),
                },
            )
        elif t == "receipt_card":
            res = card_results.get(e["card_id"], {})
            put(
                "receipt_card",
                e["card_id"],
                {
                    "kind": "receipt_card",
                    "card_id": e["card_id"],
                    "version": e["version"],
                    "fields": e["fields"],
                    "confidence": e.get("confidence", {}),
                    "unreadable": e.get("unreadable", []),
                    "confirmed_fields": res.get("confirmed_fields"),
                    "skipped_reason": res.get("skipped_reason"),
                },
            )
        elif t in {"context_card", "proposal_card", "execution_card", "retake_card", "rating_card", "case_changed"}:
            item = {k: v for k, v in e.items() if k not in {"type", "seq", "run_id", "event_id", "recorded_at"}}
            item.update(kind=t, at=_iso(r.created_at), first_seq=r.seq, last_seq=r.seq)
            item.update(card_results.get(e["card_id"], {}))
            put(t, e["card_id"], item)
        elif t == "evidence":
            timeline.append(
                {
                    "kind": "evidence",
                    "items": e["items"],
                    "at": _iso(r.created_at),
                    "first_seq": r.seq,
                    "last_seq": r.seq,
                }
            )
        elif t == "escalation_summary":
            put(
                "escalation_summary",
                e["card_id"],
                {
                    "kind": "escalation_summary",
                    **{
                        k: v
                        for k, v in e.items()
                        if k not in {"type", "seq", "run_id", "event_id", "recorded_at"}
                    },
                },
            )
        elif t == "awaiting_input":
            run["awaiting"] = {
                "kind": e["kind"],
                "input_token": e["input_token"],
                "card_id": e["card_id"],
                "version": e["version"],
            }
        elif t == "error":
            # 错误挂在所属 run 上，不再直接写全局 last_error（否则历史错误会一直随快照复活）
            run["error"] = {
                "code": e["code"],
                "message": e.get("message", ""),
                "recoverable": bool(e.get("recoverable", True)),
                "at": _iso(r.created_at),
            }
        elif t == "done":
            run["done"] = e["reason"]
            if e["reason"] == "cancelled":
                cancelled_run = {"run_id": r.run_id, "at": _iso(r.created_at)}
        # progress / ping 不进 timeline

    active_run = None
    pending_input = None
    if run_order:
        last_id = run_order[-1]
        last = runs[last_id]
        if last["done"] is None and last["started_at"] is not None:
            active_run = {
                "run_id": last_id,
                "started_at": _iso(last["started_at"]),
                "deadline_at": _iso(
                    last["started_at"] + timedelta(milliseconds=last["deadline_ms"])
                ),
            }
        elif last["done"] in ("awaiting_input", "cancelled") and last.get("awaiting"):
            # 取消后 pending_input 保持取消前的值（08 §7）
            pending_input = last["awaiting"]
        # last_error 只代表最近一次运行：更早 run 的错误留在事件表供审计，不再当成当前错误
        last_error = last["error"]
        if last["done"] == "cancelled" and not last.get("awaiting"):
            # 被取消的 run 没有发过 awaiting_input：沿用更早 run 的 pending（若有）
            for rid in reversed(run_order[:-1]):
                if runs[rid]["done"] == "awaiting_input" and runs[rid].get("awaiting"):
                    pending_input = runs[rid]["awaiting"]
                    break

    history = fold_history("", records)
    timeline = [
        item
        for item in timeline
        if item["kind"] not in {"user_message", "assistant_message", "tool"}
    ]
    for entry in history:
        common = {
            "at": entry.received_at or entry.started_at or entry.recorded_at,
            "first_seq": entry.first_seq,
            "last_seq": entry.last_seq,
            "issue_id": entry.issue_id,
        }
        if entry.kind == "message" and entry.role == "user":
            timeline.append(
                dict(
                    common,
                    kind="user_message",
                    id=entry.entry_id,
                    text=entry.text,
                    image_ids=entry.attachments,
                    images=[
                        {k: ref[k] for k in ("image_id", "purpose", "sha256", "mime", "size")}
                        for ref in entry.payload.get("images", [])
                    ],
                )
            )
        elif entry.kind == "message" and entry.role == "assistant":
            timeline.append(
                dict(
                    common,
                    kind="assistant_message",
                    message_id=entry.entry_id,
                    text=entry.text,
                    status=entry.status,
                    reply_to_input_id=entry.reply_to_input_id,
                    model_tier=entry.payload.get("model_tier"),
                    replaces=entry.references[0] if entry.references else None,
                )
            )
        elif entry.kind == "action":
            timeline.append(
                dict(
                    common,
                    kind="action",
                    id=entry.entry_id,
                    label=entry.text,
                    action_kind=entry.payload.get("kind", "unknown"),
                )
            )
        elif entry.kind == "tool":
            timeline.append(
                dict(
                    common,
                    kind="tool",
                    tool_id=entry.entry_id,
                    name=entry.payload.get("name", "tool"),
                    summary=entry.text,
                    status={"completed": "finished", "streaming": "started"}.get(
                        entry.status, "failed"
                    ),
                )
            )
        elif entry.kind == "card":
            for item in timeline:
                if item.get("card_id") == entry.entry_id:
                    item.update(common)
    timeline.sort(key=lambda item: item.get("first_seq", 0))

    return {
        "timeline": timeline,
        "active_run": active_run,
        "pending_input": pending_input,
        "last_error": last_error,
        "cancelled_run": cancelled_run,
    }


async def rebuild_projection(
    store: SessionStore, graph: CompiledStateGraph, session_id: str
) -> SessionSnapshot:
    """Restore the published pointer from commit events, never the newest candidate."""
    records = await store.list_event_records(session_id)
    if not records:
        raise SessionNotFound(session_id)
    committed = next(
        (r.event for r in reversed(records) if r.event.get("type") == "state_committed"), {}
    )
    pointer = committed.get("checkpoint_id")
    values = {}
    if pointer:
        state = await graph.aget_state(
            {"configurable": {"thread_id": session_id, "checkpoint_id": pointer}}
        )
        values = state.values or {}
    folded = fold_timeline(records, values)
    await store.upsert_projection(
        session_id,
        version=committed.get("version", 0),
        stage=values.get("stage", "intake"),
        active_run_id=(folded.get("active_run") or {}).get("run_id"),
        pending_input=None,
        published_checkpoint_id=pointer,
    )
    return await build_snapshot(store, graph, session_id)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")
