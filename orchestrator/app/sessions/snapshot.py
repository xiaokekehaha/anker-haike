"""会话快照（08 §6）：由 checkpoint（权威业务状态）与 session_events（事件日志）派生。

不读 sessions 投影表——投影表反过来由 rebuild_projection 用本模块结果重建。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from haike_contracts.snapshot import SessionSnapshot
from langgraph.graph.state import CompiledStateGraph

from app.sessions.store import EventRecord, SessionStore

log = logging.getLogger("sessions.snapshot")


async def build_snapshot(
    store: SessionStore, graph: CompiledStateGraph, session_id: str
) -> SessionSnapshot:
    records = await store.list_event_records(session_id)
    state = await graph.aget_state({"configurable": {"thread_id": session_id}})
    values: dict[str, Any] = state.values or {}
    version = int(state.metadata.get("step", -1)) + 1 if state.metadata else 0

    folded = fold_timeline(records, values)
    # pending_input 以 checkpoint 里仍挂起的 interrupt 为准（08 §2 权威来源）：动作 run 出错 / 取消后
    # 事件日志的最后一个 run 不是 awaiting_input，但图仍停在 await_input，用户仍可（重试）响应（票 23）
    if folded["active_run"] is None:
        pending_from_ckpt = _pending_from_interrupts(state, version)
        if pending_from_ckpt is not None:
            folded["pending_input"] = pending_from_ckpt
        elif action_pending_apply(state) is not None:
            # 动作已被 await_input 接收、apply_action 尚未成功（run 出错 / 取消）：不再等待用户输入，
            # 前端按 error.retry_with_same_action 复用 action_id 重试即可继续
            folded["pending_input"] = None
    last_progress = next(
        (r.event["stage"] for r in reversed(records) if r.event["type"] == "progress"), None
    )
    stage = values.get("stage") or last_progress or "intake"

    return SessionSnapshot.model_validate(
        {
            "session_id": session_id,
            "version": version,
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
    user_msgs = {m.get("run_id"): m for m in values.get("messages", []) if m.get("role") == "user"}
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
        run = runs.setdefault(r.run_id, {"started_at": None, "deadline_ms": None, "done": None})
        if t == "run_started":
            if r.run_id not in run_order:
                run_order.append(r.run_id)
            run["started_at"] = r.created_at
            run["deadline_ms"] = e["deadline_ms"]
            um = user_msgs.get(r.run_id)
            if um:
                put(
                    "user_message",
                    r.run_id,
                    {
                        "kind": "user_message",
                        "id": f"u-{r.run_id}",
                        "text": um.get("text", ""),
                        "image_ids": list(um.get("image_ids") or []),
                        "images": list(um.get("images") or []),  # 票 29：purpose / sha256 随快照
                        "at": um.get("at") or _iso(r.created_at),
                    },
                )
        elif t == "message_start":
            if e.get("replaces"):
                old = index.pop(("assistant_message", e["replaces"]), None)
                if old is not None and old in timeline:
                    timeline.remove(old)
            put(
                "assistant_message",
                e["message_id"],
                {
                    "kind": "assistant_message",
                    "message_id": e["message_id"],
                    "text": "",
                    "status": "streaming",
                    "model_tier": None,
                    "replaces": e.get("replaces"),
                },
            )
        elif t == "message":
            item = index.get(("assistant_message", e["message_id"]))
            if item is None:
                put("assistant_message", e["message_id"], _msg_stub(e["message_id"]))
                item = index[("assistant_message", e["message_id"])]
            item["text"] += e["delta"]
        elif t == "message_end":
            item = index.get(("assistant_message", e["message_id"]))
            if item is None:
                put("assistant_message", e["message_id"], _msg_stub(e["message_id"]))
                item = index[("assistant_message", e["message_id"])]
            item["status"] = e["status"]
            item["model_tier"] = e.get("model_tier")
        elif t == "tool_call":
            put(
                "tool",
                e["tool_id"],
                {
                    "kind": "tool",
                    "tool_id": e["tool_id"],
                    "name": e["name"],
                    "status": e["status"],
                    "summary": e.get("summary"),
                },
            )
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
        elif t == "evidence":
            timeline.append({"kind": "evidence", "items": e["items"]})
        elif t == "escalation_summary":
            put(
                "escalation_summary",
                e["card_id"],
                {"kind": "escalation_summary", "card_id": e["card_id"], "summary": e["summary"]},
            )
        elif t == "awaiting_input":
            run["awaiting"] = {
                "kind": e["kind"],
                "interrupt_id": e["interrupt_id"],
                "card_id": e["card_id"],
                "version": e["version"],
            }
        elif t == "error":
            last_error = {"code": e["code"], "at": _iso(r.created_at)}
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
        if last["done"] == "cancelled" and not last.get("awaiting"):
            # 被取消的 run 没有发过 awaiting_input：沿用更早 run 的 pending（若有）
            for rid in reversed(run_order[:-1]):
                if runs[rid]["done"] == "awaiting_input" and runs[rid].get("awaiting"):
                    pending_input = runs[rid]["awaiting"]
                    break

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
    """用快照结果重写 sessions 投影行（票 07 验收项 3）。"""
    snap = await build_snapshot(store, graph, session_id)
    await store.upsert_projection(
        session_id,
        version=snap.version,
        stage=snap.stage,
        active_run_id=snap.active_run.run_id if snap.active_run else None,
        pending_input=snap.pending_input.model_dump() if snap.pending_input else None,
    )
    return snap


def action_pending_apply(state: Any) -> str | None:
    """图停在 apply_action 之前且状态里带着已接收的动作 → 返回其 action_id，否则 None（票 23）。"""
    if "apply_action" not in (getattr(state, "next", ()) or ()):
        return None
    if _pending_from_interrupts(state, 0) is not None:
        return None
    last = (getattr(state, "values", None) or {}).get("last_action") or {}
    return last.get("action_id") or None


def _pending_from_interrupts(state: Any, version: int) -> dict[str, Any] | None:
    for task in getattr(state, "tasks", ()) or ():
        for intr in getattr(task, "interrupts", ()) or ():
            value = getattr(intr, "value", None)
            if isinstance(value, dict) and {"kind", "card_id"} <= set(value):
                return {
                    "kind": value["kind"],
                    "interrupt_id": value.get("interrupt_id", value["card_id"]),
                    "card_id": value["card_id"],
                    "version": version,
                }
    return None


def _msg_stub(message_id: str) -> dict[str, Any]:
    return {
        "kind": "assistant_message",
        "message_id": message_id,
        "text": "",
        "status": "streaming",
        "model_tier": None,
        "replaces": None,
    }


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")
