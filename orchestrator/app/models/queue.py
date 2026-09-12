"""全局有界并发门（票 12，07 §13）：进行中的模型调用超过上限时立即拒绝，不排队堆积。

拒绝映射为契约里的 error(recoverable=true, retry_with_same_action=true)，让用户稍后重试。
队列长度、峰值、拒绝次数以结构化字段进日志并可通过 snapshot() 读取（票 44 接指标）。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from app.observability.runtime import record

log = logging.getLogger("models.queue")


class CapacityExceeded(RuntimeError):
    code = "model_capacity_exceeded"

    def __init__(self, task: str, in_flight: int, limit: int):
        self.task = task
        self.in_flight = in_flight
        self.limit = limit
        super().__init__(f"model queue full ({in_flight}/{limit}), task {task!r} rejected")

    def as_error_fields(self) -> dict[str, Any]:
        """填入契约 error 事件的字段（seq / run_id 由会话层补）。"""
        return {
            "code": self.code,
            "message": "当前咨询人数较多，请稍后再试一次",
            "recoverable": True,
            "retry_with_same_action": True,
        }


class BoundedGate:
    def __init__(self, limit: int):
        if limit < 1:
            raise ValueError("limit must be >= 1")
        self.limit = limit
        self.in_flight = 0
        self.peak = 0
        self.rejected_total = 0
        self.admitted_total = 0

    def snapshot(self) -> dict[str, int]:
        return {
            "in_flight": self.in_flight,
            "limit": self.limit,
            "peak": self.peak,
            "admitted_total": self.admitted_total,
            "rejected_total": self.rejected_total,
        }

    def try_acquire(self, task: str) -> None:
        if self.in_flight >= self.limit:
            self.rejected_total += 1
            log.warning(
                "model_queue_full task=%s in_flight=%d limit=%d rejected_total=%d",
                task,
                self.in_flight,
                self.limit,
                self.rejected_total,
                extra={"event": "model_queue_full", "task": task, **self.snapshot()},
            )
            record("model_queue_full", task=task, **self.snapshot())  # 票 50：拒绝率告警的观测点
            raise CapacityExceeded(task, self.in_flight, self.limit)
        self.in_flight += 1
        self.admitted_total += 1
        self.peak = max(self.peak, self.in_flight)
        log.debug(
            "model_queue_enter task=%s in_flight=%d limit=%d",
            task,
            self.in_flight,
            self.limit,
            extra={"event": "model_queue_enter", "task": task, **self.snapshot()},
        )

    def release(self, task: str) -> None:
        self.in_flight -= 1
        log.debug(
            "model_queue_leave task=%s in_flight=%d",
            task,
            self.in_flight,
            extra={"event": "model_queue_leave", "task": task, **self.snapshot()},
        )

    @asynccontextmanager
    async def slot(self, task: str):
        self.try_acquire(task)
        try:
            yield
        finally:
            self.release(task)
