"""一次 run 的事件流：run_started → (progress | ping)* → done；异常路径 error → done(error)；
取消路径（票 38，08 §7）：cancel_event 置位 → 取消图任务 → done(cancelled)，状态回到上一个 checkpoint。

每条事件先 append 到 session_events 拿到 seq，再交给调用方发送（08 §2、§5）。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from haike_contracts.events import parse_event
from langgraph.graph.state import CompiledStateGraph

from app.analytics.trace import RunTrace
from app.observability.runtime import record, run_id_context
from app.sessions.store import SessionStore

log = logging.getLogger("sessions.runner")

DEFAULT_DEADLINE_MS = 25_000  # 文本轮（08 §8）
PING_INTERVAL_S = 5.0

_GRAPH_DONE = object()
_CANCELLED = object()


class RunEmitter:
    """把载荷补上 seq / run_id，校验为契约事件并落库。"""

    def __init__(self, store: SessionStore, session_id: str, run_id: str) -> None:
        self._store = store
        self.session_id = session_id
        self.run_id = run_id
        self.last_seq = 0
        self.started = time.monotonic()
        self.metrics: set[str] = set()
        self.stage = None
        self.stage_started_ms = 0
        # 管理员观测台：run 事实要用的两个延迟与错误码（与 run_metric 同一口径，不另算）
        self.metric_values: dict[str, int] = {}
        self.card_kind: str | None = None
        self.first_stage: str | None = None
        self.last_error_code: str | None = None
        self.input_id: str | None = None
        self.issue_id: str | None = None
        self.message_aliases: dict[str, str] = {}

    async def emit(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload = dict(payload)
        if payload.get("event_id"):
            previous = next(
                (
                    e
                    for e in await self._store.list_events(self.session_id)
                    if e.get("event_id") == payload["event_id"]
                ),
                None,
            )
            if previous:
                metadata = {"seq", "run_id", "event_id", "recorded_at"}
                expected = {k: v for k, v in payload.items() if k not in metadata}
                actual = {k: v for k, v in previous.items() if k not in metadata}
                if expected != actual:
                    raise RuntimeError("event_id_payload_conflict")
                self.last_seq = max(self.last_seq, previous["seq"])
                return previous
        if payload.get("type") == "message_start":
            old_id = payload["message_id"]
            old = next(
                (
                    e
                    for e in await self._store.list_events(self.session_id)
                    if e.get("type") == "message_start" and e.get("message_id") == old_id
                ),
                None,
            )
            if old:
                self.message_aliases[old_id] = uuid.uuid4().hex
                payload["replaces"] = old_id
        if payload.get("message_id") in self.message_aliases:
            payload["message_id"] = self.message_aliases[payload["message_id"]]
        # seq 由存储层分配；先用占位值过一遍校验，落库后回填真实 seq 再校验一次
        draft = {
            **payload,
            "run_id": self.run_id,
            "seq": self.last_seq + 1,
            "event_id": payload.get("event_id") or uuid.uuid4().hex,
            "recorded_at": datetime.now(UTC).isoformat(),
        }
        if draft.get("type") == "message_start":
            draft.setdefault("reply_to_input_id", self.input_id)
            draft.setdefault("issue_id", self.issue_id)
        parse_event(draft)
        seq = await self._store.append_event(self.session_id, self.run_id, draft)
        if seq != draft["seq"]:
            draft["seq"] = seq
            parse_event(draft)
            # 存储层给出的 seq 与本地计数不一致：只可能在旧事件残留时出现，纠正后继续
            log.debug(
                "seq realigned session=%s expected=%s got=%s",
                self.session_id,
                self.last_seq + 1,
                seq,
            )
        self.last_seq = seq
        elapsed = int((time.monotonic() - self.started) * 1000)
        kind = draft["type"]
        if kind == "error":
            self.last_error_code = draft.get("code")
        if kind == "progress":
            if self.first_stage is None:
                self.first_stage = self.stage
            record(
                "state_transition",
                session_id=self.session_id,
                run_id=self.run_id,
                from_stage=self.stage,
                to_stage=draft["stage"],
                substage=draft.get("substage"),
                latency_ms=elapsed - self.stage_started_ms,
                run_elapsed_ms=elapsed,
            )
            self.stage = draft["stage"]
            self.stage_started_ms = elapsed
        elif kind in {"tool_call", "evidence", "escalation_summary", "error", "done"}:
            record("session_event", session_id=self.session_id, run_id=self.run_id, payload=draft)
        metric = None
        if kind == "message" and draft.get("delta", "").strip():
            metric = "first_visible_ms"
        elif kind in {"step_card", "product_card", "receipt_card"}:
            metric = "card_ready_ms"
        if metric and metric not in self.metrics:
            self.metrics.add(metric)
            self.metric_values[metric] = elapsed
            if metric == "card_ready_ms":
                self.card_kind = kind
            record(
                "run_metric",
                session_id=self.session_id,
                run_id=self.run_id,
                metric=metric,
                value_ms=elapsed,
                card_kind=kind if kind.endswith("_card") else None,
            )
        return draft


async def run_message(
    store: SessionStore,
    graph: CompiledStateGraph,
    session_id: str,
    text: str | None = None,
    *,
    receipt: dict[str, Any] | None = None,
    entry_action: dict[str, Any] | None = None,
    image_ids: list[str] | None = None,
    deadline_ms: int = DEFAULT_DEADLINE_MS,
    ping_interval_s: float | None = None,
    cancel_event: asyncio.Event | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """每个已接收输入运行一轮；提交后恢复只交付已保存结果，不重跑业务。"""
    if receipt is None:
        row = await store.get_session(session_id)
        source = entry_action or {
            "kind": "message",
            "text": text or "",
            "image_ids": image_ids or [],
        }
        iid = source.get("action_id") or uuid.uuid4().hex
        receipt, _ = await store.reserve_input(
            session_id, iid, source, expected_version=row.version, deadline_ms=deadline_ms
        )
    run_id = receipt["run_id"]
    if ping_interval_s is None:
        ping_interval_s = PING_INTERVAL_S  # 运行时读取，便于测试覆写
    row = await store.get_session(session_id)
    em = RunEmitter(store, session_id, run_id)
    # 存储层可能已有历史事件（多轮对话），seq 需接着排
    prior = await store.list_events(session_id)
    input_event = next(
        e for e in prior if e["type"] == "input_received" and e["input_id"] == receipt["input_id"]
    )
    source = input_event["payload"]
    em.input_id = receipt["input_id"]
    em.issue_id = source.get("target_issue_id")
    em.last_seq = max((e["seq"] for e in prior), default=0)
    trace = RunTrace(
        session_id,
        run_id,
        entry="message" if source.get("kind") == "message" else f"action:{source.get('kind')}",
        seq_no=len({e["run_id"] for e in prior}),
    )

    queue: asyncio.Queue[Any] = asyncio.Queue()
    started = time.monotonic()
    stage: str | None = None
    reason = "completed"
    is_action = source.get("kind") != "message"

    async def pump() -> None:
        context_token = run_id_context.set(run_id)
        try:
            config = {"configurable": {"thread_id": session_id}}
            payload: Any
            if is_action:
                # 明确动作与自然语言共用 START → understand 入口。
                payload = {
                    "session_id": session_id,
                    "run_id": run_id,
                    "at": receipt["received_at"],
                    "entry": "action",
                    "last_action": source,
                }
            else:
                payload = {
                    "session_id": session_id,
                    "run_id": run_id,
                    "at": receipt["received_at"],
                    "entry": "message",
                    "text": source.get("text") or "",
                    "image_ids": source.get("image_ids") or [],
                }
            from app.conversation.history import fold_history

            payload.update(
                input_id=receipt["input_id"],
                input_seq=input_event["seq"],
                base_version=receipt["base_version"],
                pending_effects=[],
                history=[
                    e.as_dict()
                    for e in fold_history(session_id, await store.list_event_records(session_id))
                ],
                target_issue_id=source.get("target_issue_id"),
            )
            checkpoint = await graph.aget_state(config)
            already_committed = (checkpoint.values or {}).get("committed_input_id") == receipt[
                "input_id"
            ]
            if already_committed:
                await queue.put(_GRAPH_DONE)
                return
            if receipt.get("base_checkpoint_id"):
                config["configurable"]["checkpoint_id"] = receipt["base_checkpoint_id"]
                base_state = await graph.aget_state(config)
                from app.conversation.summary_cache import read_summary

                payload["history_summary"] = await read_summary(
                    store,
                    session_id,
                    (base_state.values or {}).get("context_revision", 0),
                    input_event["seq"],
                )
            elif checkpoint.values:
                # No published business state exists; discard only uncommitted checkpoint candidates.
                await graph.checkpointer.adelete_thread(session_id)
            async for mode, chunk in graph.astream(
                payload, config, stream_mode=["custom", "updates"]
            ):
                await queue.put((mode, chunk))
            await queue.put(_GRAPH_DONE)
        except Exception as exc:  # noqa: BLE001 - 任何节点异常都要转为 error 事件
            await queue.put(exc)
        finally:
            run_id_context.reset(context_token)

    async def watch_cancel() -> None:
        assert cancel_event is not None
        await cancel_event.wait()
        await queue.put(_CANCELLED)

    task = asyncio.create_task(pump())
    watcher = asyncio.create_task(watch_cancel()) if cancel_event is not None else None
    try:
        yield next(e for e in prior if e["run_id"] == run_id and e["type"] == "run_started")
        yield input_event
        while True:
            remaining = deadline_ms / 1000 - (time.monotonic() - started)
            if remaining <= 0:
                task.cancel()
                reason = "error"
                yield await em.emit(
                    _error(
                        "deadline_exceeded",
                        "run exceeded deadline",
                        recoverable=True,
                        retry=False,
                    )
                )
                break
            try:
                item = await asyncio.wait_for(queue.get(), timeout=min(ping_interval_s, remaining))
            except TimeoutError:
                yield await em.emit({"type": "ping"})
                continue
            if item is _GRAPH_DONE:
                break
            if item is _CANCELLED:
                # 取消：中止当前节点（其中的模型调用随之中止），状态停在上一个 checkpoint
                task.cancel()
                reason = "cancelled"
                log.info("run cancelled session=%s run=%s", session_id, run_id)
                break
            if isinstance(item, Exception):
                reason = "error"
                log.exception("graph failed session=%s run=%s", session_id, run_id, exc_info=item)
                # 本次输入保留失败回执；同 ID 只重放，继续处理使用新的输入。
                yield await em.emit(
                    _error(
                        "node_failed",
                        f"{type(item).__name__}: {item}"[:300],
                        recoverable=is_action,
                        retry=False,
                    )
                )
                break
            mode, chunk = item
            if mode == "custom" and isinstance(chunk, dict) and chunk.get("type") == "progress":
                stage = chunk.get("stage", stage)
                yield await em.emit(
                    {"type": "progress", "stage": chunk["stage"], "substage": chunk.get("substage")}
                )
            elif mode == "custom" and isinstance(chunk, dict) and "type" in chunk:
                # 后续票的卡片 / tool_call 等事件在此透传，契约校验兜底
                yield await em.emit(chunk)
            # updates 模式：状态迁移日志，票 07 用于 version 递增；此处仅记录
            elif mode == "updates":
                trace.on_updates(chunk)
                log.debug(
                    "update session=%s run=%s %s",
                    session_id,
                    run_id,
                    list(chunk)[:3] if isinstance(chunk, dict) else chunk,
                )
    finally:
        if not task.done():
            task.cancel()
        if watcher is not None and not watcher.done():
            watcher.cancel()
        # 等图任务真正退出，保证 done 落库时 checkpoint 已定稿
        if task.cancelling() or task.cancelled():
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        final_state = await checkpoint_state(graph, session_id)
        values = final_state.values if final_state else {}
        if (values or {}).get("committed_input_id") == receipt["input_id"]:
            version = await store.publish_commit(
                receipt,
                final_state.config["configurable"]["checkpoint_id"],
                (values or {}).get("stage", "intake"),
                (values or {}).get("turn_decision") or {},
            )
            for effect in (values or {}).get("pending_effects") or []:
                yield await em.emit({**effect["payload"], "event_id": effect["effect_id"]})
        else:
            version = receipt["base_version"]
            published = await store.get_session(session_id)
            if published.published_checkpoint_id:
                final_state = await graph.aget_state(
                    {
                        "configurable": {
                            "thread_id": session_id,
                            "checkpoint_id": published.published_checkpoint_id,
                        }
                    }
                )
                values = final_state.values or {}
            else:
                values = {}
                final_state = None
        pending = (values or {}).get("pending_card")
        if reason == "completed" and pending:
            reason = "awaiting_input"
            yield await em.emit(
                {
                    "type": "awaiting_input",
                    "kind": pending["kind"],
                    "issue_id": (values or {}).get("active_issue_id"),
                    "input_token": pending.get("input_token") or pending["card_id"],
                    "card_id": pending["card_id"],
                    "version": version,
                }
            )
        done = await store.complete_input(receipt, reason)
        record("session_event", session_id=session_id, run_id=run_id, payload=done)
        trace.finish(
            final_state,
            done_reason=reason,
            error_code=em.last_error_code,
            stage_from=em.first_stage,
            stage_to=stage,
            first_visible_ms=em.metric_values.get("first_visible_ms"),
            card_ready_ms=em.metric_values.get("card_ready_ms"),
            card_kind=em.card_kind,
            lane=os.environ.get("MODEL_LANE") or None,
            raw_ttl_hours=_retention_hours(),
            store_text=_store_text(),
        )
        yield done


def _error(
    code: str, message: str, *, recoverable: bool = False, retry: bool = False
) -> dict[str, Any]:
    return {
        "type": "error",
        "code": code,
        "message": message,
        "recoverable": recoverable,
        "retry_with_same_action": retry,
    }


async def checkpoint_state(graph: CompiledStateGraph, session_id: str):
    """读一次 checkpoint 状态；失败返回 None（调用方用 fallback）。"""
    try:
        return await graph.aget_state({"configurable": {"thread_id": session_id}})
    except Exception:
        log.exception("aget_state failed session=%s", session_id)
        return None


def _retention_hours() -> float:
    from app.settings import settings

    return settings.retention_session_hours


def _store_text() -> bool:
    from app.settings import settings

    return settings.analytics_store_text
