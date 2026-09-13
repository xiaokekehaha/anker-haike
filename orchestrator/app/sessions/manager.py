"""RunManager：run 在后台任务里执行并广播，HTTP 响应只是订阅者（08 §6–7，票 08）。

- 断开连接不等于取消：run 继续跑到 done 或 deadline，事件照常落库。
- subscribe(run_id, after_seq)：先从 session_events 重放，再接实时；以 seq 去重，不重复不丢失。
- 进程重启后内存里没有 live run：启动时 reconcile 把孤儿 run 以 error → done(error) 收尾。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from langgraph.graph.state import CompiledStateGraph

from app.sessions import runner
from app.sessions.store import SessionStore

log = logging.getLogger("sessions.manager")

_END = object()


class RunNotActive(LookupError):
    def __init__(self, session_id: str, run_id: str) -> None:
        super().__init__(f"run {run_id} is not active for session {session_id}")
        self.session_id = session_id
        self.run_id = run_id


@dataclass
class RunHandle:
    session_id: str
    run_id: str
    task: asyncio.Task | None = None
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    finished: bool = False
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)


class RunManager:
    def __init__(self, store: SessionStore, graph: CompiledStateGraph) -> None:
        self._store = store
        self._graph = graph
        self._live: dict[str, RunHandle] = {}
        from app.conversation.summary_cache import SummaryCache

        self.summary_cache = SummaryCache(store, graph)
        self._closing = False

    # ---- 启动 ----
    async def start(self, session_id: str, text: str | None = None, **kw: Any) -> RunHandle:
        """启动已接收输入；内部调用也必须先经过统一输入账本。"""
        cancel_event = asyncio.Event()
        gen = runner.run_message(
            self._store,
            self._graph,
            session_id,
            text,
            cancel_event=cancel_event,
            **kw,
        )
        first = await anext(gen)
        handle = RunHandle(session_id=session_id, run_id=first["run_id"], cancel_event=cancel_event)
        self._live[handle.run_id] = handle
        handle.task = asyncio.create_task(
            self._drain(handle, gen, first), name=f"run-{handle.run_id}"
        )
        return handle

    async def wait_finished(self, handle: RunHandle) -> None:
        """等待 run 收尾（done 已落库）。"""
        if handle.task is not None:
            await asyncio.shield(handle.task)

    async def _drain(self, handle: RunHandle, gen: AsyncIterator[dict], first: dict) -> None:
        try:
            self._broadcast(handle, first)
            async for ev in gen:
                self._broadcast(handle, ev)
        except Exception:
            log.exception("run drain failed run=%s", handle.run_id)
        finally:
            handle.finished = True
            for q in list(handle.subscribers):
                q.put_nowait(_END)
            self._live.pop(handle.run_id, None)
            if not self._closing:
                self.summary_cache.schedule(handle.session_id)

    def _broadcast(self, handle: RunHandle, ev: dict) -> None:
        for q in list(handle.subscribers):
            q.put_nowait(ev)

    # ---- 订阅 ----
    def is_live(self, run_id: str) -> bool:
        return run_id in self._live and not self._live[run_id].finished

    async def reconcile_session(self, session_id: str) -> None:
        """Caller holds the short session lock. Recovery never invokes a new model."""
        from app.sessions.snapshot import SnapshotRecovering
        from app.sessions.store import SessionNotFound

        try:
            row = await self._store.get_session(session_id)
        except SessionNotFound:
            return
        if row.active_run_id and not self.is_live(row.active_run_id):
            try:
                await self._finalize_orphan(session_id, row.active_run_id)
                if (await self._store.get_session(session_id)).active_run_id:
                    raise SnapshotRecovering("publication did not finish")
            except Exception as exc:
                raise SnapshotRecovering("publication recovery pending") from exc

    async def subscribe(
        self, session_id: str, run_id: str, after_seq: int = 0
    ) -> AsyncIterator[dict]:
        """先重放 seq > after_seq 的历史，再接实时；实时事件按 seq 过滤掉重放已覆盖的部分。"""
        queue: asyncio.Queue = asyncio.Queue()
        handle = self._live.get(run_id)
        if handle is not None and not handle.finished:
            handle.subscribers.add(queue)  # 先订阅再读历史，避免中间漏事件
        try:
            history = await self._store.list_events(session_id, run_id=run_id, after_seq=after_seq)
            last = after_seq
            for ev in history:
                last = ev["seq"]
                if ev.get("visibility") != "internal":
                    yield ev
            if handle is None or handle.finished:
                return
            while True:
                item = await queue.get()
                if item is _END:
                    return
                if item["seq"] <= last:
                    continue
                last = item["seq"]
                if item.get("visibility") != "internal":
                    yield item
                if item["type"] == "done":
                    return
        finally:
            if handle is not None:
                handle.subscribers.discard(queue)

    # ---- 取消（票 38，08 §7）----
    async def cancel(self, session_id: str, run_id: str, *, wait_s: float = 5.0) -> str:
        """设置取消标志并等待 run 收尾。返回 'cancelled'（已写 done）或 'cancelling'（超过 wait_s 仍在收尾）。
        run 不在本进程运行或不属于该会话时抛 RunNotActive。"""
        handle = self._live.get(run_id)
        if handle is None or handle.finished or handle.session_id != session_id:
            raise RunNotActive(session_id, run_id)
        handle.cancel_event.set()
        if handle.task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(handle.task), timeout=wait_s)
            except TimeoutError:
                return "cancelling"
        return "cancelled"

    # ---- 重启后的孤儿 run ----
    async def reconcile_orphans(self) -> list[tuple[str, str]]:
        """把投影表里仍标 active 但本进程没有在跑的 run 以 error → done(error) 收尾（服务重启）。
        单个会话收尾失败只跳过该会话：一条坏数据不能让整轮收尾（以及启动流程）中断。"""
        fixed: list[tuple[str, str]] = []
        for session_id, run_id in await self._store.list_active_runs():
            if self.is_live(run_id):
                continue
            try:
                await self._finalize_orphan(session_id, run_id)
            except Exception as exc:  # noqa: BLE001 - 坏会话跳过，其余仍要收尾
                log.error(
                    "orphan run reconcile failed session=%s run=%s: %s: %s",
                    session_id,
                    run_id,
                    type(exc).__name__,
                    str(exc)[:200],
                )
                continue
            fixed.append((session_id, run_id))
            log.warning("orphan run finalized session=%s run=%s", session_id, run_id)
        return fixed

    async def _finalize_orphan(self, session_id: str, run_id: str) -> None:
        em = runner.RunEmitter(self._store, session_id, run_id)
        prior = await self._store.list_event_records(session_id)
        em.last_seq = max((r.seq for r in prior), default=0)
        accepted = next(
            (
                r.event
                for r in prior
                if r.run_id == run_id and r.event.get("type") == "input_received"
            ),
            None,
        )
        receipt = (
            await self._store.get_input(session_id, accepted["input_id"]) if accepted else None
        )
        if receipt is None:
            raise RuntimeError("active run has no input receipt")
        if any(r.run_id == run_id and r.event.get("type") == "done" for r in prior):
            raise RuntimeError("terminal input still holds active run")
        from app.conversation.history import fold_history

        for entry in fold_history(session_id, prior):
            if (
                entry.run_id == run_id
                and entry.role == "assistant"
                and entry.kind == "message"
                and entry.status == "streaming"
            ):
                await em.emit(
                    {"type": "message_end", "message_id": entry.entry_id, "status": "aborted"}
                )
        checkpoint = await runner.checkpoint_state(self._graph, session_id)
        if (
            checkpoint
            and (checkpoint.values or {}).get("committed_input_id") == accepted["input_id"]
        ):
            handle = await self.start(session_id, receipt=receipt)
            await self.wait_finished(handle)
            return
        await em.emit(
            {
                "type": "error",
                "code": "server_restarted",
                "message": "本轮在提交前中断，之前的记录已保留，请重新发送。",
                "recoverable": True,
                "retry_with_same_action": False,
            }
        )
        await self._store.complete_input(receipt, "error")

    async def shutdown(self) -> None:
        self._closing = True
        await self.summary_cache.close()
        tasks = [h.task for h in list(self._live.values()) if h.task and not h.task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
