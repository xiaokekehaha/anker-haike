"""会话接口（03 §2.1）：POST /sessions、POST /sessions/{id}/messages（SSE）。"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from haike_contracts.snapshot import SessionSnapshot
from pydantic import BaseModel

from app.sessions import runner, sse
from app.sessions.snapshot import build_snapshot
from app.sessions.store import ActiveRunConflict

log = logging.getLogger("sessions.router")
router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionCreated(BaseModel):
    session_id: str
    version: int


def _runtime(request: Request):
    store = getattr(request.app.state, "session_store", None)
    graph = getattr(request.app.state, "session_graph", None)
    if store is None or graph is None:
        raise HTTPException(
            503,
            detail={"code": "sessions_unavailable", "message": "会话存储未就绪（数据库不可用）"},
        )
    return store, graph


@router.post("", status_code=201, response_model=SessionCreated)
async def create_session(request: Request) -> SessionCreated:
    store, _ = _runtime(request)
    row = await store.create_session()
    return SessionCreated(session_id=row.session_id, version=row.version)


@router.post("/{session_id}/messages")
async def post_message(
    session_id: str,
    request: Request,
    text: Annotated[str, Form(min_length=1, max_length=4000)],
):
    store, graph = _runtime(request)
    await _ensure_exists(store, session_id)

    stream = runner.run_message(store, graph, session_id, text)
    # 先取首事件：若 active run 冲突在此抛出，可返回普通 409 而不是半截 SSE
    try:
        first = await anext(stream)
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

    async def body():
        try:
            yield sse.encode(first)
            async for ev in stream:
                yield sse.encode(ev)
        finally:
            await stream.aclose()

    return StreamingResponse(body(), media_type="text/event-stream", headers=sse.SSE_HEADERS)


@router.get("/{session_id}", response_model=SessionSnapshot)
async def get_snapshot(session_id: str, request: Request) -> SessionSnapshot:
    """权威快照（08 §6）：由 checkpoint 与事件日志派生，不读投影表。"""
    store, graph = _runtime(request)
    await _ensure_exists(store, session_id)
    return await build_snapshot(store, graph, session_id)


async def _ensure_exists(store, session_id: str) -> None:
    # 存在性用投影行或事件日志任一判断：投影被删后仍可访问并重建
    if not await store.session_exists(session_id):
        raise HTTPException(404, detail={"code": "session_not_found", "message": session_id})
