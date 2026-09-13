"""Optional extractive history cache. Events/checkpoints remain authoritative.

No model call in the request path. Each excerpt is complete and source-labelled;
corrections invalidate the cache by context revision, and CAS cannot resurrect a session.
"""

import asyncio
import copy
from datetime import UTC, datetime, timedelta

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.context.builder import estimate_tokens
from app.context.config import conversation_config
from app.conversation.history import fold_history
from app.conversation.reduce import stable_id
from app.settings import settings


def extract_summary(entries):
    cfg = conversation_config()
    groups = {}
    for entry in entries:
        if (
            entry.kind == "message"
            and entry.status == "completed"
            and entry.processing_status not in {"failed", "cancelled"}
        ):
            groups.setdefault(entry.run_id, []).append(entry)
    if len(groups) < cfg.summary_after_turns:
        return None
    selected, used = [], 0
    for group in list(groups.values())[: -cfg.recent_turns]:
        # Only completed Q/A groups are eligible; never summarize an accepted in-flight input.
        if not any(e.role == "assistant" for e in group):
            continue
        block = "\n".join(f"[{e.entry_id} | {e.recorded_at} | {e.role}] {e.text}" for e in group)
        cost = estimate_tokens(block)
        if used + cost <= cfg.summary_max_tokens:
            selected.extend(group)
            used += cost
    if not selected:
        return None
    return {
        "text": "\n".join(
            f"[{e.entry_id} | {e.recorded_at} | {e.role}] {e.text}" for e in selected
        ),
        "source_entry_ids": [e.entry_id for e in selected],
        "through_seq": max(e.last_seq for e in selected),
    }


class SummaryCache:
    def __init__(self, store, graph):
        self.store, self.graph = store, graph
        self.tasks = {}
        if not hasattr(store, "_summary_cache"):
            store._summary_cache = {}

    def schedule(self, sid):
        if sid not in self.tasks:
            task = asyncio.create_task(self.refresh(sid), name=f"summary-{sid}")
            self.tasks[sid] = task

            def finished(t):
                self.tasks.pop(sid, None)
                if not t.cancelled():
                    t.exception()  # consume failure; cache is optional

            task.add_done_callback(finished)

    async def refresh(self, sid):
        from app.sessions.store import SessionNotFound

        try:
            async with self.store.snapshot_view(sid) as (row, records):
                if not row.published_checkpoint_id or row.active_run_id:
                    return False
                state = await self.graph.aget_state(
                    {
                        "configurable": {
                            "thread_id": sid,
                            "checkpoint_id": row.published_checkpoint_id,
                        }
                    }
                )
                revision = state.values.get("context_revision", 0)
            candidate = extract_summary(fold_history(sid, records))
            if candidate is None:
                return False
            candidate.update(
                session_id=sid,
                summary_id=stable_id(sid, row.version, "history_summary"),
                source_context_revision=revision,
                generated_at=datetime.now(UTC).isoformat(),
                status="active",
                expires_at=(
                    row.updated_at + timedelta(hours=settings.retention_session_hours)
                ).isoformat(),
            )
            return await self.save(candidate, row.published_checkpoint_id)
        except SessionNotFound:
            return False

    async def save(self, candidate, checkpoint_id):
        sid = candidate["session_id"]
        if hasattr(self.store, "_pool"):
            async with (
                self.store._pool.connection() as conn,
                conn.transaction(),
                conn.cursor(row_factory=dict_row) as cur,
            ):
                await cur.execute(
                    "select published_checkpoint_id,updated_at from sessions where session_id=%s for update",
                    (sid,),
                )
                row = await cur.fetchone()
                if (
                    not row
                    or row["published_checkpoint_id"] != checkpoint_id
                    or datetime.fromisoformat(candidate["expires_at"]) <= datetime.now(UTC)
                ):
                    return False
                await cur.execute("delete from conversation_summaries where session_id=%s", (sid,))
                data = dict(candidate, source_entry_ids=Jsonb(candidate["source_entry_ids"]))
                await cur.execute(
                    """insert into conversation_summaries(session_id,summary_id,through_seq,source_context_revision,source_entry_ids,text,generated_at,status,expires_at)
                    values (%(session_id)s,%(summary_id)s,%(through_seq)s,%(source_context_revision)s,%(source_entry_ids)s,%(text)s,%(generated_at)s,%(status)s,%(expires_at)s)""",
                    data,
                )
                return True
        async with self.store._lock:
            mem = self.store._sessions.get(sid)
            if (
                not mem
                or not mem.row
                or mem.row.published_checkpoint_id != checkpoint_id
                or datetime.fromisoformat(candidate["expires_at"]) <= datetime.now(UTC)
            ):
                return False
            self.store._summary_cache[sid] = copy.deepcopy(candidate)
            return True

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def read_summary(store, sid, revision, before_seq):
    if hasattr(store, "_pool"):
        async with store._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """select c.* from conversation_summaries c join sessions s using(session_id)
                where c.session_id=%s and c.source_context_revision=%s and c.through_seq<%s and c.expires_at>now() and c.status='active'
                order by c.generated_at desc limit 1""",
                (sid, revision, before_seq),
            )
            row = await cur.fetchone()
    else:
        row = copy.deepcopy(getattr(store, "_summary_cache", {}).get(sid))
        if row and (
            row["source_context_revision"] != revision
            or row["through_seq"] >= before_seq
            or datetime.fromisoformat(row["expires_at"]) <= datetime.now(UTC)
        ):
            row = None
    if not row:
        return None
    return {
        k: row[k]
        for k in (
            "summary_id",
            "through_seq",
            "source_context_revision",
            "source_entry_ids",
            "text",
        )
    }
