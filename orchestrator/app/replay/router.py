"""ReplayRouter / RecordingRouter（票 43）：与 ModelRouter 同接口（invoke / stream / registry）。

- ReplayRouter：按 model_key 命中录制包；未命中抛 ModelInvokeError(reason=replay_miss)，节点走既有降级路径，
  不发任何真实请求、不借用其他记录。stream 命中按录制的分片重放（可配延迟，演示时有打字感）。
- RecordingRouter：包装真实 ModelRouter，成功的 invoke / 完整的 stream 写入 Recorder；失败不记录
  （回放时同样未命中 → 同样的降级路径）。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any, TypeVar

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ValidationError

from app.models.queue import BoundedGate
from app.models.registry import ModelRegistry
from app.models.router import (
    Attempt,
    Method,
    ModelInvokeError,
    ModelResult,
    ModelRouter,
    StreamEvent,
)
from app.replay.package import Recorder, ReplayPackage, model_key

log = logging.getLogger("replay.router")
T = TypeVar("T", bound=BaseModel)
REPLAY_MODEL = "replay"
DEFAULT_STREAM_DELAY_S = 0.02


class ReplayRouter:
    """只读回放：`registry` 仍是真实配置（节点用它算 max_images 等能力），但绝不构建模型实例。"""

    def __init__(
        self,
        registry: ModelRegistry,
        package: ReplayPackage,
        *,
        stream_delay_s: float = DEFAULT_STREAM_DELAY_S,
    ):
        self.registry = registry
        self.package = package
        self.gate = BoundedGate(registry.cfg.concurrency.max_in_flight)
        self.stream_delay_s = stream_delay_s
        self.hits = 0
        self.misses: list[dict[str, Any]] = []

    @property
    def case_id(self) -> str:
        return self.package.case_id

    def _miss(self, task: str, lane: str, key: str, mode: str) -> ModelInvokeError:
        self.misses.append({"task": task, "mode": mode, "key": key})
        log.warning(
            "replay miss case=%s task=%s mode=%s key=%s", self.case_id, task, mode, key[:12]
        )
        attempt = Attempt(
            alias=REPLAY_MODEL,
            model_used=f"{REPLAY_MODEL}/{self.case_id}",
            lane=lane,
            method=None,
            outcome="error",
            latency_ms=0,
            error=f"replay_miss: task {task!r} not in package {self.case_id!r}",
        )
        return ModelInvokeError(task, [attempt], "replay_miss")

    async def invoke(
        self,
        task: str,
        messages: Sequence[BaseMessage | tuple[str, str] | dict[str, Any]],
        schema: type[T],
        *,
        budget_ms: int,
        session_id: str | None = None,
        lane: str | None = None,
        method: Method | None = None,
    ) -> ModelResult[T]:
        lane = lane or self.registry.cfg.default_lane
        key = model_key(task, schema.__name__, messages)
        rec = self.package.models.get(key)
        if rec is None or rec.get("mode") != "invoke":
            raise self._miss(task, lane, key, "invoke")
        try:
            parsed = schema.model_validate(rec.get("output"))
        except ValidationError as exc:
            log.error("replay record invalid case=%s task=%s: %s", self.case_id, task, exc)
            raise self._miss(task, lane, key, "invoke") from exc
        self.hits += 1
        model_used = str(rec.get("model_used") or f"{REPLAY_MODEL}/{self.case_id}")
        attempt = Attempt(
            REPLAY_MODEL, model_used, lane, rec.get("method") or "json_schema", "ok", 0
        )
        return ModelResult(
            parsed=parsed,
            model_used=model_used,
            alias=REPLAY_MODEL,
            lane=lane,
            method=rec.get("method") or "json_schema",
            latency_ms=0,
            usage={},
            attempts=[attempt],
        )

    async def stream(
        self,
        task: str,
        messages: Sequence[BaseMessage | tuple[str, str] | dict[str, Any]],
        *,
        budget_ms: int,
        message_id: str,
        session_id: str | None = None,
        lane: str | None = None,
        fallback_messages: Sequence[Any] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        lane = lane or self.registry.cfg.default_lane
        key = model_key(task, None, messages)
        rec = self.package.models.get(key)
        if rec is None or rec.get("mode") != "stream":
            raise self._miss(task, lane, key, "stream")
        self.hits += 1
        model_used = str(rec.get("model_used") or f"{REPLAY_MODEL}/{self.case_id}")
        chunks = [c for c in (rec.get("chunks") or [rec.get("text") or ""]) if c]
        if not chunks:
            raise self._miss(task, lane, key, "stream")
        yield StreamEvent(
            "start", message_id, model_tier="primary", alias=REPLAY_MODEL, model_used=model_used
        )
        for chunk in chunks:
            if self.stream_delay_s > 0:
                await asyncio.sleep(self.stream_delay_s)
            yield StreamEvent(
                "delta", message_id, text=chunk, model_tier="primary", alias=REPLAY_MODEL
            )
        yield StreamEvent(
            "end", message_id, model_tier="primary", alias=REPLAY_MODEL, model_used=model_used
        )


class RecordingRouter:
    """透传真实 ModelRouter 并录制成功结果。`registry` / `gate` 转发，节点无感。"""

    def __init__(self, inner: ModelRouter, recorder: Recorder):
        self.inner = inner
        self.recorder = recorder

    @property
    def registry(self) -> ModelRegistry:
        return self.inner.registry

    @property
    def gate(self) -> BoundedGate:
        return self.inner.gate

    async def invoke(
        self, task, messages, schema, *, budget_ms, session_id=None, lane=None, method=None
    ):
        key = model_key(task, schema.__name__, messages)
        try:
            res = await self.inner.invoke(
                task,
                messages,
                schema,
                budget_ms=budget_ms,
                session_id=session_id,
                lane=lane,
                method=method,
            )
        except ModelInvokeError as exc:
            self.recorder.misses.append({"task": task, "mode": "invoke", "reason": exc.reason})
            raise
        self.recorder.add_model(
            key,
            {
                "task": task,
                "mode": "invoke",
                "schema": schema.__name__,
                "output": res.parsed.model_dump(mode="json"),
                "model_used": res.model_used,
                "method": res.method,
                "lane": res.lane,
                "latency_ms": res.latency_ms,
            },
        )
        return res

    async def stream(
        self,
        task,
        messages,
        *,
        budget_ms,
        message_id,
        session_id=None,
        lane=None,
        fallback_messages=None,
    ) -> AsyncIterator[StreamEvent]:
        key = model_key(task, None, messages)
        chunks: list[str] = []
        model_used = None
        completed = False
        async for ev in self.inner.stream(
            task,
            messages,
            budget_ms=budget_ms,
            message_id=message_id,
            session_id=session_id,
            lane=lane,
            fallback_messages=fallback_messages,
        ):
            if ev.kind == "start":
                chunks = []  # 降级替换：从头记录
                model_used = ev.model_used
            elif ev.kind == "delta":
                chunks.append(ev.text)
            elif ev.kind == "end":
                completed = True
                model_used = ev.model_used or model_used
            yield ev
        if completed and chunks:
            self.recorder.add_model(
                key,
                {
                    "task": task,
                    "mode": "stream",
                    "text": "".join(chunks),
                    "chunks": chunks,
                    "model_used": model_used or "unknown",
                    "lane": lane or self.inner.registry.cfg.default_lane,
                },
            )
        elif not completed:
            self.recorder.misses.append({"task": task, "mode": "stream", "reason": "not completed"})
