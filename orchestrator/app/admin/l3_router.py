"""Minimal approvals; proxy supplies authenticated actor, dev uses a named demo actor."""

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.actions.runtime import require_services
from app.cases.service import validate_manual_action
from app.cases.store import CaseConflict, CaseNotFound
from app.sessions.router import _accept, _runtime
from app.settings import settings

router = APIRouter(prefix="/admin/api", tags=["L3 cases"])


class DecisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision_id: UUID
    expected_revision: int = Field(ge=0)
    decision: Literal["approve", "reject", "request_info"]
    option_id: str | None = None
    edited_option: dict | None = None
    override_reason: str | None = Field(default=None, max_length=2000)
    note: str = Field(min_length=1, max_length=2000)


class RevisionBody(BaseModel):
    expected_revision: int = Field(ge=0)


def actor(request):
    name = request.headers.get("X-Authenticated-User")
    if not name and settings.app_env != "dev":
        raise HTTPException(
            403, detail={"code": "admin_identity_required", "message": "需要代理认证的管理员身份"}
        )
    return "agent:" + (name or "demo")[:128]


def services():
    try:
        return require_services()
    except RuntimeError as error:
        raise HTTPException(
            503, detail={"code": "l3_unavailable", "message": str(error)}
        ) from error


@router.get("/cases/queue")
async def queue(status: str | None = "awaiting_approval", priority: str | None = None):
    return {"items": await services().cases.store.queue(status or None, priority or None)}


@router.get("/cases/{case_id}")
async def detail(case_id: UUID, request: Request):
    from app.admin.router import _snapshot

    try:
        row = await services().cases.store.get(str(case_id))
    except CaseNotFound:
        raise HTTPException(
            404, detail={"code": "case_not_found", "message": "案件不存在"}
        ) from None
    events = row.get("events", [])
    row["commitments"] = [e["payload"] for e in events if e["type"] == "commitment"]
    row["handoff_summary"] = next((e["payload"] for e in reversed(events) if e["type"] == "handoff_summary"), None)
    row["snapshot"] = await _snapshot(request, row["session_id"]) if row.get("session_id") else None
    row["executions"] = await services().executor.store.for_case(str(case_id))
    return row


@router.post("/cases/{case_id}/decision")
async def decide(case_id: UUID, body: DecisionBody, request: Request):
    try:
        row = await services().cases.decide(
            str(case_id),
            decision_id=str(body.decision_id),
            decision=body.decision,
            actor=actor(request),
            expected_revision=body.expected_revision,
            note=body.note,
            option_id=body.option_id,
            edited_option=body.edited_option,
            override_reason=body.override_reason,
        )
    except CaseNotFound:
        raise HTTPException(
            404, detail={"code": "case_not_found", "message": "案件不存在"}
        ) from None
    except CaseConflict as error:
        raise HTTPException(409, detail={"code": "case_conflict", "message": str(error)}) from error
    except ValueError as error:
        raise HTTPException(
            422, detail={"code": "invalid_decision", "message": str(error)}
        ) from error
    return await deliver(row, str(body.decision_id), request)


async def get_case(case_id):
    try:
        return await services().cases.store.get(str(case_id))
    except CaseNotFound:
        raise HTTPException(
            404, detail={"code": "case_not_found", "message": "案件不存在"}
        ) from None


async def deliver(row, decision_id, request):
    store, _, _ = _runtime(request)
    if not row.get("session_id") or not await store.session_exists(row["session_id"]):
        raise HTTPException(
            409,
            detail={
                "code": "session_unavailable",
                "message": "决定已保存，原会话不可恢复，请人工联系客户",
            },
        )
    session = await store.get_session(row["session_id"])
    payload = {
        "kind": "human_decision",
        "case_id": row["case_id"],
        "decision_id": decision_id,
        "target_issue_id": row["issue_id"],
    }
    response = await _accept(request, row["session_id"], decision_id, payload, session.version)
    if isinstance(response, JSONResponse):
        return response
    return {
        "case_id": row["case_id"],
        "decision_id": decision_id,
        "run_id": response.headers["X-Run-Id"],
        "status": "accepted",
    }


@router.post("/cases/{case_id}/decisions/{decision_id}/resume")
async def resume_decision(case_id: UUID, decision_id: UUID, request: Request):
    actor(request)
    row = await get_case(case_id)
    if not any(d["decision_id"] == str(decision_id) for d in row["decisions"]):
        raise HTTPException(404, detail={"code": "decision_not_found", "message": "决定不存在"})
    return await deliver(row, str(decision_id), request)


@router.post("/cases/{case_id}/close")
async def close(case_id: UUID, body: RevisionBody, request: Request):
    return await lifecycle(case_id, body, request, "close")


@router.post("/cases/{case_id}/reopen")
async def reopen(case_id: UUID, body: RevisionBody, request: Request):
    return await lifecycle(case_id, body, request, "reopen")


async def lifecycle(case_id, body, request, command):
    row = await get_case(case_id)
    who = actor(request)
    command_id = str(uuid5(NAMESPACE_URL, f"case:{case_id}:{body.expected_revision}:{command}:{who}"))
    try:
        if not any(e["type"] == "manual_action" and e["payload"].get("command_id") == command_id for e in row["events"]):
            validate_manual_action(row, command, body.expected_revision)
    except CaseConflict as error:
        raise HTTPException(409, detail={"code": "case_conflict", "message": str(error)}) from error
    store, _, manager = _runtime(request)
    if not row.get("session_id") or not await store.session_exists(row["session_id"]):
        # Retained cases remain administrable after the conversation expires.
        try:
            return await services().cases.manual_action(str(case_id), command, command_id=command_id, actor=who, expected_revision=body.expected_revision)
        except CaseConflict as error:
            raise HTTPException(409, detail={"code": "case_conflict", "message": str(error)}) from error
    session = await store.get_session(row["session_id"])
    response = await _accept(request, row["session_id"], command_id, {
        "kind": "case_command", "command": command, "case_id": str(case_id),
        "expected_revision": body.expected_revision, "actor": who,
        "target_issue_id": row["issue_id"],
    }, session.version)
    if isinstance(response, JSONResponse):
        return response
    # This deterministic command has no model or backend write. Return success
    # only after the normal run commits both state and durable display effects.
    completed = False
    async for event in manager.subscribe(row["session_id"], response.headers["X-Run-Id"]):
        if event["type"] == "error":
            raise HTTPException(409, detail={"code": "case_command_failed", "message": event["message"]})
        if event["type"] == "done":
            completed = event["reason"] == "completed"
    if not completed:
        raise HTTPException(409, detail={"code": "case_command_incomplete", "message": "案件操作尚未完成，请刷新后重试"})
    return await get_case(case_id)


@router.get("/metrics/l3")
async def l3_metrics(request: Request, since: datetime | None = None):
    from app.analytics.l3 import metrics

    since = since or datetime.now(UTC) - timedelta(days=7)
    if since.tzinfo is None:
        since = since.replace(tzinfo=UTC)
    result = metrics(await services().cases.store.metric_rows(since))
    result["unauthorized_executions"] = None
    pool = getattr(request.app.state, "session_pool", None)
    if pool:
        async with pool.connection() as conn:
            cur = await conn.execute(
                """select count(*) from action_executions a
                where action_kind='replacement.create' and status='succeeded' and started_at >= %s
                and not exists(select 1 from service_episodes e where e.session_id=a.session_id and e.issue_id=a.issue_id and e.source in ('replay','smoke'))
                and (gate_result is null or gate_result->>'passed' is distinct from 'true'
                or exists(select 1 from jsonb_array_elements(coalesce(gate_result->'checks','[]')) c where c->>'passed' is distinct from 'true')
                or not (coalesce(gate_result->'checks','[]') @> '[{"name":"policy"},{"name":"evidence_and_consent"},{"name":"safety"},{"name":"idempotency"}]'::jsonb))""",
                (since,),
            )
            row = await cur.fetchone()
            result["unauthorized_executions"] = (
                row[0] if not isinstance(row, dict) else row["count"]
            )
    return result
