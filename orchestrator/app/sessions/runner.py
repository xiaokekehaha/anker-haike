"""一次 run 的事件流：run_started → (progress | ping)* → done；异常路径 error → done(error)；
取消路径（票 38，08 §7）：cancel_event 置位 → 取消图任务 → done(cancelled)，状态回到上一个 checkpoint。

每条事件先 append 到 session_events 拿到 seq，再交给调用方发送（08 §2、§5）。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from haike_contracts.events import parse_event
from langgraph.graph.state import CompiledStateGraph

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
        return draft


async def run_message(
    store: SessionStore,
    graph: CompiledStateGraph,
    session_id: str,
    text: str,
    *,
    image_ids: list[str] | None = None,
    deadline_ms: int = DEFAULT_DEADLINE_MS,
    ping_interval_s: float | None = None,
    cancel_event: asyncio.Event | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """占用 active run，产出契约事件字典。调用前 store.try_start_run 已成功。"""
    run_id = uuid.uuid4().hex
    if ping_interval_s is None:
        ping_interval_s = PING_INTERVAL_S  # 运行时读取，便于测试覆写
    row = await store.try_start_run(session_id, run_id)  # 失败抛 ActiveRunConflict
    em = RunEmitter(store, session_id, run_id)
    # 存储层可能已有历史事件（多轮对话），seq 需接着排
    prior = await store.list_events(session_id)
    em.last_seq = max((e["seq"] for e in prior), default=0)

    queue: asyncio.Queue[Any] = asyncio.Queue()
    started = time.monotonic()
    stage: str | None = None
    reason = "completed"

    async def pump() -> None:
        try:
            config = {"configurable": {"thread_id": session_id}}
            payload = {
                "session_id": session_id,
                "run_id": run_id,
                "at": datetime.now(UTC).isoformat(),
                "text": text,
                "image_ids": image_ids or [],
            }
            async for mode, chunk in graph.astream(
                payload, config, stream_mode=["custom", "updates"]
            ):
                await queue.put((mode, chunk))
            await queue.put(_GRAPH_DONE)
        except Exception as exc:  # noqa: BLE001 - 任何节点异常都要转为 error 事件
            await queue.put(exc)

    async def watch_cancel() -> None:
        assert cancel_event is not None
        await cancel_event.wait()
        await queue.put(_CANCELLED)

    task = asyncio.create_task(pump())
    watcher = asyncio.create_task(watch_cancel()) if cancel_event is not None else None
    try:
        yield await em.emit({"type": "run_started", "resumed": False, "deadline_ms": deadline_ms})
        while True:
            remaining = deadline_ms / 1000 - (time.monotonic() - started)
            if remaining <= 0:
                task.cancel()
                reason = "error"
                yield await em.emit(
                    _error("deadline_exceeded", "run exceeded deadline", recoverable=True)
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
                yield await em.emit(_error("node_failed", f"{type(item).__name__}: {item}"[:300]))
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
        version = await checkpoint_version(graph, session_id, fallback=row.version)
        try:
            await store.finish_run(session_id, run_id, version=version, stage=stage)
        except Exception:
            log.exception("finish_run failed session=%s run=%s", session_id, run_id)
        # 必以 done 结束；若消费者已断开，done 仍要落库（票 08 续接读取）
        done = await em.emit({"type": "done", "reason": reason, "version": version})
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


async def checkpoint_version(
    graph: CompiledStateGraph, session_id: str, *, fallback: int = 0
) -> int:
    """version = 最新 checkpoint 的 step + 1（step 跨 run 单调递增，无 checkpoint 时为 0）。"""
    try:
        state = await graph.aget_state({"configurable": {"thread_id": session_id}})
    except Exception:
        log.exception("aget_state failed session=%s", session_id)
        return fallback
    if not state.metadata:
        return 0
    return int(state.metadata.get("step", -1)) + 1
