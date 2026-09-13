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
from langgraph.types import Command

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

    async def emit(self, payload: dict[str, Any]) -> dict[str, Any]:
        # seq 由存储层分配；先用占位值过一遍校验，落库后回填真实 seq 再校验一次
        draft = {**payload, "run_id": self.run_id, "seq": self.last_seq + 1}
        parse_event(draft)
        seq = await self._store.append_event(self.session_id, self.run_id, draft)
        if seq != draft["seq"]:
            draft["seq"] = seq
            parse_event(draft)
            # 存储层给出的 seq 与本地计数不一致：只可能在旧事件残留时出现，纠正后继续
            log.warning(
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
    resume: dict[str, Any] | None = None,
    continue_run: bool = False,
    entry_action: dict[str, Any] | None = None,
    image_ids: list[str] | None = None,
    deadline_ms: int = DEFAULT_DEADLINE_MS,
    ping_interval_s: float | None = None,
    cancel_event: asyncio.Event | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """占用 active run，产出契约事件字典。text 为新消息；resume 为对 interrupt 的动作（票 20），
    此时以 Command(resume=action) 恢复图，run_started.resumed=True。continue_run=True 为「同一 action_id 重试」
    （票 23）：动作已被 await_input 接收但 apply_action 未成功，以 None 输入让图从待执行节点继续。"""
    run_id = uuid.uuid4().hex
    if ping_interval_s is None:
        ping_interval_s = PING_INTERVAL_S  # 运行时读取，便于测试覆写
    row = await store.try_start_run(session_id, run_id)  # 失败抛 ActiveRunConflict
    em = RunEmitter(store, session_id, run_id)
    # 存储层可能已有历史事件（多轮对话），seq 需接着排
    prior = await store.list_events(session_id)
    em.last_seq = max((e["seq"] for e in prior), default=0)
    trace = RunTrace(
        session_id,
        run_id,
        entry=_entry_label(text, resume, continue_run, entry_action),
        seq_no=len({e["run_id"] for e in prior}) + 1,
    )

    queue: asyncio.Queue[Any] = asyncio.Queue()
    started = time.monotonic()
    stage: str | None = None
    reason = "completed"
    interrupted = False
    is_action = resume is not None or continue_run or entry_action is not None

    async def pump() -> None:
        context_token = run_id_context.set(run_id)
        try:
            config = {"configurable": {"thread_id": session_id}}
            payload: Any
            if resume is not None:
                payload = Command(resume=resume)
            elif continue_run:
                payload = None
            elif entry_action is not None:
                # 全局动作（request_human，票 25）在没有 interrupt 时从 START 进图：route_entry 直达 human_request
                payload = {
                    "session_id": session_id,
                    "run_id": run_id,
                    "at": datetime.now(UTC).isoformat(),
                    "entry": "action",
                    "last_action": entry_action,
                }
            else:
                payload = {
                    "session_id": session_id,
                    "run_id": run_id,
                    "at": datetime.now(UTC).isoformat(),
                    "entry": "message",
                    "text": text or "",
                    "image_ids": image_ids or [],
                }
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
        yield await em.emit(
            {
                "type": "run_started",
                "resumed": resume is not None or continue_run,
                "deadline_ms": deadline_ms,
            }
        )
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
                        retry=is_action,
                    )
                )
                break
            try:
                item = await asyncio.wait_for(queue.get(), timeout=min(ping_interval_s, remaining))
            except TimeoutError:
                yield await em.emit({"type": "ping"})
                continue
            if item is _GRAPH_DONE:
                if interrupted:
                    reason = "awaiting_input"
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
                # 动作 run 失败：状态停在中断前的 checkpoint、动作未被应用，前端可复用 action_id 重试（票 23）
                yield await em.emit(
                    _error(
                        "node_failed",
                        f"{type(item).__name__}: {item}"[:300],
                        recoverable=is_action,
                        retry=is_action,
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
            elif mode == "updates" and isinstance(chunk, dict) and "__interrupt__" in chunk:
                trace.on_updates(chunk)
                # 图在 await_input 中断：awaiting_input 的 version 由节点随中断载荷带出（langgraph_step），
                # 不在此查 checkpoint——PostgresSaver 写入异步，此刻可能尚未落地
                interrupted = True
                for intr in chunk["__interrupt__"]:
                    value = dict(getattr(intr, "value", {}) or {})
                    if "version" not in value:
                        value["version"] = await checkpoint_version(graph, session_id)
                    yield await em.emit({"type": "awaiting_input", **value})
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
        version = version_of(final_state, fallback=row.version)
        try:
            await store.finish_run(session_id, run_id, version=version, stage=stage)
        except Exception:
            log.exception("finish_run failed session=%s run=%s", session_id, run_id)
        # 必以 done 结束；若消费者已断开，done 仍要落库（票 08 续接读取）
        done = await em.emit({"type": "done", "reason": reason, "version": version})
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


def version_of(state, *, fallback: int = 0) -> int:
    """version = 最新 checkpoint 的 step + 1（step 跨 run 单调递增，无 checkpoint 时为 0）。"""
    if state is None:
        return fallback
    if not state.metadata:
        return 0
    return int(state.metadata.get("step", -1)) + 1


async def checkpoint_version(
    graph: CompiledStateGraph, session_id: str, *, fallback: int = 0
) -> int:
    return version_of(await checkpoint_state(graph, session_id), fallback=fallback)


def _entry_label(
    text: str | None,
    resume: dict[str, Any] | None,
    continue_run: bool,
    entry_action: dict[str, Any] | None,
) -> str:
    """run 的入口，供观测台按来源分组。"""
    action = resume or entry_action
    if action is not None:
        return f"action:{action.get('kind', 'unknown')}"
    if continue_run:
        return "action:retry"
    return "message" if text is not None else "unknown"


def _retention_hours() -> float:
    from app.settings import settings

    return settings.retention_session_hours


def _store_text() -> bool:
    from app.settings import settings

    return settings.analytics_store_text
