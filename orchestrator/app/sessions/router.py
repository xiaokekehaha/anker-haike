"""会话接口（03 §2.1）：POST /sessions、POST /sessions/{id}/messages（SSE）、GET /sessions/{id}、
GET /sessions/{id}/runs/{run_id}/events?after_seq=（续接）、POST /sessions/{id}/cancel、
POST /sessions/{id}/actions（票 20 基本通路；幂等 / 会话锁在票 22，完整 409 语义在票 23）。"""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Form, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from haike_contracts.actions import parse_action
from haike_contracts.snapshot import SessionSnapshot
from pydantic import BaseModel, ValidationError

from app.sessions import sse
from app.sessions.manager import RunNotActive
from app.sessions.snapshot import build_snapshot
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
    """动作协议（08 §4）：校验后以 Command(resume=action) 恢复图并开新 SSE 流。"""
    store, graph, manager = _runtime(request)
    await _ensure_exists(store, session_id)
    try:
        action = parse_action(await request.json())
    except (ValidationError, ValueError) as exc:
        raise HTTPException(
            422, detail={"code": "invalid_action", "message": str(exc)[:500]}
        ) from None

    snap = await build_snapshot(store, graph, session_id)

    def conflict(code: str, message: str) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"code": code, "message": message, "snapshot": snap.model_dump(mode="json")},
        )

    if snap.active_run is not None:
        return conflict("run_active", f"session has active run {snap.active_run.run_id}")
    if action.kind not in _CARD_KINDS:
        # request_human（票 25）、rediagnose（票 37）在各自票接入
        return conflict("not_allowed_now", f"{action.kind} is not supported yet")
    pending = snap.pending_input
    if pending is None or pending.kind != action.kind:
        return conflict("not_allowed_now", f"no pending input of kind {action.kind}")
    if action.card_id != pending.card_id or action.interrupt_id != pending.interrupt_id:
        return conflict("stale_card", "card_id / interrupt_id do not match pending input")
    if action.expected_version != snap.version:
        return conflict(
            "version_mismatch", f"expected {action.expected_version}, current {snap.version}"
        )

    try:
        handle = await manager.start(session_id, resume=action.model_dump(mode="json"))
    except ActiveRunConflict as exc:
        return conflict("run_active", f"session has active run {exc.active_run_id}")
    return _sse(manager.subscribe(session_id, handle.run_id, after_seq=0))


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


def _sse(events) -> StreamingResponse:
    async def body():
        async for ev in events:
            yield sse.encode(ev)

    return StreamingResponse(body(), media_type="text/event-stream", headers=sse.SSE_HEADERS)


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
