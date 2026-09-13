"""Fold immutable events into ordered entries, preserving role and delivery status."""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field


@dataclass
class ConversationEntry:
    entry_id: str
    session_id: str
    run_id: str
    kind: str
    role: str
    first_seq: int
    last_seq: int
    recorded_at: str | None
    text: str = ""
    payload: dict = field(default_factory=dict)
    issue_id: str | None = None
    device_ref_id: str | None = None
    received_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    time_source: str = "server"
    reply_to_input_id: str | None = None
    references: list[str] = field(default_factory=list)
    attachments: list[str] = field(default_factory=list)
    status: str = "completed"
    processing_status: str | None = None
    source_event_ids: list[str] = field(default_factory=list)

    def as_dict(self):
        return asdict(self)


ACTION_LABELS = {
    "request_human": "请求人工",
    "select_product": "选择产品",
    "step_feedback": "反馈排障结果",
    "confirm_receipt": "确认凭证",
    "skip_receipt": "跳过凭证",
    "rediagnose": "补充问题",
    "new_issue": "开始新问题",
    "resume_issue": "继续之前的问题",
}


def fold_history(
    session_id: str, records: list, *, through_seq: int | None = None
) -> list[ConversationEntry]:
    entries: dict[str, ConversationEntry] = {}
    run_inputs: dict[str, str] = {}
    for record in sorted(records, key=lambda r: r.seq):
        if through_seq is not None and record.seq > through_seq:
            break
        e = record.event
        kind = e.get("type")
        at = e.get("recorded_at") or (record.created_at.isoformat() if record.created_at else None)
        base = {
            "session_id": session_id,
            "run_id": record.run_id,
            "first_seq": record.seq,
            "last_seq": record.seq,
            "recorded_at": at,
            "time_source": "server" if at else "unknown",
        }
        entry = None
        if kind == "input_received":
            iid = e["input_id"]
            run_inputs[record.run_id] = iid
            payload = copy.deepcopy(e["payload"])
            is_message = e["input_kind"] == "message"
            entry = entries.get(iid)
            if entry is None:
                entry = ConversationEntry(
                    **base,
                    entry_id=iid,
                    role="user",
                    kind="message" if is_message else "action",
                    received_at=at,
                    text=payload.get("text", "")
                    if is_message
                    else ACTION_LABELS.get(payload.get("kind"), "操作"),
                    payload=payload,
                    attachments=list(payload.get("image_ids") or []),
                    issue_id=e.get("issue_id"),
                )
        elif kind == "issue_changed":
            source = entries.get(e["input_id"])
            if source:
                source.issue_id = e["resolved_issue_id"]
                source.last_seq = record.seq
                source.source_event_ids.append(e["event_id"])
        elif kind == "message_start":
            mid = e["message_id"]
            if old := entries.get(e.get("replaces")):
                old.status = "replaced"
            entry = entries.get(mid) or ConversationEntry(
                **base,
                entry_id=mid,
                role="assistant",
                kind="message",
                started_at=at,
                status="streaming",
                issue_id=e.get("issue_id"),
                reply_to_input_id=e.get("reply_to_input_id") or run_inputs.get(record.run_id),
                references=[e["replaces"]] if e.get("replaces") else [],
            )
        elif kind in {"message", "message_end"}:
            mid = e["message_id"]
            entry = entries.get(mid) or ConversationEntry(
                **base,
                entry_id=mid,
                role="assistant",
                kind="message",
                status="streaming",
                reply_to_input_id=run_inputs.get(record.run_id),
            )
            if kind == "message":
                entry.text += e["delta"]
            else:
                entry.status = e["status"]
                entry.completed_at = at
                entry.payload["model_tier"] = e.get("model_tier")
        elif kind == "tool_call":
            entry = entries.get(e["tool_id"]) or ConversationEntry(
                **base,
                entry_id=e["tool_id"],
                role="tool",
                kind="tool",
                started_at=at,
                reply_to_input_id=run_inputs.get(record.run_id),
            )
            entry.text = e.get("summary") or e["name"]
            entry.payload = copy.deepcopy(e)
            entry.status = {"started": "streaming", "finished": "completed", "failed": "failed"}[
                e["status"]
            ]
            if e["status"] != "started":
                entry.completed_at = at
        elif kind in {"product_card", "step_card", "receipt_card", "escalation_summary"}:
            entry = entries.get(e["card_id"]) or ConversationEntry(
                **base,
                entry_id=e["card_id"],
                role="assistant",
                kind="card",
                started_at=at,
                completed_at=at,
                reply_to_input_id=run_inputs.get(record.run_id),
                issue_id=e.get("issue_id"),
            )
            entry.payload = copy.deepcopy(e)
            entry.text = e.get("step", {}).get("instruction", "")
        elif kind == "done":
            if input_entry := entries.get(run_inputs.get(record.run_id)):
                input_entry.processing_status = {"error": "failed", "cancelled": "cancelled"}.get(
                    e["reason"], "completed"
                )
            for item in entries.values():
                if item.run_id == record.run_id and item.status == "streaming":
                    item.status = "aborted"
                    item.completed_at = at
                    item.last_seq = record.seq
                    item.source_event_ids.append(e.get("event_id", f"{session_id}:{record.seq}"))
        if entry is not None:
            entry.last_seq = record.seq
            entry.source_event_ids.append(e.get("event_id", f"{session_id}:{record.seq}"))
            entries[entry.entry_id] = entry
    return sorted(entries.values(), key=lambda item: item.first_seq)
