"""Atomic input acceptance. Raw content lives in events, receipts only index it."""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from datetime import UTC, datetime

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

INPUT_DDL = """
alter table sessions add column if not exists published_checkpoint_id text;
create table if not exists session_inputs (
    session_id text not null,
    input_id text not null,
    kind text not null,
    payload_digest text not null,
    run_id text not null,
    input_event_seq integer not null,
    received_at timestamptz not null,
    status text not null default 'accepted',
    state_commit_version integer,
    last_output_seq integer,
    base_version integer not null,
    base_checkpoint_id text,
    primary key(session_id, input_id)
);
create index if not exists session_inputs_run_idx on session_inputs(session_id, run_id);
create unique index if not exists session_events_identity_idx on session_events(session_id,(event_json->>'event_id'));
create table if not exists conversation_summaries (
    session_id text not null,
    summary_id text not null,
    through_seq integer not null,
    source_context_revision integer not null,
    source_entry_ids jsonb not null,
    text text not null,
    generated_at timestamptz not null default now(),
    status text not null default 'active',
    expires_at timestamptz not null,
    primary key(session_id, summary_id)
);
"""


class InputConflict(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def payload_digest(payload: dict) -> str:
    # Stored attachment IDs vary on upload retries; content hashes define identity.
    ignored = {"expected_version", "client_sent_at", "received_at", "input_id", "action_id"}
    if "attachment_hashes" in payload:
        ignored.add("image_ids")
        ignored.add("images")  # Server-generated timestamps are not business identity.
    business = {k: v for k, v in payload.items() if k not in ignored}
    raw = json.dumps(business, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def check_replay(receipt: dict, payload: dict) -> None:
    if receipt["payload_digest"] != payload_digest(payload):
        raise InputConflict("input_id_conflict")


def _check_new(row, expected_version: int, payload: dict) -> None:
    if row.active_run_id:
        raise InputConflict("run_active")
    if payload.get("kind") != "request_human" and expected_version != row.version:
        raise InputConflict("stale_version")


def _new_input(sid: str, iid: str, payload: dict, seq: int, deadline_ms: int, row):
    at = datetime.now(UTC).isoformat()
    rid = uuid.uuid4().hex
    receipt = {
        "session_id": sid,
        "input_id": iid,
        "base_version": row.version,
        "base_checkpoint_id": row.published_checkpoint_id,
        "kind": "message" if payload.get("kind") == "message" else "action",
        "payload_digest": payload_digest(payload),
        "run_id": rid,
        "input_event_seq": seq + 2,
        "received_at": at,
        "status": "accepted",
        "state_commit_version": None,
        "last_output_seq": None,
    }
    base = {"run_id": rid, "recorded_at": at}
    events = [
        dict(
            base,
            type="run_started",
            seq=seq + 1,
            event_id=uuid.uuid4().hex,
            resumed=False,
            deadline_ms=deadline_ms,
        ),
        dict(
            base,
            type="input_received",
            seq=seq + 2,
            event_id=uuid.uuid4().hex,
            input_id=iid,
            input_kind=receipt["kind"],
            payload=copy.deepcopy(payload),
            issue_id=payload.get("target_issue_id"),
        ),
    ]
    return receipt, events


class PostgresInputStore:
    async def get_input(self, session_id: str, input_id: str) -> dict | None:
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "select * from session_inputs where session_id=%s and input_id=%s",
                (session_id, input_id),
            )
            return _receipt(await cur.fetchone())

    async def reserve_input(
        self,
        session_id: str,
        input_id: str,
        payload: dict,
        *,
        expected_version: int,
        deadline_ms: int = 25000,
        staged_images=(),
        image_store=None,
    ) -> tuple[dict, bool]:
        from app.sessions.store import SessionNotFound, _row

        async with (
            self._pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as cur,
        ):
            # Serialize ALL input acceptance, even different workers/processes.
            await cur.execute(
                "select * from sessions where session_id=%s for update", (session_id,)
            )
            row = await cur.fetchone()
            if row is None:
                raise SessionNotFound(session_id)
            await cur.execute(
                "select * from session_inputs where session_id=%s and input_id=%s",
                (session_id, input_id),
            )
            old = _receipt(await cur.fetchone())
            if old:
                check_replay(old, payload)
                return old, True
            _check_new(_row(row), expected_version, payload)
            if staged_images:
                await image_store.persist_staged(staged_images, conn=conn)
            await cur.execute(
                "select coalesce(max(seq),0) as seq from session_events where session_id=%s",
                (session_id,),
            )
            receipt, events = _new_input(
                session_id, input_id, payload, (await cur.fetchone())["seq"], deadline_ms, _row(row)
            )
            await cur.execute(
                "update sessions set active_run_id=%s, updated_at=now() where session_id=%s",
                (receipt["run_id"], session_id),
            )
            for event in events:
                await cur.execute(
                    "insert into session_events(session_id,seq,run_id,event_json,created_at) values (%s,%s,%s,%s,%s)",
                    (
                        session_id,
                        event["seq"],
                        receipt["run_id"],
                        Jsonb(event),
                        receipt["received_at"],
                    ),
                )
            await cur.execute(
                """insert into session_inputs(session_id,input_id,kind,payload_digest,run_id,input_event_seq,received_at,base_version,base_checkpoint_id)
                values (%(session_id)s,%(input_id)s,%(kind)s,%(payload_digest)s,%(run_id)s,%(input_event_seq)s,%(received_at)s,%(base_version)s,%(base_checkpoint_id)s)""",
                receipt,
            )
            return receipt, False

    async def publish_commit(
        self, receipt: dict, checkpoint_id: str, stage: str, decision: dict
    ) -> int:
        sid, iid, rid = receipt["session_id"], receipt["input_id"], receipt["run_id"]
        async with (
            self._pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as cur,
        ):
            await cur.execute("select * from sessions where session_id=%s for update", (sid,))
            row = await cur.fetchone()
            await cur.execute(
                "select state_commit_version from session_inputs where session_id=%s and input_id=%s",
                (sid, iid),
            )
            old = await cur.fetchone()
            if old and old["state_commit_version"] is not None:
                return old["state_commit_version"]
            if not row or row["active_run_id"] != rid or row["version"] != receipt["base_version"]:
                raise InputConflict("publish_conflict")
            version = row["version"] + 1
            await cur.execute(
                "update sessions set version=%s,stage=%s,published_checkpoint_id=%s where session_id=%s",
                (version, stage, checkpoint_id, sid),
            )
            await cur.execute(
                "update session_inputs set state_commit_version=%s,status='running' where session_id=%s and input_id=%s",
                (version, sid, iid),
            )
            event = _commit_event(receipt, checkpoint_id, version, decision)
            await cur.execute(
                """insert into session_events(session_id,seq,run_id,event_json)
                select %s,coalesce(max(seq),0)+1,%s,%s from session_events where session_id=%s""",
                (sid, rid, Jsonb(event), sid),
            )
            return version

    async def complete_input(self, receipt: dict, reason: str) -> dict:
        sid, iid, rid = receipt["session_id"], receipt["input_id"], receipt["run_id"]
        async with (
            self._pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as cur,
        ):
            await cur.execute("select * from sessions where session_id=%s for update", (sid,))
            row = await cur.fetchone()
            await cur.execute(
                "select seq,event_json from session_events where session_id=%s and run_id=%s and event_json->>'type'='done' order by seq limit 1",
                (sid, rid),
            )
            old = await cur.fetchone()
            if old:
                return {**old["event_json"], "seq": old["seq"], "run_id": rid}
            if not row or row["active_run_id"] != rid:
                raise InputConflict("finish_conflict")
            await cur.execute(
                "select coalesce(max(seq),0)+1 as seq from session_events where session_id=%s",
                (sid,),
            )
            event = _done_event(receipt, reason, row["version"], (await cur.fetchone())["seq"])
            await cur.execute(
                "insert into session_events(session_id,seq,run_id,event_json) values (%s,%s,%s,%s)",
                (sid, event["seq"], rid, Jsonb(event)),
            )
            await cur.execute(
                "update session_inputs set status=%s,last_output_seq=%s where session_id=%s and input_id=%s",
                (_status(reason), event["seq"], sid, iid),
            )
            await cur.execute(
                "update sessions set active_run_id=null,updated_at=now() where session_id=%s",
                (sid,),
            )
            return event


def _receipt(row: dict | None) -> dict | None:
    if row and isinstance(row["received_at"], datetime):
        row["received_at"] = row["received_at"].isoformat()
    return row


class MemoryInputStore:
    async def get_input(self, session_id: str, input_id: str) -> dict | None:
        return copy.deepcopy(self._inputs.get((session_id, input_id)))

    async def reserve_input(
        self,
        session_id: str,
        input_id: str,
        payload: dict,
        *,
        expected_version: int,
        deadline_ms: int = 25000,
        staged_images=(),
        image_store=None,
    ) -> tuple[dict, bool]:
        from app.sessions.store import EventRecord, SessionNotFound

        async with self._lock:
            mem = self._get(session_id)
            if mem.row is None:
                raise SessionNotFound(session_id)
            old = self._inputs.get((session_id, input_id))
            if old:
                check_replay(old, payload)
                return copy.deepcopy(old), True
            _check_new(mem.row, expected_version, payload)
            receipt, events = _new_input(
                session_id, input_id, payload, len(mem.events), deadline_ms, mem.row
            )
            if staged_images:
                image_store.persist_staged_memory(staged_images)
            mem.row.active_run_id = receipt["run_id"]
            for ev in events:
                mem.events.append(
                    EventRecord(
                        ev["seq"], ev["run_id"], datetime.fromisoformat(ev["recorded_at"]), ev
                    )
                )
            self._inputs[(session_id, input_id)] = receipt
            return copy.deepcopy(receipt), False

    async def publish_commit(
        self, receipt: dict, checkpoint_id: str, stage: str, decision: dict
    ) -> int:
        from app.sessions.store import EventRecord

        sid, iid = receipt["session_id"], receipt["input_id"]
        async with self._lock:
            mem = self._get(sid)
            stored = self._inputs[(sid, iid)]
            if stored["state_commit_version"] is not None:
                return stored["state_commit_version"]
            if (
                not mem.row
                or mem.row.active_run_id != receipt["run_id"]
                or mem.row.version != receipt["base_version"]
            ):
                raise InputConflict("publish_conflict")
            mem.row.version += 1
            mem.row.stage = stage
            mem.row.published_checkpoint_id = checkpoint_id
            stored.update(state_commit_version=mem.row.version, status="running")
            event = _commit_event(receipt, checkpoint_id, mem.row.version, decision)
            mem.events.append(
                EventRecord(len(mem.events) + 1, receipt["run_id"], datetime.now(UTC), event)
            )
            return mem.row.version

    async def complete_input(self, receipt: dict, reason: str) -> dict:
        from app.sessions.store import EventRecord

        sid, iid, rid = receipt["session_id"], receipt["input_id"], receipt["run_id"]
        async with self._lock:
            mem = self._get(sid)
            old = next(
                (r for r in mem.events if r.run_id == rid and r.event.get("type") == "done"), None
            )
            if old:
                return {**old.event, "seq": old.seq, "run_id": rid}
            if not mem.row or mem.row.active_run_id != rid:
                raise InputConflict("finish_conflict")
            event = _done_event(receipt, reason, mem.row.version, len(mem.events) + 1)
            mem.events.append(EventRecord(event["seq"], rid, datetime.now(UTC), event))
            self._inputs[(sid, iid)].update(status=_status(reason), last_output_seq=event["seq"])
            mem.row.active_run_id = None
            mem.row.updated_at = datetime.now(UTC)
            return event


def _status(reason):
    return {"error": "failed", "cancelled": "cancelled"}.get(reason, "completed")


def _done_event(receipt, reason, version, seq):
    from app.conversation.reduce import stable_id

    return {
        "type": "done",
        "event_id": stable_id(receipt["input_id"], "done"),
        "recorded_at": datetime.now(UTC).isoformat(),
        "run_id": receipt["run_id"],
        "seq": seq,
        "reason": reason,
        "version": version,
    }


def _commit_event(receipt, checkpoint_id, version, decision):
    from app.conversation.reduce import stable_id
    from app.sessions.internal_events import StateCommitted

    return StateCommitted.model_validate(
        {
            "type": "state_committed",
            "event_id": stable_id(receipt["input_id"], "committed"),
            "recorded_at": datetime.now(UTC).isoformat(),
            "visibility": "internal",
            "input_id": receipt["input_id"],
            "checkpoint_id": checkpoint_id,
            "version": version,
            "decision": decision,
        }
    ).model_dump()
