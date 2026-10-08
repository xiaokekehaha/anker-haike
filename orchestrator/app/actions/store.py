"""Durable idempotency claims with bounded lease takeover and fencing tokens."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

CASE_COLUMNS = (
    "execution_id", "action_kind", "status", "receipt", "error", "gate_result",
    "actions_version", "started_at",
)


class ExecutionBusy(RuntimeError):
    pass


class ExecutionNeedsReview(ExecutionBusy):
    """A lease already taken over once went stale again; a person must check the outcome."""


class IdempotencyConflict(RuntimeError):
    pass


def _validate_reuse(old, new):
    if any(old.get(k) != new.get(k) for k in ("action_kind", "request", "case_id", "session_id")):
        raise IdempotencyConflict("同一幂等键不能用于不同请求")


def _claim(old, new, timeout_ms):
    if old is None:
        return {
            **deepcopy(new),
            "status": "running",
            "attempt": 1,
            "started_at": datetime.now(UTC),
            "receipt": None,
            "error": None,
        }, True
    _validate_reuse(old, new)
    if old["status"] == "succeeded":
        return old, False
    if old["status"] == "running" and old["started_at"] + timedelta(
        milliseconds=timeout_ms
    ) > datetime.now(UTC):
        raise ExecutionBusy("相同动作仍在执行")
    # A single recovery of an expired lease; the retry looks the order up by client_ref first.
    if old["status"] == "running" and old["attempt"] >= 2:
        raise ExecutionNeedsReview("执行状态需人工核实")
    if old["status"] == "failed" and not (old.get("error") or {}).get("recoverable"):
        return old, False
    return {
        **old,
        "status": "running",
        "attempt": old["attempt"] + 1,
        "started_at": datetime.now(UTC),
        "error": None,
    }, True


class MemoryExecutionStore:
    def __init__(self):
        self.rows = {}
        self.lock = asyncio.Lock()

    async def get(self, key):
        return deepcopy(self.rows.get(key))

    async def claim(self, row, timeout_ms):
        async with self.lock:
            value, acquired = _claim(self.rows.get(row["idempotency_key"]), row, timeout_ms)
            self.rows[row["idempotency_key"]] = value
            return deepcopy(value), acquired

    async def for_case(self, case_id):
        rows = sorted((r for r in self.rows.values() if r.get("case_id") == case_id), key=lambda r: r["started_at"])
        return [
            {k: r.get(k) for k in CASE_COLUMNS} | {"started_at": r["started_at"].isoformat()} for r in rows
        ]

    async def finish(self, key, attempt, status, receipt, error):
        async with self.lock:
            row = self.rows[key]
            if row["attempt"] != attempt or row["status"] != "running":
                raise ExecutionBusy("执行租约已变更")
            row.update(status=status, receipt=receipt, error=error, finished_at=datetime.now(UTC))


class PostgresExecutionStore:
    def __init__(self, pool):
        self.pool = pool

    async def get(self, key):
        async with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("select * from action_executions where idempotency_key=%s", (key,))
            row = await cur.fetchone()
            if row:
                for name in ("case_id", "execution_id"):
                    if row[name] is not None:
                        row[name] = str(row[name])
            return row

    async def for_case(self, case_id):
        async with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                f"select {','.join(CASE_COLUMNS)} from action_executions where case_id=%s order by started_at",
                (case_id,),
            )
            rows = await cur.fetchall()
        return [r | {"execution_id": str(r["execution_id"]), "started_at": r["started_at"].isoformat()} for r in rows]

    async def claim(self, row, timeout_ms):
        async with (
            self.pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as cur,
        ):
            # Lock even when no row exists, including concurrent first inserts.
            await cur.execute(
                "select pg_advisory_xact_lock(hashtextextended(%s,0))", (row["idempotency_key"],)
            )
            await cur.execute(
                "select * from action_executions where idempotency_key=%s for update",
                (row["idempotency_key"],),
            )
            old = await cur.fetchone()
            if old:
                old["case_id"] = str(old["case_id"]) if old["case_id"] else None
                old["execution_id"] = str(old["execution_id"])
            value, acquired = _claim(old, row, timeout_ms)
            if not acquired:
                return value, False
            if old is None:
                values = {**value}
                for field in ("request", "gate_result"):
                    values[field] = Jsonb(values.get(field))
                await cur.execute(
                    """insert into action_executions(execution_id,case_id,session_id,issue_id,run_id,action_kind,idempotency_key,request,gate_result,status,actions_version,started_at)
                    values (%(execution_id)s,%(case_id)s,%(session_id)s,%(issue_id)s,%(run_id)s,%(action_kind)s,%(idempotency_key)s,%(request)s,%(gate_result)s,'running',%(actions_version)s,%(started_at)s)""",
                    values,
                )
            else:
                if old["status"] == "running":
                    await cur.execute(
                        "update action_executions set status='stale' where idempotency_key=%s",
                        (row["idempotency_key"],),
                    )
                await cur.execute(
                    "update action_executions set status='running',attempt=%s,started_at=%s,error=null,finished_at=null where idempotency_key=%s",
                    (value["attempt"], value["started_at"], row["idempotency_key"]),
                )
            return value, True

    async def finish(self, key, attempt, status, receipt, error):
        async with self.pool.connection() as conn:
            cur = await conn.execute(
                "update action_executions set status=%s,receipt=%s,error=%s,finished_at=now() where idempotency_key=%s and attempt=%s and status='running'",
                (status, Jsonb(receipt), Jsonb(error), key, attempt),
            )
            if cur.rowcount != 1:
                raise ExecutionBusy("执行租约已变更")
