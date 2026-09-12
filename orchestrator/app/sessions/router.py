"""会话接口（03 §2.1）：POST /sessions、POST /sessions/{id}/messages（SSE）。"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.sessions import runner, sse
from app.sessions.store import ActiveRunConflict, SessionNotFound

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
    try:
        await store.get_session(session_id)
    except SessionNotFound:
        raise HTTPException(
            404, detail={"code": "session_not_found", "message": session_id}
        ) from None

    stream = runner.run_message(store, graph, session_id, text)
    # 先取首事件：若 active run 冲突在此抛出，可返回普通 409 而不是半截 SSE
    try:
        first = await anext(stream)
    except ActiveRunConflict as exc:
        row = await store.get_session(session_id)
        return JSONResponse(
            status_code=409,
            content={
                "code": "run_active",
                "message": f"session has active run {exc.active_run_id}",
                "snapshot": {
                    "session_id": row.session_id,
                    "version": row.version,
                    "stage": row.stage,
                    "active_run": {"run_id": exc.active_run_id},
                },
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
