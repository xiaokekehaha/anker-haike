"""管理员观测台接口 `/admin/api/*`（只读为主 + 案例标注）。

黑客松范围不做鉴权（02_hackathon-scope.md）：生产必须放在反向代理之后并加访问控制，
见 docs/planning/2026-09-13_admin-observability-console/01_design.md §11 D4。

24 小时 / 演示期 7 天内的会话，详情里附带现有权威快照（完整时间线复用聊天端契约）；
过期后只剩 analytics 事实，页面据 `raw_available` 决定能否渲染完整对话。
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from app.admin.graph_export import topology
from app.analytics.derive import REASON_TAGS
from app.analytics.queries import Queries
from app.settings import settings

log = logging.getLogger("admin.router")
router = APIRouter(prefix="/admin/api", tags=["admin"])

Verdict = Literal["good", "bad", "review"]
CaseStatus = Literal["open", "exported", "fixed", "wontfix"]


def _queries(request: Request) -> Queries:
    pool = getattr(request.app.state, "session_pool", None)
    if pool is None:
        raise HTTPException(
            503, detail={"code": "analytics_unavailable", "message": "数据库未就绪"}
        )
    return Queries(pool, abandon_after_h=settings.analytics_abandon_after_h)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get("/graph")
async def get_graph(response: Response) -> dict[str, Any]:
    """静态拓扑（进程内缓存）：DAG 底图。"""
    response.headers["Cache-Control"] = "public, max-age=300"
    return topology()


@router.get("/sessions")
async def list_sessions(
    request: Request,
    response: Response,
    frm: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    outcome: str | None = None,
    reason: str | None = None,
    category: str | None = None,
    sku: str | None = None,
    plan: str | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, Any]:
    _no_store(response)
    return await _queries(request).sessions(
        frm=frm,
        to=to,
        outcome=outcome,
        reason=reason,
        category=category,
        sku=sku,
        plan=plan,
        q=q,
        cursor=cursor,
        limit=limit,
    )


@router.get("/sessions/{session_id}/journey")
async def get_journey(session_id: str, request: Request, response: Response) -> dict[str, Any]:
    """一个会话的完整旅程：会话事实 + 每个 run 的节点轨迹 / 模型 / 检索 + 可用时的原始快照。"""
    _no_store(response)
    journey = await _queries(request).journey(session_id)
    if journey is None:
        raise HTTPException(
            404, detail={"code": "session_not_found", "message": session_id}
        )
    journey["snapshot"] = await _snapshot(request, session_id)
    return journey


async def _snapshot(request: Request, session_id: str) -> dict[str, Any] | None:
    """原始会话还在（未到 TTL）时给出权威快照；否则 None，由前端降级为只显示事实。"""
    store = getattr(request.app.state, "session_store", None)
    graph = getattr(request.app.state, "session_graph", None)
    if store is None or graph is None:
        return None
    try:
        if not await store.session_exists(session_id):
            return None
        from app.sessions.snapshot import build_snapshot

        snap = await build_snapshot(store, graph, session_id)
        return snap.model_dump(mode="json")
    except Exception:  # 快照读不到不影响旅程页
        log.warning("snapshot unavailable session=%s", session_id, exc_info=True)
        return None


@router.get("/metrics/overview")
async def metrics_overview(
    request: Request,
    response: Response,
    frm: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    bucket: Literal["hour", "day"] = "day",
    dim: Literal["category", "sku", "plan", "reason", "emotion", "product_state"] = "category",
) -> dict[str, Any]:
    """经营面板：KPI、趋势、维度分布、模型与检索健康。"""
    _no_store(response)
    return await _queries(request).overview(frm=frm, to=to, bucket=bucket, dim=dim)


@router.get("/metrics/flow")
async def metrics_flow(
    request: Request,
    response: Response,
    frm: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    category: str | None = None,
    outcome: str | None = None,
) -> dict[str, Any]:
    """聚合 DAG：边经过次数、节点中位耗时与中断数、入口节点分布。"""
    _no_store(response)
    return await _queries(request).flow(frm=frm, to=to, category=category, outcome=outcome)


# ---------------------------------------------------------------- 案例库


class CaseIn(BaseModel):
    session_id: str
    run_id: str | None = None
    verdict: Verdict = "review"
    reason_tags: list[str] = Field(default_factory=list)
    note: str | None = Field(default=None, max_length=2000)
    labeled_by: str | None = Field(default=None, max_length=80)


class CasePatch(BaseModel):
    verdict: Verdict | None = None
    reason_tags: list[str] | None = None
    note: str | None = Field(default=None, max_length=2000)
    status: CaseStatus | None = None
    fixed_in: str | None = Field(default=None, max_length=80)


@router.get("/cases")
async def list_cases(
    request: Request,
    response: Response,
    verdict: Verdict | None = None,
    status: CaseStatus | None = None,
    tag: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, Any]:
    _no_store(response)
    queries = _queries(request)
    return {
        "items": await queries.cases(verdict=verdict, status=status, tag=tag, limit=limit),
        "tag_stats": await queries.case_tag_stats(),
        "reason_tags": REASON_TAGS,
    }


@router.post("/cases", status_code=201)
async def upsert_case(body: CaseIn, request: Request, response: Response) -> dict[str, Any]:
    """标注一个会话（一会话一条案例，重复标注即更新）。"""
    _no_store(response)
    unknown = [t for t in body.reason_tags if t not in REASON_TAGS]
    if unknown:
        raise HTTPException(
            422, detail={"code": "unknown_reason_tags", "message": f"{unknown}"}
        )
    queries = _queries(request)
    if await queries.journey(body.session_id) is None:
        raise HTTPException(
            404, detail={"code": "session_not_found", "message": body.session_id}
        )
    row = await _write_case(request, body)
    return row


async def _write_case(request: Request, body: CaseIn) -> dict[str, Any]:
    from psycopg.rows import dict_row

    pool = request.app.state.session_pool
    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            insert into analytics.cases
                (case_id, session_id, run_id, verdict, reason_tags, note, labeled_by, labeled_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (session_id) do update set
                verdict = excluded.verdict, reason_tags = excluded.reason_tags,
                note = excluded.note, labeled_by = excluded.labeled_by,
                run_id = coalesce(excluded.run_id, analytics.cases.run_id)
            returning *
            """,
            (
                uuid.uuid4().hex,
                body.session_id,
                body.run_id,
                body.verdict,
                body.reason_tags,
                body.note,
                body.labeled_by,
                datetime.now(UTC),
            ),
        )
        return dict(await cur.fetchone())


@router.patch("/cases/{case_id}")
async def patch_case(
    case_id: str, body: CasePatch, request: Request, response: Response
) -> dict[str, Any]:
    """改判定 / 标签 / 状态（复盘完成后标 fixed 并记录版本）。"""
    _no_store(response)
    from psycopg.rows import dict_row

    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(422, detail={"code": "empty_patch", "message": "没有要修改的字段"})
    if "reason_tags" in fields:
        unknown = [t for t in fields["reason_tags"] if t not in REASON_TAGS]
        if unknown:
            raise HTTPException(
                422, detail={"code": "unknown_reason_tags", "message": f"{unknown}"}
            )
    assignments = ", ".join(f"{name} = %({name})s" for name in fields)
    pool = request.app.state.session_pool
    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"update analytics.cases set {assignments} where case_id = %(case_id)s returning *",
            {**fields, "case_id": case_id},
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(404, detail={"code": "case_not_found", "message": case_id})
    return dict(row)
