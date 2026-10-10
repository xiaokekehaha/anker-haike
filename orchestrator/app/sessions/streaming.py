"""ModelRouter.stream → 契约 message 事件（票 13 / 14 / 18）。

只有 stream()（tag=user_visible）产出的 delta 会经此进入 message 事件；invoke()（tag=internal）的输出
永远只写状态，不经过 writer。首个 delta 到达时记录 first_visible_ms（08 §8 测量口径）。
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.models.router import ModelInvokeError, ModelRouter, StreamEvent

log = logging.getLogger("sessions.streaming")

# 证据标识不经模型之手（2026-10-10）：T35 第十轮正文出现了把两条证据 id 拼接成的假 UUID。
# 提示词只给 [n] 编号，这里再把模型抄出来的 UUID / [n] / [uuid] 一律丢掉；用户可见的引用只取 message_end.citations
# （服务端按句子重叠归因的真实 evidence_id）。「[Power]」「[Click here](…)」这类方括号不是标识符，保留。
_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_MARKER = re.compile(rf"\s*(?:\[(?:{_UUID}|\d{{1,2}})\]|(?<!\[){_UUID})(?=[\s.,;:!?。，；！？\]\[]|$)")
# 还可能是标记开头的半截（「[05af0178-」「[1」「05af0178-096c」）：在流里连同前导空白一起扣住，等到能判定再放行
# 尾部空白也扣住：标记连同前导空白一起删，首块末尾的空格若已放行，删掉「 [uuid]」后会留下双空格
_PARTIAL = re.compile(r"\s*(?:\[(?:[0-9a-fA-F-]*|\d{0,2})|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{0,4}){0,3}(?:-[0-9a-fA-F]{0,12})?)?$")


def strip_markers(text: str) -> str:
    return _MARKER.sub("", text)


class MarkerFilter:
    """按 delta 过滤：标记可能被切成多块，缓冲到能判定为止；flush 把剩余原样放出。"""

    def __init__(self) -> None:
        self._buf = ""

    def feed(self, delta: str) -> str:
        self._buf += delta
        cleaned = strip_markers(self._buf)
        # 末尾若像一个未完成的标记，留在缓冲区；其余放行
        tail = _PARTIAL.search(cleaned)
        hold = tail.group() if tail else ""
        if hold:
            # 「Done [」会被扣住等下一块；「[Power」后面已有字母，不是标识符前缀，直接放行
            out, self._buf = cleaned[: len(cleaned) - len(hold)], hold
        else:
            out, self._buf = cleaned, ""
        return out

    def flush(self) -> str:
        out, self._buf = self._buf, ""
        return out


@dataclass
class StreamOutcome:
    message_id: str | None = None
    text: str = ""
    model_tier: str | None = None
    completed: bool = False
    citation: dict[str, Any] | None = None  # G1a 事后归因：citations 与未落地句计数
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
    cite: Callable[[str], dict[str, Any]] | None = None,
) -> StreamOutcome:
    out = StreamOutcome()
    t0 = time.perf_counter()
    markers = MarkerFilter()
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
                markers = MarkerFilter()
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
                visible = markers.feed(ev.text)
                out.text += visible
                if visible:
                    writer({"type": "message", "message_id": ev.message_id, "delta": visible})
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
                if rest := markers.flush():
                    out.text += rest
                    writer({"type": "message", "message_id": ev.message_id, "delta": rest})
                # message_end 是这条回复的唯一收口，引用也在这里定稿
                out.citation = cite(out.text) if cite else None
                writer(
                    {
                        "type": "message_end",
                        "message_id": ev.message_id,
                        "status": "completed",
                        "model_tier": ev.model_tier,
                        **(
                            {"citations": out.citation["citations"]}
                            if out.citation and out.citation["citations"]
                            else {}
                        ),
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
