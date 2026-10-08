"""Case aggregate transaction: state, event and human decision commit together."""

import asyncio
from copy import deepcopy
from datetime import datetime
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class CaseConflict(RuntimeError):
    pass


class CaseNotFound(KeyError):
    pass


def _json(row):
    if isinstance(row, dict):
        return {k: _json(v) for k, v in row.items()}
    if isinstance(row, list):
        return [_json(v) for v in row]
    if isinstance(row, (datetime, UUID)):
        return str(row) if isinstance(row, UUID) else row.isoformat()
    return row


class MemoryCaseStore:
    def __init__(self):
        self.rows = {}
        self.lock = asyncio.Lock()
        self.ratings = {}
        self.episodes = {}

    async def open(self, row):
        async with self.lock:
            return deepcopy(
                self.rows.setdefault(row["case_id"], {**row, "events": [], "decisions": []})
            )

    async def get(self, case_id):
        if case_id not in self.rows:
            raise CaseNotFound(case_id)
        return deepcopy(self.rows[case_id])

    async def mutate(self, case_id, fn, expected_revision=None):
        async with self.lock:
            row = await self.get(case_id)
            if expected_revision is not None and row["revision"] != expected_revision:
                raise CaseConflict("案件已变化，请刷新")
            fn(row)
            self.rows[case_id] = row
            return deepcopy(row)

    async def queue(self, status=None, priority=None):
        rows = [
            deepcopy(r)
            for r in self.rows.values()
            if (not status or r["status"] == status) and (not priority or r["priority"] == priority)
        ]
        return sorted(rows, key=lambda r: (not r["complaint_risk"], r["opened_at"]))

    async def rate(self, row):
        async with self.lock:
            self.ratings[(row["session_id"], row["issue_id"])] = deepcopy(row)

    async def record_episode(self, row):
        async with self.lock:
            key = (row["session_id"], row["issue_id"])
            self.episodes[key] = {**self.episodes.get(key, {}), **deepcopy(row)}

    async def metric_rows(self, since):
        return [
            {**r, "rating": self.ratings.get(k, {}).get("score")}
            for k, r in self.episodes.items()
            if r["updated_at"] >= since.isoformat()
        ]


class PostgresCaseStore:
    def __init__(self, pool):
        self.pool = pool

    async def open(self, row):
        async with self.pool.connection() as conn:
            await conn.execute(
                """insert into cases(case_id,session_id,issue_id,sku,category,status,complaint_risk,priority)
                values (%(case_id)s,%(session_id)s,%(issue_id)s,%(sku)s,%(category)s,%(status)s,%(complaint_risk)s,%(priority)s)
                on conflict(session_id,issue_id) do nothing""",
                row,
            )
        return await self.get(row["case_id"])

    async def _read(self, cur, case_id, lock=False):
        await cur.execute(
            "select * from cases where case_id=%s" + (" for update" if lock else ""), (case_id,)
        )
        row = await cur.fetchone()
        if row is None:
            raise CaseNotFound(case_id)
        row = _json(row)
        await cur.execute("select * from case_events where case_id=%s order by seq", (case_id,))
        row["events"] = _json(await cur.fetchall())
        await cur.execute(
            "select * from human_decisions where case_id=%s order by at,decision_id", (case_id,)
        )
        row["decisions"] = _json(await cur.fetchall())
        return row

    async def get(self, case_id):
        async with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            return await self._read(cur, case_id)

    async def mutate(self, case_id, fn, expected_revision=None):
        async with (
            self.pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as cur,
        ):
            row = await self._read(cur, case_id, lock=True)
            if expected_revision is not None and row["revision"] != expected_revision:
                raise CaseConflict("案件已变化，请刷新")
            old_events = len(row["events"])
            old_decisions = {d["decision_id"]: d.get("consumed_input_id") for d in row["decisions"]}
            fn(row)
            values = {**row}
            for field in ("warranty", "proposal", "gate_result", "external_refs"):
                values[field] = Jsonb(row.get(field))
            await cur.execute(
                """update cases set sku=%(sku)s,category=%(category)s,status=%(status)s,complaint_risk=%(complaint_risk)s,priority=%(priority)s,
                warranty=%(warranty)s,proposal=%(proposal)s,chosen_option_id=%(chosen_option_id)s,
                gate_result=%(gate_result)s,owner=%(owner)s,external_refs=%(external_refs)s,updated_at=%(updated_at)s,
                closed_at=%(closed_at)s,reopened_count=%(reopened_count)s,revision=%(revision)s where case_id=%(case_id)s""",
                values,
            )
            for event in row["events"][old_events:]:
                await cur.execute(
                    "insert into case_events(case_id,seq,type,payload,actor,at) values (%s,%s,%s,%s,%s,%s)",
                    (
                        case_id,
                        event["seq"],
                        event["type"],
                        Jsonb(event["payload"]),
                        event["actor"],
                        event["at"],
                    ),
                )
            for decision in row["decisions"]:
                if decision["decision_id"] not in old_decisions:
                    data = decision | {
                        "case_id": case_id,
                        "edited_proposal": Jsonb(decision.get("edited_proposal")),
                    }
                    await cur.execute(
                        """insert into human_decisions(decision_id,case_id,actor,decision,edited_proposal,option_id,override_reason,note,at,consumed_input_id,case_revision)
                        values (%(decision_id)s,%(case_id)s,%(actor)s,%(decision)s,%(edited_proposal)s,%(option_id)s,%(override_reason)s,%(note)s,%(at)s,%(consumed_input_id)s,%(case_revision)s)""",
                        data,
                    )
                elif decision.get("consumed_input_id") != old_decisions[decision["decision_id"]]:
                    await cur.execute(
                        "update human_decisions set consumed_input_id=%s where decision_id=%s",
                        (decision["consumed_input_id"], decision["decision_id"]),
                    )
            return deepcopy(row)

    async def queue(self, status=None, priority=None):
        async with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """select * from cases where (%s::text is null or status=%s) and (%s::text is null or priority=%s)
                order by complaint_risk desc, opened_at limit 200""",
                (status, status, priority, priority),
            )
            return _json(await cur.fetchall())

    async def rate(self, row):
        async with self.pool.connection() as conn:
            await conn.execute(
                """insert into satisfaction_ratings(session_id,issue_id,case_id,score,comment)
                values (%(session_id)s,%(issue_id)s,%(case_id)s,%(score)s,%(comment)s)
                on conflict(session_id,issue_id) do update set score=excluded.score,comment=excluded.comment,at=now()""",
                row,
            )

    async def record_episode(self, row):
        async with self.pool.connection() as conn:
            await conn.execute(
                """insert into service_episodes(episode_id,session_id,issue_id,case_id,outcome,human_involved,source,updated_at)
                values (%(episode_id)s,%(session_id)s,%(issue_id)s,%(case_id)s,%(outcome)s,%(human_involved)s,%(source)s,%(updated_at)s)
                on conflict(episode_id) do update set outcome=excluded.outcome,human_involved=excluded.human_involved,
                case_id=excluded.case_id,updated_at=excluded.updated_at""",
                row,
            )

    async def metric_rows(self, since):
        from app.analytics.l3 import METRIC_ROWS_SQL

        async with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                METRIC_ROWS_SQL + " where e.updated_at >= %s",
                (since,),
            )
            return _json(await cur.fetchall())
