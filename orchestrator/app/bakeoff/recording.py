"""把 ModelRouter 钉到单一别名并记录每次调用的 attempts / usage（评测用，不进生产）。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.models.config import ModelsConfig
from app.models.registry import ModelRegistry
from app.models.router import Attempt, ModelInvokeError, ModelRouter, StreamEvent


@dataclass
class CallRecord:
    task: str
    alias: str
    attempts: list[Attempt] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    ok: bool = False
    error: str | None = None
    stream_text: str = ""

    @property
    def first_pass(self) -> bool:
        """§3.8 Schema 通过率口径：首次真实输出即通过校验（跳过项不算一次输出）。"""
        real = [a for a in self.attempts if a.outcome != "skipped"]
        return bool(real) and real[0].outcome == "ok"

    @property
    def latency_ms(self) -> int:
        return sum(a.latency_ms for a in self.attempts)


def pin_config(cfg: ModelsConfig, task: str, alias: str, lane: str) -> ModelsConfig:
    """复制配置并把 lane/task 的链改为 [alias]，其余不变。"""
    lanes = {ln: dict(tasks) for ln, tasks in cfg.lanes.items()}
    route = lanes[lane][task]
    lanes[lane][task] = route.model_copy(update={"chain": [alias]})
    return cfg.model_copy(update={"lanes": lanes})


class RecordingRouter(ModelRouter):
    def __init__(self, registry: ModelRegistry, alias: str, **kw: Any):
        super().__init__(registry, **kw)
        self.alias = alias
        self.records: list[CallRecord] = []

    async def invoke(self, task, messages, schema, **kw):  # type: ignore[override]
        rec = CallRecord(task, self.alias)
        self.records.append(rec)
        try:
            res = await super().invoke(task, messages, schema, **kw)
        except ModelInvokeError as exc:
            rec.attempts, rec.error = list(exc.attempts), exc.reason
            raise
        rec.attempts, rec.usage, rec.ok = list(res.attempts), dict(res.usage), True
        return res

    async def stream(self, task, messages, **kw) -> AsyncIterator[StreamEvent]:  # type: ignore[override]
        rec = CallRecord(task, self.alias)
        self.records.append(rec)
        try:
            async for ev in super().stream(task, messages, **kw):
                if ev.kind == "delta":
                    rec.stream_text += ev.text
                elif ev.kind == "end":
                    rec.ok = True
                yield ev
        except ModelInvokeError as exc:
            rec.attempts, rec.error = list(exc.attempts), exc.reason
            raise
        # stream 成功路径拿不到 attempts 引用，这里按文本长度估算 usage（中文约 1.5 字 / token）
        rec.usage = {"input_tokens": 0, "output_tokens": max(1, int(len(rec.stream_text) / 1.5))}
        if not rec.attempts:
            rec.attempts = [Attempt(self.alias, "?", "?", None, "ok" if rec.ok else "error", 0)]
