"""RunTrace：一次 run 的节点轨迹与事实收集（运行器调用）。

节点名来自 LangGraph `updates` 流的 chunk 键；`updates` 在节点执行完成后产出，因此把
「上一条 updates 到本条 updates」的间隔记为本节点耗时（图内节点串行）。

所有方法吞掉自身异常：观测失败不得影响 run。
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

from app.analytics import derive
from app.analytics.context import clear_context_events, take_context_events
from app.analytics.hooks import get_sink, take_counters
from app.analytics.schema import RunFacts

log = logging.getLogger("analytics.trace")

# updates 流里非节点的保留键
_RESERVED = {"__interrupt__", "__metadata__", "__error__"}


class RunTrace:
    def __init__(self, session_id: str, run_id: str, *, entry: str, seq_no: int) -> None:
        self.session_id = session_id
        self.run_id = run_id
        self.entry = entry
        self.seq_no = seq_no
        self.started = time.monotonic()
        self.started_wall = datetime.now(UTC)
        self.updates: list[tuple[str, Any, float]] = []
        self.context_events: dict[int, list[dict[str, object]]] = {}
        self.interrupted = False

    def on_updates(self, chunk: Any) -> None:
        """记录一条 updates；一条里可能有多个节点（并行分支），按出现顺序展开。"""
        try:
            if not isinstance(chunk, dict):
                return
            now = time.monotonic()
            for node, update in chunk.items():
                if node in _RESERVED:
                    if node == "__interrupt__":
                        self.interrupted = True
                    continue
                self.updates.append((str(node), update, now))
                self.context_events[len(self.updates)] = take_context_events(self.run_id, str(node))
        except Exception:
            log.debug("analytics on_updates failed", exc_info=True)

    def finish(
        self,
        state: Any,
        *,
        done_reason: str,
        error_code: str | None,
        stage_from: str | None,
        stage_to: str | None,
        first_visible_ms: int | None,
        card_ready_ms: int | None,
        card_kind: str | None,
        lane: str | None = None,
        raw_ttl_hours: float = 24.0,
        store_text: bool = True,
    ) -> None:
        """run 结束：写 node_runs + run_facts + session_facts（都进 sink 队列，不等待落库）。"""
        sink = get_sink()
        counters = take_counters(self.run_id)
        clear_context_events(self.run_id)
        if sink is None:
            return
        try:
            ended = time.monotonic()
            nodes = derive.node_runs_from_updates(
                self.session_id,
                self.run_id,
                self.updates,
                run_started=self.started,
                started_wall=self.started_wall,
            )
            if nodes and self.interrupted:
                nodes[-1].status = "interrupt"
            for row in nodes:
                if metrics := self.context_events.get(row.idx):
                    row.summary = {**(row.summary or {}), "context_metrics": metrics}
                sink.put("node_run", row)

            duration_ms = int((ended - self.started) * 1000)
            model_calls = counters.get("model_calls", 0)
            tokens_in = counters.get("tokens_in", 0)
            tokens_out = counters.get("tokens_out", 0)
            sink.put(
                "run_facts",
                RunFacts(
                    run_id=self.run_id,
                    session_id=self.session_id,
                    seq_no=self.seq_no,
                    started_at=self.started_wall,
                    ended_at=datetime.now(UTC),
                    duration_ms=duration_ms,
                    entry=self.entry,
                    stage_from=stage_from,
                    stage_to=stage_to,
                    done_reason=done_reason,
                    error_code=error_code,
                    first_visible_ms=first_visible_ms,
                    card_ready_ms=card_ready_ms,
                    card_kind=card_kind,
                    model_calls=model_calls,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    node_count=len(nodes),
                ),
            )

            values = dict(getattr(state, "values", None) or {})
            sink.put(
                "session_facts",
                derive.session_facts(
                    self.session_id,
                    values,
                    lane=lane,
                    done_reason=done_reason,
                    error_code=error_code,
                    pending=bool(values.get("pending_card")),
                    runs=self.seq_no,
                    created_at=self.started_wall,
                    last_run_at=datetime.now(UTC),
                    model_calls=model_calls,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    total_latency_ms=duration_ms,
                    raw_ttl_hours=raw_ttl_hours,
                    store_text=store_text,
                ),
            )
        except Exception:
            log.debug("analytics finish failed run=%s", self.run_id, exc_info=True)


def _has_interrupt(state: Any) -> bool:
    return any(getattr(t, "interrupts", None) for t in getattr(state, "tasks", ()) or ())
