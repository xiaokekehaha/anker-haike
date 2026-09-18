"""会话接口（03 §2.1）：POST /sessions、POST /sessions/{id}/messages（SSE）、GET /sessions/{id}、
GET /sessions/{id}/runs/{run_id}/events?after_seq=（续接）、POST /sessions/{id}/cancel、
POST /sessions/{id}/actions（票 20 通路 + 票 22 幂等 / 会话锁 + 票 23 三种 409 与重试语义）、
POST /sessions/_exists（批量存活探测）。"""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from haike_contracts.actions import parse_action
from haike_contracts.snapshot import SessionSnapshot
from pydantic import BaseModel, ValidationError

from app.images import ImageRejected
from app.images.runtime import get_image_store
from app.images.store import MAX_IMAGE_BYTES, stage_image
from app.sessions import sse
from app.sessions.inputs import InputConflict, check_replay
from app.sessions.locks import DEFAULT_LOCK_TIMEOUT_S, LockTimeout
from app.sessions.manager import RunNotActive
from app.sessions.snapshot import SnapshotRecovering, build_snapshot
from app.sessions.store import SessionNotFound
from app.settings import settings as app_settings

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


MAX_PROBE_IDS = 50


class ExistsRequest(BaseModel):
    session_ids: list[str]


class ExistsResult(BaseModel):
    alive: list[str]


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


@router.post("/_exists", response_model=ExistsResult)
async def probe_sessions(body: ExistsRequest, request: Request) -> ExistsResult:
    """批量存活探测：前端最近会话列表用来剔除已过期的本地引用。

    刻意不走 GET /{session_id} —— 那条路要会话锁 + reconcile + 派生快照，首屏并发探测吃不消。
    这里只查存在性；存储不可用时由 _runtime 抛 503，调用方据此整轮跳过而不是当成「不存在」。
    """
    store, _, _ = _runtime(request)
    ids = list(dict.fromkeys(body.session_ids))
    if len(ids) > MAX_PROBE_IDS:
        raise HTTPException(
            422,
            detail={"code": "too_many_ids", "message": f"最多 {MAX_PROBE_IDS} 个会话"},
        )
    alive = [sid for sid in ids if await store.session_exists(sid)]
    return ExistsResult(alive=alive)


@router.post("/{session_id}/messages")
async def post_message(
    session_id: str,
    request: Request,
    input_id: Annotated[str, Form(min_length=1, max_length=128)],
    expected_version: Annotated[int, Form(ge=0)],
    text: Annotated[str, Form(max_length=4000)] = "",
    target_issue_id: Annotated[str | None, Form()] = None,
    images: Annotated[list[UploadFile], File()] = [],  # noqa: B006 - FastAPI 表单默认
    purpose: Annotated[str, Form(pattern="^(fault|receipt)$")] = "fault",
    evaluation_source: Annotated[str, Form(pattern="^(live|replay|smoke)$")] = "live",
):
    store, _graph, _manager = _runtime(request)
    await _ensure_exists(store, session_id)
    if not text.strip() and not images:
        raise HTTPException(422, detail={"code": "empty_input", "message": "请输入文字或添加图片"})
    staged = []
    img_store = get_image_store(request.app) if images else None
    if images and img_store is None:
        raise HTTPException(503, detail={"code": "images_unavailable", "message": "图片存储未就绪"})
    for index, up in enumerate(images):
        data = await up.read(MAX_IMAGE_BYTES + 1)
        try:
            staged.append(stage_image(session_id, input_id, index, purpose, data, up.content_type))
        except ImageRejected as exc:
            return JSONResponse(
                status_code=413 if exc.code == "too_large" else 415,
                content={"code": exc.code, "message": str(exc)},
            )
    payload = {
        "kind": "message",
        "evaluation_source": evaluation_source,
        "text": text,
        "purpose": purpose,
        "image_ids": [item.ref.image_id for item in staged],
        "images": [item.ref.public() for item in staged],
        "attachment_hashes": [item.ref.sha256 for item in staged],
        "target_issue_id": target_issue_id,
    }
    return await _accept(
        request,
        session_id,
        input_id,
        payload,
        expected_version,
        staged_images=staged,
        image_store=img_store,
    )


@router.get("/{session_id}/images/{image_id}")
async def get_image(session_id: str, image_id: str, request: Request):
    """会话内图片原图 / 缩略图来源（票 29）；只按 session 取，越会话访问 404。"""
    img_store = get_image_store(request.app)
    if img_store is None:
        return JSONResponse(
            status_code=503, content={"code": "images_unavailable", "message": "图片存储未就绪"}
        )
    found = await img_store.get(session_id, image_id)
    if found is None:
        return JSONResponse(
            status_code=404, content={"code": "not_found", "message": "image not found"}
        )
    ref, data = found
    return Response(
        content=data,
        media_type=ref.mime,
        headers={"Cache-Control": "private, max-age=3600", "X-Image-Sha256": ref.sha256},
    )


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


_CARD_KINDS = {"select_product", "step_feedback", "answer_observation", "confirm_receipt", "skip_receipt", "confirm_context", "confirm_proposal", "decline_proposal", "skip_retake", "rate_satisfaction"}


@router.post("/{session_id}/actions")
async def post_action(session_id: str, request: Request):
    try:
        action = parse_action(await request.json())
    except (ValidationError, ValueError) as exc:
        raise HTTPException(
            422, detail={"code": "invalid_action", "message": str(exc)[:500]}
        ) from None
    return await _accept(
        request,
        session_id,
        action.action_id,
        action.model_dump(mode="json"),
        action.expected_version,
    )


async def _accept(
    request: Request,
    session_id: str,
    input_id: str,
    payload: dict,
    expected_version: int,
    *,
    staged_images=(),
    image_store=None,
):
    store, graph, manager = _runtime(request)
    await _ensure_exists(store, session_id)
    lock = request.app.state.session_lock
    try:
        # Retries MUST be recognized before a request_human can cancel another run.
        async with lock.hold(session_id, timeout_s=LOCK_TIMEOUT_S):
            await manager.reconcile_session(session_id)
            old = await store.get_input(session_id, input_id)
            if old:
                check_replay(old, payload)
                return _sse(
                    manager.subscribe(session_id, old["run_id"]),
                    extra_headers={"X-Input-Replayed": "true", "X-Run-Id": old["run_id"]},
                )
        if payload["kind"] == "request_human":
            async with lock.hold(session_id, timeout_s=LOCK_TIMEOUT_S):
                old = await store.get_input(session_id, input_id)
                if old:
                    check_replay(old, payload)
                    return _sse(
                        manager.subscribe(session_id, old["run_id"]),
                        extra_headers={"X-Input-Replayed": "true", "X-Run-Id": old["run_id"]},
                    )
                row = await store.get_session(session_id)
                if row.published_checkpoint_id:
                    published = await graph.aget_state(
                        {
                            "configurable": {
                                "thread_id": session_id,
                                "checkpoint_id": row.published_checkpoint_id,
                            }
                        }
                    )
                    known = (published.values or {}).get("issues") or {}
                    if known and payload.get("target_issue_id") not in known:
                        raise InputConflict("wrong_issue")
                cancel_id = row.active_run_id
            # Never hold the acceptance lock while waiting for a run to finish.
            if cancel_id:
                try:
                    await manager.cancel(session_id, cancel_id)
                except RunNotActive:
                    pass
        async with lock.hold(session_id, timeout_s=LOCK_TIMEOUT_S):
            old = await store.get_input(session_id, input_id)
            if old:
                check_replay(old, payload)
                return _sse(
                    manager.subscribe(session_id, old["run_id"]),
                    extra_headers={"X-Input-Replayed": "true", "X-Run-Id": old["run_id"]},
                )
            await manager.reconcile_session(session_id)
            snap = await _consistent_snapshot(store, graph, session_id)
            row = await store.get_session(session_id)
            values = {}
            if row.published_checkpoint_id:
                state = await graph.aget_state(
                    {
                        "configurable": {
                            "thread_id": session_id,
                            "checkpoint_id": row.published_checkpoint_id,
                        }
                    }
                )
                values = state.values or {}
            if payload["kind"] != "request_human" and expected_version != snap.version:
                raise InputConflict("stale_version")
            target = payload.get("target_issue_id")
            if payload["kind"] == "request_human" and values.get("issues") and not target:
                raise InputConflict("wrong_issue")
            if target and target not in (values.get("issues") or {}):
                raise InputConflict("unknown_issue")
            if payload["kind"] in _CARD_KINDS:
                pending = snap.pending_input
                if pending is None:
                    raise InputConflict("not_allowed_now")
                if (
                    payload.get("card_id") != pending.card_id
                    or payload.get("input_token") != pending.input_token
                ):
                    raise InputConflict("stale_card")
                if target and target != values.get("active_issue_id"):
                    raise InputConflict("wrong_issue")
                if not _kind_allowed(payload["kind"], pending.kind):
                    raise InputConflict("not_allowed_now")
                if payload["kind"] == "select_product" and payload["payload"]["sku"] not in {
                    c["sku"]
                    for c in (values.get("pending_card") or {})
                    .get("payload", {})
                    .get("candidates", [])
                }:
                    raise InputConflict("invalid_selection")
                if payload["kind"] == "confirm_proposal" and payload["payload"]["option_id"] not in {o["option_id"] for o in ((values.get("pending_card") or {}).get("payload") or {}).get("options",[])}:
                    raise InputConflict("invalid_selection")
                if payload["kind"] == "answer_observation":
                    declared = ((values.get("pending_card") or {}).get("payload") or {}).get("observation") or {}
                    if payload["payload"]["observation_id"] != declared.get("observation_id") or payload["payload"]["option_id"] not in {
                        o["option_id"] for o in declared.get("options", [])
                    }:
                        raise InputConflict("invalid_selection")
            receipt, replay = await store.reserve_input(
                session_id,
                input_id,
                payload,
                expected_version=expected_version,
                staged_images=staged_images,
                image_store=image_store,
            )
            if not replay:
                await manager.start(session_id, receipt=receipt)
            return _sse(
                manager.subscribe(session_id, receipt["run_id"]),
                extra_headers={
                    "X-Input-Replayed": str(replay).lower(),
                    "X-Run-Id": receipt["run_id"],
                },
            )
    except InputConflict as exc:
        snap = await _consistent_snapshot(store, graph, session_id)
        return JSONResponse(
            status_code=409,
            content={
                "code": getattr(exc, "code", "run_active"),
                "message": str(exc),
                "snapshot": snap.model_dump(mode="json"),
            },
        )
    except SnapshotRecovering:
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "1"},
            content={"code": "recovering", "message": "会话记录正在恢复，请稍后重试"},
        )
    except LockTimeout:
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "2"},
            content={
                "code": "lock_timeout",
                "message": "会话正忙，请重试同一输入",
                "recoverable": True,
            },
        )


def _kind_allowed(kind: str, pending_kind: str) -> bool:
    if kind == "decline_proposal":
        return pending_kind == "confirm_proposal"
    if kind == "skip_retake":
        return pending_kind == "upload_retake"
    return (
        pending_kind in ("upload_receipt", "confirm_receipt")
        if kind == "skip_receipt"
        else kind == pending_kind
    )


@router.post("/{session_id}/cancel", response_model=CancelResult)
async def cancel_run(session_id: str, body: CancelRequest, request: Request) -> CancelResult:
    """取消 active run（08 §7）：图在当前节点中止、状态停在上一个 checkpoint，写 done(cancelled)；
    pending_input 保持取消前的值。仅 abort fetch 不等于取消。"""
    store, graph, manager = _runtime(request)
    await _ensure_exists(store, session_id)
    try:
        status = await manager.cancel(session_id, body.run_id)
    except RunNotActive:
        snap = await _consistent_snapshot(store, graph, session_id)
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


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    request: Request,
    x_admin_token: Annotated[str | None, Header()] = None,
):
    """票 48：按 session_id 删除全部数据（投影、事件、动作、图片、checkpoint），供人工处理删除请求。

    需 X-Admin-Token 与 ADMIN_TOKEN 一致；未配置 ADMIN_TOKEN 时接口关闭（403）。有 active run 先取消。
    """
    if not app_settings.admin_token:
        raise HTTPException(
            403, detail={"code": "admin_disabled", "message": "ADMIN_TOKEN not configured"}
        )
    if x_admin_token != app_settings.admin_token:
        raise HTTPException(403, detail={"code": "forbidden", "message": "bad admin token"})
    store, graph, manager = _runtime(request)
    try:
        row = await store.get_session(session_id)
    except SessionNotFound:
        row = None
    if row is not None and row.active_run_id:
        try:
            await manager.cancel(session_id, row.active_run_id)
        except RunNotActive:
            pass
    async with request.app.state.session_lock.hold(session_id, timeout_s=LOCK_TIMEOUT_S):
        if await store.session_exists(session_id):
            current = await store.get_session(session_id)
            if current.active_run_id:
                return JSONResponse(
                    status_code=409,
                    content={"code": "run_active", "message": "运行尚未结束，暂不能删除"},
                )
        pool = getattr(request.app.state, "session_pool", None)
        if pool is not None:
            from app.retention import delete_session_data

            counts = await delete_session_data(pool, session_id)
        else:
            counts = await store.delete_session_data(session_id)
            img_store = get_image_store(request.app)
            if img_store is not None:
                counts["session_images"] = await img_store.delete_session(session_id)
            checkpointer = getattr(graph, "checkpointer", None)
            if checkpointer is not None and hasattr(checkpointer, "adelete_thread"):
                await checkpointer.adelete_thread(session_id)
    if sum(counts.values()) == 0:
        raise HTTPException(404, detail={"code": "session_not_found", "message": session_id})
    return {"session_id": session_id, "deleted": counts}


@router.get("/{session_id}", response_model=SessionSnapshot)
async def get_snapshot(session_id: str, request: Request) -> SessionSnapshot:
    """权威快照（08 §6）：由 checkpoint 与事件日志派生，不读投影表。"""
    store, graph, manager = _runtime(request)
    async with request.app.state.session_lock.hold(session_id, timeout_s=LOCK_TIMEOUT_S):
        await _ensure_exists(store, session_id)
        try:
            await manager.reconcile_session(session_id)
            return await _consistent_snapshot(store, graph, session_id)
        except SnapshotRecovering:
            raise HTTPException(
                503,
                detail={"code": "recovering", "message": "会话记录正在恢复"},
                headers={"Retry-After": "1"},
            ) from None


async def _consistent_snapshot(store, graph, session_id):
    try:
        return await build_snapshot(store, graph, session_id)
    except SnapshotRecovering:
        raise HTTPException(
            503,
            detail={"code": "recovering", "message": "会话记录正在恢复"},
            headers={"Retry-After": "1"},
        ) from None


async def _ensure_exists(store, session_id: str) -> None:
    # 存在性用投影行或事件日志任一判断：投影被删后仍可访问并重建
    if not await store.session_exists(session_id):
        raise HTTPException(404, detail={"code": "session_not_found", "message": session_id})
