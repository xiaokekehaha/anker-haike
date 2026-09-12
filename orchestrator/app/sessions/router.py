"""会话接口（03 §2.1）：POST /sessions、POST /sessions/{id}/messages（SSE）、GET /sessions/{id}、
GET /sessions/{id}/runs/{run_id}/events?after_seq=（续接）、POST /sessions/{id}/cancel、
POST /sessions/{id}/actions（票 20 通路 + 票 22 幂等 / 会话锁 + 票 23 三种 409 与重试语义）。"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Form, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from haike_contracts.actions import parse_action
from haike_contracts.snapshot import SessionSnapshot
from pydantic import BaseModel, ValidationError

from app.sessions import sse
from app.sessions.locks import DEFAULT_LOCK_TIMEOUT_S, LockTimeout
from app.sessions.manager import RunNotActive
from app.sessions.snapshot import action_pending_apply, build_snapshot
from app.sessions.store import ActiveRunConflict

log = logging.getLogger("sessions.router")
router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionCreated(BaseModel):
    session_id: str
    version: int


class CancelRequest(BaseModel):
    run_id: str


class CancelResult(BaseModel):
    run_id: str
    status: Literal["cancelled", "cancelling"]


LOCK_TIMEOUT_S = DEFAULT_LOCK_TIMEOUT_S  # 08 §4：30 s；测试可覆写


def _runtime(request: Request):
    store = getattr(request.app.state, "session_store", None)
    graph = getattr(request.app.state, "session_graph", None)
    manager = getattr(request.app.state, "run_manager", None)
    if store is None or graph is None or manager is None:
        raise HTTPException(
            503,
            detail={"code": "sessions_unavailable", "message": "会话存储未就绪（数据库不可用）"},
        )
    return store, graph, manager


@router.post("", status_code=201, response_model=SessionCreated)
async def create_session(request: Request) -> SessionCreated:
    store, _, _ = _runtime(request)
    row = await store.create_session()
    return SessionCreated(session_id=row.session_id, version=row.version)


@router.post("/{session_id}/messages")
async def post_message(
    session_id: str,
    request: Request,
    text: Annotated[str, Form(min_length=1, max_length=4000)],
):
    store, graph, manager = _runtime(request)
    await _ensure_exists(store, session_id)
    try:
        handle = await manager.start(session_id, text)
    except ActiveRunConflict as exc:
        # 409 附最新权威快照供前端重建（08 §4 第 3 步）
        snap = await build_snapshot(store, graph, session_id)
        return JSONResponse(
            status_code=409,
            content={
                "code": "run_active",
                "message": f"session has active run {exc.active_run_id}",
                "snapshot": snap.model_dump(mode="json"),
            },
        )
    # run 已在后台执行；本响应只是从 seq 0 起的订阅者，断开不影响 run（08 §7）
    return _sse(manager.subscribe(session_id, handle.run_id, after_seq=0))


@router.get("/{session_id}/runs/{run_id}/events")
async def resume_events(
    session_id: str,
    run_id: str,
    request: Request,
    after_seq: Annotated[int, Query(ge=0)] = 0,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
):
    """续接：先重放 session_events 中 seq > after_seq 的本 run 事件，再接实时流（08 §6 规则 2）。
    也接受标准 SSE 重连头 Last-Event-ID（取两者较大值）。"""
    store, _, manager = _runtime(request)
    await _ensure_exists(store, session_id)
    if last_event_id and last_event_id.isdigit():
        after_seq = max(after_seq, int(last_event_id))
    if not manager.is_live(run_id) and not await store.list_events(session_id, run_id=run_id):
        raise HTTPException(404, detail={"code": "run_not_found", "message": run_id})
    return _sse(manager.subscribe(session_id, run_id, after_seq=after_seq))


_CARD_KINDS = {"select_product", "step_feedback", "confirm_receipt", "skip_receipt"}


@router.post("/{session_id}/actions")
async def post_action(session_id: str, request: Request):
    """动作协议（08 §4）：会话锁串行 → action_id 去重（重放）→ 校验 → 占位 → Command(resume) → 回填。"""
    store, graph, manager = _runtime(request)
    lock = request.app.state.session_lock
    await _ensure_exists(store, session_id)
    try:
        action = parse_action(await request.json())
    except (ValidationError, ValueError) as exc:
        raise HTTPException(
            422, detail={"code": "invalid_action", "message": str(exc)[:500]}
        ) from None

    # 1. 会话级锁：同会话动作串行；锁一直持有到本动作的 run 结束（见 _finish_action）
    hold = lock.hold(session_id, timeout_s=LOCK_TIMEOUT_S)
    try:
        await hold.__aenter__()
    except LockTimeout:
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "2"},
            content={
                "code": "lock_timeout",
                "message": "会话正忙，请稍后重试同一动作",
                "recoverable": True,
                "retry_with_same_action": True,
            },
        )
    release = hold.__aexit__
    handoff = False  # True = 锁交给后台回填任务释放
    try:
        # 2. 去重：同一 action_id 已记录 → 直接重放对应事件流（200，replayed=true）
        recorded = await store.get_action(session_id, action.action_id)
        if recorded is not None:
            return _sse(
                manager.subscribe(session_id, recorded["run_id"], after_seq=0),
                extra_headers={
                    "X-Action-Id": action.action_id,
                    "X-Run-Id": recorded["run_id"],
                    "X-Action-Replayed": "true",
                },
            )

        # 3. 校验（票 23）
        snap = await build_snapshot(store, graph, session_id)
        # 同一 action_id 重试且图停在「动作已接收、apply_action 未成功」：跳过校验，从待执行节点继续
        state = await graph.aget_state({"configurable": {"thread_id": session_id}})
        continue_run = snap.active_run is None and action_pending_apply(state) == action.action_id

        def conflict(code: str, message: str) -> JSONResponse:
            return JSONResponse(
                status_code=409,
                content={
                    "code": code,
                    "message": message,
                    "snapshot": snap.model_dump(mode="json"),
                },
            )

        # 08 §4 步骤 3 的顺序：version → card → kind（票 23）。快照随 409 返回供前端重建
        if snap.active_run is not None:
            return conflict("run_active", f"session has active run {snap.active_run.run_id}")
        if not continue_run:
            if action.kind not in _CARD_KINDS:
                # 全局动作不校 version / pending（08 §4 步骤 4）：request_human（票 25）、rediagnose（票 37）接入前先拒绝
                return conflict("not_allowed_now", f"{action.kind} is not supported yet")
            if action.expected_version != snap.version:
                return conflict(
                    "stale_version", f"expected {action.expected_version}, current {snap.version}"
                )
            pending = snap.pending_input
            if pending is None:
                return conflict("not_allowed_now", "no pending input")
            if action.card_id != pending.card_id or action.interrupt_id != pending.interrupt_id:
                return conflict("stale_card", "card_id / interrupt_id do not match pending input")
            if not _kind_allowed(action.kind, pending.kind):
                return conflict(
                    "not_allowed_now",
                    f"{action.kind} is not allowed while awaiting {pending.kind}",
                )

        # 4. 启动 run 并写占位（占位带 run_id：进程中途挂掉时，重放仍能定位到该 run 的事件）
        try:
            if continue_run:
                handle = await manager.start(session_id, continue_run=True)
            else:
                handle = await manager.start(session_id, resume=action.model_dump(mode="json"))
        except ActiveRunConflict as exc:
            return conflict("run_active", f"session has active run {exc.active_run_id}")
        inserted = await store.try_insert_action(
            session_id,
            action.action_id,
            {
                "action_id": action.action_id,
                "run_id": handle.run_id,
                "replayed": False,
                "version_after": None,
                "status": "pending",
            },
        )
        if not inserted:  # 理论上不可能（锁内），防御性记录
            log.error(
                "action placeholder already present session=%s action=%s",
                session_id,
                action.action_id,
            )
        handoff = True
    finally:
        # 重放 / 409 / 异常：在此释放；只有成功启动 run 时锁交给 _finish_action 在 run 结束后释放
        if not handoff:
            await release(None, None, None)

    # 5. 后台：run 结束后回填结果并释放锁；HTTP 响应只是订阅者
    asyncio.create_task(_finish_action(store, manager, handle, action.action_id, release))
    return _sse(
        manager.subscribe(session_id, handle.run_id, after_seq=0),
        extra_headers={
            "X-Action-Id": action.action_id,
            "X-Run-Id": handle.run_id,
            "X-Action-Replayed": "false",
        },
    )


def _kind_allowed(kind: str, pending_kind: str) -> bool:
    """08 §4 允许时机表：skip_receipt 在 upload_receipt / confirm_receipt 下均可，其余 kind 须与 pending 相同。"""
    if kind == "skip_receipt":
        return pending_kind in ("upload_receipt", "confirm_receipt")
    return kind == pending_kind


async def _finish_action(store, manager, handle, action_id: str, release) -> None:
    try:
        await manager.wait_finished(handle)
        events = await store.list_events(handle.session_id, run_id=handle.run_id)
        done = next((e for e in reversed(events) if e["type"] == "done"), None)
        if done is not None and done["reason"] in ("error", "cancelled"):
            # 动作未被应用：撤销占位，同一 action_id 重试时真正执行而不是重放失败流（票 23，
            # 与 error.retry_with_same_action=true 配套）。apply_action 以 card_id 幂等，重放副作用安全
            await store.delete_action(handle.session_id, action_id)
            return
        await store.set_action_result(
            handle.session_id,
            action_id,
            {
                "action_id": action_id,
                "run_id": handle.run_id,
                "replayed": False,
                "version_after": done["version"] if done else None,
                "status": "done",
            },
        )
    except Exception:
        log.exception("action backfill failed session=%s action=%s", handle.session_id, action_id)
    finally:
        await release(None, None, None)


@router.post("/{session_id}/cancel", response_model=CancelResult)
async def cancel_run(session_id: str, body: CancelRequest, request: Request) -> CancelResult:
    """取消 active run（08 §7）：图在当前节点中止、状态停在上一个 checkpoint，写 done(cancelled)；
    pending_input 保持取消前的值。仅 abort fetch 不等于取消。"""
    store, graph, manager = _runtime(request)
    await _ensure_exists(store, session_id)
    try:
        status = await manager.cancel(session_id, body.run_id)
    except RunNotActive:
        snap = await build_snapshot(store, graph, session_id)
        return JSONResponse(  # type: ignore[return-value]
            status_code=409,
            content={
                "code": "run_not_active",
                "message": f"run {body.run_id} is not the active run of this session",
                "snapshot": snap.model_dump(mode="json"),
            },
        )
    return CancelResult(run_id=body.run_id, status=status)


def _sse(events, extra_headers: dict[str, str] | None = None) -> StreamingResponse:
    async def body():
        async for ev in events:
            yield sse.encode(ev)

    headers = {**sse.SSE_HEADERS, **(extra_headers or {})}
    return StreamingResponse(body(), media_type="text/event-stream", headers=headers)


@router.get("/{session_id}", response_model=SessionSnapshot)
async def get_snapshot(session_id: str, request: Request) -> SessionSnapshot:
    """权威快照（08 §6）：由 checkpoint 与事件日志派生，不读投影表。"""
    store, graph, _ = _runtime(request)
    await _ensure_exists(store, session_id)
    return await build_snapshot(store, graph, session_id)


async def _ensure_exists(store, session_id: str) -> None:
    # 存在性用投影行或事件日志任一判断：投影被删后仍可访问并重建
    if not await store.session_exists(session_id):
        raise HTTPException(404, detail={"code": "session_not_found", "message": session_id})
