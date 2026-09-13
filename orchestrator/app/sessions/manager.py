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

    # ---- 启动 ----
    async def start(
        self, session_id: str, text: str | None = None, *, resume: dict | None = None, **kw: Any
    ) -> RunHandle:
        """占用 active run 并落库 run_started 后返回；ActiveRunConflict 在此同步抛出。
        text 为新消息，resume 为对 interrupt 的动作（票 20）。"""
        cancel_event = asyncio.Event()
        gen = runner.run_message(
            self._store,
            self._graph,
            session_id,
            text,
            resume=resume,
            cancel_event=cancel_event,
            **kw,
        )
        first = await anext(gen)  # try_start_run + run_started；冲突在这里抛
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

    def _broadcast(self, handle: RunHandle, ev: dict) -> None:
        for q in list(handle.subscribers):
            q.put_nowait(ev)

    # ---- 订阅 ----
    def is_live(self, run_id: str) -> bool:
        return run_id in self._live and not self._live[run_id].finished

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
        # seq / run_id / type 取自事件表的列，不读 event_json：历史行的 JSON 可能缺字段，
        # 且 last_seq 必须是库里真实的最大 seq，否则续写会撞唯一约束。
        prior = await self._store.list_event_records(session_id)
        em.last_seq = max((r.seq for r in prior), default=0)
        already_done = any(
            r.run_id == run_id and r.event.get("type") == "done" for r in prior
        )
        version = await runner.checkpoint_version(self._graph, session_id)
        if not already_done:
            await em.emit(
                {
                    "type": "error",
                    "code": "server_restarted",
                    "message": "编排服务重启，本轮处理中断，请重新发送",
                    "recoverable": True,
                    "retry_with_same_action": False,
                }
            )
            await em.emit({"type": "done", "reason": "error", "version": version})
        await self._store.finish_run(session_id, run_id, version=version)

    async def shutdown(self) -> None:
        for h in list(self._live.values()):
            if h.task and not h.task.done():
                h.task.cancel()
