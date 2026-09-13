"""把观测台上线之前的历史会话补成 analytics 事实（幂等，可反复跑）。

三个来源，都不改动原数据：
- `session_events`：run 边界（run_started / done）、结果、错误码、首可见 / 首卡延迟（事件落库时刻之差，
  与在线口径同一事件、同一时刻，差别只有数据库写入的亚毫秒）；
- `checkpoint_writes.task_path` + `checkpoints.metadata->>'step'`：节点执行序列。节点按 step 排序后
  依次落到各 run 的 version 区间（run 结束时 version = step + 1），因此跨 run 的归属是推导的，
  **没有耗时**（历史 checkpoint 不记时间），duration_ms 留空；
- LangGraph checkpoint 状态：会话事实（结果分类、产品、计划、步骤数……）。

模型 / 检索事实来自结构化日志 JSONL（--logs）；日志已轮转的部分补不回来，属已知缺口。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.analytics import derive, hooks
from app.analytics.schema import NodeRun, RunFacts
from app.analytics.store import AnalyticsStore, Op

log = logging.getLogger("analytics.backfill")

BATCH = 200


@dataclass
class Stats:
    sessions: int = 0
    runs: int = 0
    nodes: int = 0
    model_calls: int = 0
    retrieval_calls: int = 0
    sessions_without_nodes: int = 0

    def as_dict(self) -> dict[str, int]:
        return self.__dict__.copy()


@dataclass
class _Run:
    run_id: str
    started_at: datetime
    ended_at: datetime | None = None
    version: int = 0
    done_reason: str | None = None
    error_code: str | None = None
    entry: str = "message"
    first_visible_ms: int | None = None
    card_ready_ms: int | None = None
    card_kind: str | None = None
    stage_from: str | None = None
    stage_to: str | None = None
    nodes: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.nodes = []


def runs_from_events(records: list[dict[str, Any]]) -> list[_Run]:
    """按 seq 重放事件，折出每个 run 的边界与指标。records: {run_id, created_at, event_json}。"""
    runs: dict[str, _Run] = {}
    order: list[str] = []
    for rec in records:
        event, at, run_id = rec["event_json"], rec["created_at"], rec["run_id"]
        kind = event.get("type")
        if kind == "run_started":
            runs[run_id] = _Run(
                run_id=run_id,
                started_at=at,
                entry="action:resumed" if event.get("resumed") else "message",
            )
            order.append(run_id)
            continue
        run = runs.get(run_id)
        if run is None:  # 没有 run_started 的残缺 run（进程中途挂掉）
            run = runs[run_id] = _Run(run_id=run_id, started_at=at)
            order.append(run_id)
        elapsed = int((at - run.started_at).total_seconds() * 1000)
        if kind == "progress":
            if run.stage_from is None:
                run.stage_from = event.get("stage")
            run.stage_to = event.get("stage") or run.stage_to
        elif kind == "message" and (event.get("delta") or "").strip():
            run.first_visible_ms = run.first_visible_ms or elapsed
        elif kind in ("step_card", "product_card", "receipt_card"):
            if run.card_ready_ms is None:
                run.card_ready_ms, run.card_kind = elapsed, kind
        elif kind == "error":
            run.error_code = event.get("code")
        elif kind == "done":
            run.ended_at = at
            run.done_reason = event.get("reason")
            run.version = int(event.get("version") or 0)
    return [runs[r] for r in order]


def assign_nodes(runs: list[_Run], steps: list[tuple[int, str]]) -> None:
    """把 (step, node) 序列按 version 区间分给各 run。

    run 结束时 version = 最新 checkpoint 的 step + 1，故 step s 的节点属于第一个满足 s + 1 <= version
    的 run；末尾多出来的节点归最后一个 run。
    """
    if not runs:
        return
    i = 0
    for step, node in sorted(steps):
        while i < len(runs) - 1 and runs[i].version and step + 1 > runs[i].version:
            i += 1
        runs[i].nodes.append(node)


class Backfiller:
    def __init__(self, pool: AsyncConnectionPool, store: AnalyticsStore, graph: Any = None) -> None:
        self._pool = pool
        self._store = store
        self._graph = graph

    async def session_ids(self, since: datetime | None = None) -> list[str]:
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """select distinct session_id from session_events
                   where %s::timestamptz is null or created_at >= %s order by 1""",
                (since, since),
            )
            return [r["session_id"] for r in await cur.fetchall()]

    async def _events(self, session_id: str) -> list[dict[str, Any]]:
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """select run_id, created_at, event_json from session_events
                   where session_id = %s order by seq""",
                (session_id,),
            )
            return list(await cur.fetchall())

    async def _node_steps(self, session_id: str) -> list[tuple[int, str]]:
        """(step, node)：node 取 task_path 里 `~__pregel_pull, <node>` 的节点名，__start__ 不算执行。"""
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """select distinct (c.metadata->>'step')::int as step, w.task_path, w.task_id
                   from checkpoint_writes w
                   join checkpoints c
                     on c.thread_id = w.thread_id
                    and c.checkpoint_ns = w.checkpoint_ns
                    and c.checkpoint_id = w.checkpoint_id
                   where w.thread_id = %s and w.checkpoint_ns = ''
                   order by step""",
                (session_id,),
            )
            rows = await cur.fetchall()
        out: list[tuple[int, str]] = []
        for row in rows:
            node = str(row["task_path"] or "").rsplit(",", 1)[-1].strip()
            if node and node != "__start__" and row["step"] is not None:
                out.append((int(row["step"]), node))
        return out

    async def session(self, session_id: str, stats: Stats, *, store_text: bool = True) -> list[Op]:
        records = await self._events(session_id)
        if not records:
            return []
        runs = runs_from_events(records)
        assign_nodes(runs, await self._node_steps(session_id))
        ops: list[Op] = []
        for seq_no, run in enumerate(runs, start=1):
            prev: str | None = None
            for idx, node in enumerate(run.nodes, start=1):
                ops.append(
                    (
                        "node_run",
                        NodeRun(
                            session_id=session_id,
                            run_id=run.run_id,
                            idx=idx,
                            node=node,
                            prev_node=prev,
                            started_at=run.started_at,
                            duration_ms=None,  # 历史 checkpoint 没有时间戳
                            status="ok",
                            summary={"backfilled": True},
                        ),
                    )
                )
                prev = node
            stats.nodes += len(run.nodes)
            ops.append(
                (
                    "run_facts",
                    RunFacts(
                        run_id=run.run_id,
                        session_id=session_id,
                        seq_no=seq_no,
                        started_at=run.started_at,
                        ended_at=run.ended_at,
                        duration_ms=int((run.ended_at - run.started_at).total_seconds() * 1000)
                        if run.ended_at
                        else None,
                        entry=run.entry,
                        stage_from=run.stage_from,
                        stage_to=run.stage_to,
                        done_reason=run.done_reason,
                        error_code=run.error_code,
                        first_visible_ms=run.first_visible_ms,
                        card_ready_ms=run.card_ready_ms,
                        card_kind=run.card_kind,
                        node_count=len(run.nodes),
                    ),
                )
            )
        stats.runs += len(runs)
        if not any(r.nodes for r in runs):
            stats.sessions_without_nodes += 1

        values = await self._state(session_id)
        last = runs[-1]
        ops.append(
            (
                "session_facts",
                derive.session_facts(
                    session_id,
                    values,
                    lane=None,
                    done_reason=last.done_reason,
                    error_code=last.error_code,
                    pending=_pending_from_events(records),
                    runs=len(runs),
                    created_at=runs[0].started_at,
                    last_run_at=last.ended_at or last.started_at,
                    total_latency_ms=sum(
                        int((r.ended_at - r.started_at).total_seconds() * 1000)
                        for r in runs
                        if r.ended_at
                    ),
                    store_text=store_text,
                ),
            )
        )
        stats.sessions += 1
        return ops

    async def _state(self, session_id: str) -> dict[str, Any]:
        if self._graph is None:
            return {}
        try:
            state = await self._graph.aget_state({"configurable": {"thread_id": session_id}})
            return dict(state.values or {})
        except Exception:  # noqa: BLE001 - checkpoint 已被 TTL 清掉属正常
            log.debug("no checkpoint for %s", session_id)
            return {}

    async def logs(self, paths: list[Path], stats: Stats) -> list[Op]:
        """从结构化日志补模型 / 检索事实。逐行解析，坏行跳过。"""
        ops: list[Op] = []
        for path in paths:
            if not path.exists():
                continue
            with path.open(encoding="utf-8") as lines:
                for line in lines:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(row, dict):
                        continue
                    event = row.get("event")
                    if event == "model_call":
                        ops.append(("model_call", hooks._model_call(row)))
                        stats.model_calls += 1
                    elif event == "knowledge_search":
                        ops.append(("retrieval_call", hooks._retrieval_call(row)))
                        stats.retrieval_calls += 1
        # 日志回填不该污染在线 run 的计数器
        hooks._counters.clear()
        return ops

    async def run(
        self,
        *,
        since: datetime | None = None,
        log_paths: list[Path] | None = None,
        store_text: bool = True,
    ) -> Stats:
        stats = Stats()
        pending: list[Op] = []
        for session_id in await self.session_ids(since):
            pending.extend(await self.session(session_id, stats, store_text=store_text))
            if len(pending) >= BATCH:
                await self._store.write(pending)
                pending = []
        if log_paths:
            pending.extend(await self.logs(log_paths, stats))
        for start in range(0, len(pending), BATCH):
            await self._store.write(pending[start : start + BATCH])
        return stats


def _pending_from_events(records: list[dict[str, Any]]) -> bool:
    """最后一个 run 以 awaiting_input 结束即视为在等用户。"""
    for rec in reversed(records):
        kind = rec["event_json"].get("type")
        if kind == "done":
            return rec["event_json"].get("reason") == "awaiting_input"
    return False


def rotated(path: Path) -> list[Path]:
    """events.jsonl + 轮转备份 events.jsonl.1/.2/.3。"""
    return [path, *sorted(path.parent.glob(f"{path.name}.*"))]
