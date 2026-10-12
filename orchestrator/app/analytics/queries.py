"""观测台的只读查询。全部参数化，不拼字符串；每条查询都走索引或按天聚合。

两个只在查询期成立的口径（不写回库，改阈值不用重算）：
- `abandoned`：未终结且超过 ANALYTICS_ABANDON_AFTER_H 没有新 run；
- 解决率的分母只算「系统该负责」的结局，`unknown` / `interrupted` 不进分子也不进分母（§8）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.analytics.derive import POLICY_RULES, SYSTEM_FAILURE_RULES

# 未终结但久无动静 → abandoned；unknown / interrupted 原样保留
EFFECTIVE_OUTCOME = """
case when f.outcome in ('awaiting_user', 'clarifying', 'in_progress')
      and f.last_run_at < now() - (%(abandon_h)s::float * interval '1 hour')
     then 'abandoned' else f.outcome end
"""

# 解决率：分子 resolved，分母 = resolved + 系统原因升级 + 放弃在排障途中的
SYSTEM_ESCALATIONS = tuple(sorted(SYSTEM_FAILURE_RULES))
POLICY_ESCALATIONS = tuple(sorted(POLICY_RULES))

MAX_LIMIT = 100


def _window(frm: datetime | None, to: datetime | None) -> tuple[datetime, datetime]:
    end = to or datetime.now(UTC)
    return (frm or end - timedelta(days=7)), end


class Queries:
    def __init__(self, pool: AsyncConnectionPool, *, abandon_after_h: float = 6.0) -> None:
        self._pool = pool
        self._abandon_h = abandon_after_h

    async def _rows(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            # 管理端查询不得拖垮在线接口
            await cur.execute("set local statement_timeout = '5s'")
            await cur.execute(sql, {"abandon_h": self._abandon_h, **params})
            return [dict(r) for r in await cur.fetchall()]

    async def _one(self, sql: str, params: dict[str, Any]) -> dict[str, Any] | None:
        rows = await self._rows(sql, params)
        return rows[0] if rows else None

    # ------------------------------------------------------------------ 会话列表

    async def sessions(
        self,
        *,
        frm: datetime | None = None,
        to: datetime | None = None,
        outcome: str | None = None,
        reason: str | None = None,
        category: str | None = None,
        sku: str | None = None,
        plan: str | None = None,
        q: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """按 last_run_at 倒序的 keyset 分页；cursor 为上一页最后一行的 `last_run_at|session_id`。"""
        start, end = _window(frm, to)
        params: dict[str, Any] = {
            "start": start,
            "end": end,
            "limit": min(limit, MAX_LIMIT) + 1,
            "outcome": outcome,
            "reason": reason,
            "category": category,
            "sku": sku,
            "plan": plan,
            "q": f"%{q}%" if q else None,
            "cur_at": None,
            "cur_id": None,
        }
        if cursor and "|" in cursor:
            at, _, sid = cursor.partition("|")
            try:
                params["cur_at"], params["cur_id"] = datetime.fromisoformat(at), sid
            except ValueError:
                pass
        rows = await self._rows(
            f"""
            select f.session_id, f.created_at, f.last_run_at, f.runs, f.first_question,
                   f.sku, f.category, f.product_state, f.emotion_level, f.steps_executed,
                   f.knowledge_status, f.outcome_reason, f.model_calls,
                   f.tokens_in + f.tokens_out as tokens, f.total_latency_ms,
                   f.fault_plan_ids, f.raw_available_until > now() as raw_available,
                   {EFFECTIVE_OUTCOME} as outcome,
                   c.verdict as case_verdict, c.reason_tags as case_tags
            from analytics.session_facts f
            left join analytics.cases c on c.session_id = f.session_id
            where f.last_run_at between %(start)s and %(end)s
              and (%(outcome)s::text is null or {EFFECTIVE_OUTCOME} = %(outcome)s)
              and (%(reason)s::text is null or f.outcome_reason = %(reason)s)
              and (%(category)s::text is null or f.category = %(category)s)
              and (%(sku)s::text is null or f.sku = %(sku)s)
              and (%(plan)s::text is null or %(plan)s = any(f.fault_plan_ids))
              and (%(q)s::text is null or f.first_question ilike %(q)s)
              and (%(cur_at)s::timestamptz is null
                   or (f.last_run_at, f.session_id) < (%(cur_at)s, %(cur_id)s))
            order by f.last_run_at desc, f.session_id desc
            limit %(limit)s
            """,
            params,
        )
        limit = min(limit, MAX_LIMIT)
        has_more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = (
            f"{rows[-1]['last_run_at'].isoformat()}|{rows[-1]['session_id']}"
            if has_more and rows
            else None
        )
        return {"items": rows, "next_cursor": next_cursor}

    # ------------------------------------------------------------------ 会话旅程

    async def journey(self, session_id: str) -> dict[str, Any] | None:
        facts = await self._one(
            f"""select f.*, {EFFECTIVE_OUTCOME} as outcome,
                       f.raw_available_until > now() as raw_available
                from analytics.session_facts f where f.session_id = %(sid)s""",
            {"sid": session_id},
        )
        if facts is None:
            return None
        runs = await self._rows(
            """select * from analytics.run_facts where session_id = %(sid)s
               order by seq_no, started_at""",
            {"sid": session_id},
        )
        nodes = await self._rows(
            """select run_id, idx, node, prev_node, started_at, duration_ms, status, summary
               from analytics.node_runs where session_id = %(sid)s order by run_id, idx""",
            {"sid": session_id},
        )
        models = await self._rows(
            """select run_id, node, task, model_used, lane, status, attempts, fallback_used,
                      stream, latency_ms, tokens_in, tokens_out, error_type, created_at
               from analytics.model_calls where session_id = %(sid)s order by created_at""",
            {"sid": session_id},
        )
        retrievals = await self._rows(
            """select run_id, node, round, kb, status, allowed_count, hits, top_score,
                      latency_ms, query, created_at
               from analytics.retrieval_calls where session_id = %(sid)s order by created_at""",
            {"sid": session_id},
        )
        case = await self._one(
            "select * from analytics.cases where session_id = %(sid)s", {"sid": session_id}
        )
        by_run: dict[str, dict[str, list]] = {}
        for run in runs:
            by_run[run["run_id"]] = {"nodes": [], "model_calls": [], "retrieval_calls": []}
        for row in nodes:
            by_run.setdefault(
                row["run_id"], {"nodes": [], "model_calls": [], "retrieval_calls": []}
            )["nodes"].append(row)
        for row in models:
            bucket = by_run.get(row["run_id"])
            if bucket is not None:
                bucket["model_calls"].append(row)
        for row in retrievals:
            bucket = by_run.get(row["run_id"])
            if bucket is not None:
                bucket["retrieval_calls"].append(row)
        for run in runs:
            run.update(by_run.get(run["run_id"], {}))
        return {"session": facts, "runs": runs, "case": case}

    # ------------------------------------------------------------------ 经营面板

    async def overview(
        self,
        *,
        frm: datetime | None = None,
        to: datetime | None = None,
        bucket: str = "day",
        dim: str = "category",
    ) -> dict[str, Any]:
        start, end = _window(frm, to)
        params = {"start": start, "end": end, "bucket": "hour" if bucket == "hour" else "day"}
        totals = await self._one(
            f"""
            with s as (
                select {EFFECTIVE_OUTCOME} as outcome, f.outcome_reason, f.steps_executed,
                       f.model_calls, f.tokens_in, f.tokens_out, f.runs
                from analytics.session_facts f
                where f.last_run_at between %(start)s and %(end)s
            )
            select count(*) as sessions,
                   count(*) filter (where outcome = 'resolved') as resolved,
                   count(*) filter (where outcome = 'closed_unresolved') as closed_unresolved,
                   count(*) filter (where outcome = 'escalated') as escalated,
                   count(*) filter (where outcome = 'escalated'
                                      and outcome_reason = any(%(system)s)) as escalated_system,
                   count(*) filter (where outcome = 'escalated'
                                      and outcome_reason = any(%(policy)s)) as escalated_policy,
                   count(*) filter (where outcome = 'abandoned') as abandoned,
                   count(*) filter (where outcome = 'awaiting_user') as awaiting_user,
                   count(*) filter (where outcome = 'clarifying') as clarifying,
                   count(*) filter (where outcome = 'errored') as errored,
                   count(*) filter (where outcome = 'interrupted') as interrupted,
                   count(*) filter (where outcome = 'unknown') as unknown,
                   coalesce(sum(model_calls), 0) as model_calls,
                   coalesce(sum(tokens_in), 0) as tokens_in,
                   coalesce(sum(tokens_out), 0) as tokens_out,
                   coalesce(avg(runs), 0)::numeric(10,2) as avg_runs,
                   coalesce(avg(steps_executed), 0)::numeric(10,2) as avg_steps
            from s
            """,
            {**params, "system": list(SYSTEM_ESCALATIONS), "policy": list(POLICY_ESCALATIONS)},
        )
        latency = await self._one(
            """
            select percentile_disc(0.5) within group (order by first_visible_ms)
                     filter (where first_visible_ms is not null) as first_visible_p50,
                   percentile_disc(0.95) within group (order by first_visible_ms)
                     filter (where first_visible_ms is not null) as first_visible_p95,
                   percentile_disc(0.5) within group (order by card_ready_ms)
                     filter (where card_ready_ms is not null) as card_ready_p50,
                   percentile_disc(0.95) within group (order by card_ready_ms)
                     filter (where card_ready_ms is not null) as card_ready_p95,
                   count(*) as runs,
                   count(*) filter (where done_reason = 'error') as runs_errored,
                   count(*) filter (where done_reason = 'cancelled') as runs_cancelled
            from analytics.run_facts where started_at between %(start)s and %(end)s
            """,
            params,
        )
        series = await self._rows(
            f"""
            select date_trunc(%(bucket)s, f.last_run_at) as at,
                   count(*) as sessions,
                   count(*) filter (where {EFFECTIVE_OUTCOME} = 'resolved') as resolved,
                   count(*) filter (where {EFFECTIVE_OUTCOME} = 'escalated') as escalated
            from analytics.session_facts f
            where f.last_run_at between %(start)s and %(end)s
            group by 1 order by 1
            """,
            params,
        )
        models = await self._rows(
            """
            select task, model_used,
                   count(*) as calls,
                   count(*) filter (where status <> 'ok') as errors,
                   count(*) filter (where fallback_used) as fallbacks,
                   percentile_disc(0.95) within group (order by latency_ms)
                     filter (where latency_ms is not null) as p95_ms,
                   coalesce(sum(tokens_in), 0) as tokens_in,
                   coalesce(sum(tokens_out), 0) as tokens_out
            from analytics.model_calls where created_at between %(start)s and %(end)s
            group by 1, 2 order by calls desc limit 30
            """,
            params,
        )
        retrieval = await self._rows(
            """
            select kb, status, count(*) as n
            from analytics.retrieval_calls where created_at between %(start)s and %(end)s
            group by 1, 2 order by 1, 3 desc
            """,
            params,
        )
        return {
            "window": {"from": start, "to": end, "bucket": params["bucket"]},
            "totals": totals or {},
            "latency": latency or {},
            "rates": _rates(totals or {}),
            "series": series,
            "breakdown": await self.breakdown(dim, frm=start, to=end),
            "models": models,
            "retrieval": retrieval,
        }

    async def breakdown(
        self, dim: str, *, frm: datetime | None = None, to: datetime | None = None
    ) -> list[dict[str, Any]]:
        """按维度分组的会话数与结局。dim ∈ category|sku|plan|reason|emotion|product_state。"""
        start, end = _window(frm, to)
        column = {
            "category": "coalesce(f.category, '(未识别)')",
            "sku": "coalesce(f.sku, '(未确认)')",
            "reason": "coalesce(f.outcome_reason, '(无)')",
            "emotion": "coalesce(f.emotion_level, '(未知)')",
            "product_state": "coalesce(f.product_state, '(未知)')",
        }.get(dim)
        source = "analytics.session_facts f"
        if column is None:  # plan：一会话可命中多个计划，展开统计
            column, source = (
                "plan",
                "analytics.session_facts f cross join unnest(f.fault_plan_ids) as plan",
            )
        return await self._rows(
            f"""
            select {column} as value, count(*) as sessions,
                   count(*) filter (where {EFFECTIVE_OUTCOME} = 'resolved') as resolved,
                   count(*) filter (where {EFFECTIVE_OUTCOME} = 'escalated') as escalated
            from {source}
            where f.last_run_at between %(start)s and %(end)s
            group by 1 order by sessions desc limit 30
            """,
            {"start": start, "end": end},
        )

    # ------------------------------------------------------------------ DAG 聚合流量

    async def flow(
        self,
        *,
        frm: datetime | None = None,
        to: datetime | None = None,
        category: str | None = None,
        outcome: str | None = None,
    ) -> dict[str, Any]:
        """边计数与节点耗时：边宽 = 经过次数，节点色 = 中位耗时 / 错误率。

        avg_step 是节点在一轮里的平均步序（node_runs.idx），前端据此按实际先后排列。
        """
        start, end = _window(frm, to)
        params = {"start": start, "end": end, "category": category, "outcome": outcome}
        scope = f"""
            from analytics.node_runs n
            join analytics.session_facts f on f.session_id = n.session_id
            where n.started_at between %(start)s and %(end)s
              and (%(category)s::text is null or f.category = %(category)s)
              and (%(outcome)s::text is null or {EFFECTIVE_OUTCOME} = %(outcome)s)
        """
        edges = await self._rows(
            f"""select n.prev_node as source, n.node as target, count(*) as n
                {scope} and n.prev_node is not null
                group by 1, 2 order by n desc""",
            params,
        )
        nodes = await self._rows(
            f"""select n.node, count(*) as n,
                       round(avg(n.idx)::numeric, 2)::float as avg_step,
                       count(*) filter (where n.status = 'error') as errors,
                       count(*) filter (where n.status = 'interrupt') as interrupts,
                       percentile_disc(0.5) within group (order by n.duration_ms)
                         filter (where n.duration_ms is not null) as p50_ms
                {scope}
                group by 1 order by n desc""",
            params,
        )
        entries = await self._rows(
            f"""select n.node, count(*) as n {scope} and n.prev_node is null
                group by 1 order by n desc""",
            params,
        )
        return {"edges": edges, "nodes": nodes, "entries": entries}

    # ------------------------------------------------------------------ 案例库

    async def cases(
        self,
        *,
        verdict: str | None = None,
        status: str | None = None,
        tag: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return await self._rows(
            f"""
            select c.*, f.first_question, f.category, f.sku, f.outcome_reason,
                   {EFFECTIVE_OUTCOME} as outcome
            from analytics.cases c
            left join analytics.session_facts f on f.session_id = c.session_id
            where (%(verdict)s::text is null or c.verdict = %(verdict)s)
              and (%(status)s::text is null or c.status = %(status)s)
              and (%(tag)s::text is null or %(tag)s = any(c.reason_tags))
            order by c.labeled_at desc limit %(limit)s
            """,
            {
                "verdict": verdict,
                "status": status,
                "tag": tag,
                "limit": min(limit, MAX_LIMIT),
            },
        )

    async def case_tag_stats(self) -> list[dict[str, Any]]:
        return await self._rows(
            """select tag as value, count(*) as n
               from analytics.cases c cross join unnest(c.reason_tags) as tag
               where c.verdict <> 'good' group by 1 order by n desc""",
            {},
        )


def _rates(totals: dict[str, Any]) -> dict[str, float | None]:
    """解决率的两个口径（§8）。分母为 0 时返回 None，不返回 0——没有数据不等于 0%。"""
    resolved = int(totals.get("resolved") or 0)
    system = int(totals.get("escalated_system") or 0)
    abandoned = int(totals.get("abandoned") or 0)
    escalated = int(totals.get("escalated") or 0)
    unresolved = int(totals.get("closed_unresolved") or 0)
    self_denom = resolved + system + abandoned + unresolved
    closed_denom = resolved + escalated + unresolved
    return {
        # 系统该负责的部分里，自己解决掉的比例
        "self_service": round(resolved / self_denom, 4) if self_denom else None,
        # 有明确结局（解决或转人工）的会话里，解决掉的比例
        "closure": round(resolved / closed_denom, 4) if closed_denom else None,
        "escalation": round(escalated / closed_denom, 4) if closed_denom else None,
    }
