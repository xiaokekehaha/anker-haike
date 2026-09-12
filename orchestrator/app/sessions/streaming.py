"""ModelRouter.stream → 契约 message 事件（票 13 / 14 / 18）。

只有 stream()（tag=user_visible）产出的 delta 会经此进入 message 事件；invoke()（tag=internal）的输出
永远只写状态，不经过 writer。首个 delta 到达时记录 first_visible_ms（08 §8 测量口径）。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.models.router import ModelInvokeError, ModelRouter, StreamEvent

log = logging.getLogger("sessions.streaming")


@dataclass
class StreamOutcome:
    message_id: str | None = None
    text: str = ""
    model_tier: str | None = None
    completed: bool = False
    aborted_ids: list[str] = field(default_factory=list)
    first_visible_ms: int | None = None
    error: str | None = None
    events: list[StreamEvent] = field(default_factory=list)


async def stream_to_writer(
    writer: Callable[[dict[str, Any]], None],
    router: ModelRouter,
    task: str,
    messages,
    *,
    message_id: str,
    budget_ms: int,
    session_id: str | None,
    lane: str,
    fallback_messages=None,
    run_started_at: float | None = None,
) -> StreamOutcome:
    out = StreamOutcome()
    t0 = time.perf_counter()
    try:
        async for ev in router.stream(
            task,
            messages,
            budget_ms=budget_ms,
            message_id=message_id,
            session_id=session_id,
            lane=lane,
            fallback_messages=fallback_messages,
        ):
            out.events.append(ev)
            if ev.kind == "start":
                out.message_id, out.text, out.model_tier = ev.message_id, "", ev.model_tier
                payload: dict[str, Any] = {"type": "message_start", "message_id": ev.message_id}
                if ev.replaces:
                    payload["replaces"] = ev.replaces
                writer(payload)
            elif ev.kind == "delta":
                if out.first_visible_ms is None:
                    base = run_started_at if run_started_at is not None else t0
                    out.first_visible_ms = int((time.perf_counter() - base) * 1000)
                    log.info(
                        "first_visible_ms=%d task=%s session=%s tier=%s",
                        out.first_visible_ms,
                        task,
                        session_id,
                        ev.model_tier,
                        extra={
                            "event": "first_visible",
                            "first_visible_ms": out.first_visible_ms,
                            "task": task,
                            "session_id": session_id,
                        },
                    )
                out.text += ev.text
                writer({"type": "message", "message_id": ev.message_id, "delta": ev.text})
            elif ev.kind == "aborted":
                out.aborted_ids.append(ev.message_id)
                writer(
                    {
                        "type": "message_end",
                        "message_id": ev.message_id,
                        "status": "aborted",
                        "model_tier": ev.model_tier,
                    }
                )
            elif ev.kind == "end":
                out.completed = True
                writer(
                    {
                        "type": "message_end",
                        "message_id": ev.message_id,
                        "status": "completed",
                        "model_tier": ev.model_tier,
                    }
                )
    except ModelInvokeError as exc:
        out.error = str(exc)
        log.warning("stream failed task=%s session=%s: %s", task, session_id, str(exc)[:200])
        if out.message_id and not out.completed and out.message_id not in out.aborted_ids:
            writer(
                {
                    "type": "message_end",
                    "message_id": out.message_id,
                    "status": "aborted",
                    "model_tier": out.model_tier,
                }
            )
    return out
