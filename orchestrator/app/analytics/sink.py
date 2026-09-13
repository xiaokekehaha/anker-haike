"""AnalyticsSink：旁路写入，主链路零阻塞。

纪律与票 44 的 LangfuseExporter 一致：
- 有界队列，满即丢弃并计数（业务永不等待写库）；
- 单 worker 批量落库（≤ batch_max 行或 flush_ms 到点）；
- 写失败只记日志，不改变任何业务返回值或异常语义；
- close() 最多等 drain_timeout_s 把队列写完。
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.analytics.schema import Row
from app.analytics.store import AnalyticsStore, Op

log = logging.getLogger("analytics.sink")


class AnalyticsSink:
    def __init__(
        self,
        store: AnalyticsStore,
        *,
        capacity: int = 2000,
        batch_max: int = 200,
        flush_ms: int = 1000,
        drain_timeout_s: float = 3.0,
    ) -> None:
        self._store = store
        self._queue: asyncio.Queue[Op] = asyncio.Queue(maxsize=capacity)
        self._batch_max = batch_max
        self._flush_s = flush_ms / 1000
        self._drain_timeout_s = drain_timeout_s
        self._worker: asyncio.Task | None = None
        self.dropped = 0
        self.written = 0
        self.failed = 0
        self.last_flush_at: float | None = None

    # ---- 生产者侧：只做一次 put_nowait，绝不抛 ----
    def put(self, kind: str, row: Row) -> None:
        try:
            self._queue.put_nowait((kind, row))
        except asyncio.QueueFull:
            self.dropped += 1
            if self.dropped % 100 == 1:  # 避免刷屏
                log.warning("analytics queue full, dropped=%d", self.dropped)
        except Exception:  # noqa: BLE001 - 观测不得影响业务
            self.dropped += 1

    def put_many(self, ops: list[Op]) -> None:
        for kind, row in ops:
            self.put(kind, row)

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    # ---- 生命周期 ----
    def start(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._work(), name="analytics-sink")

    async def _work(self) -> None:
        while True:
            op = await self._queue.get()
            batch = [op]
            deadline = time.monotonic() + self._flush_s
            # 攒批：到 batch_max 或 flush_ms 为止
            while len(batch) < self._batch_max:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    batch.append(await asyncio.wait_for(self._queue.get(), timeout=remaining))
                except TimeoutError:
                    break
            await self._flush(batch)
            for _ in batch:
                self._queue.task_done()

    async def _flush(self, batch: list[Op]) -> None:
        try:
            await self._store.write(batch)
            self.written += len(batch)
            self.last_flush_at = time.time()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - 写库失败不能影响业务
            self.failed += len(batch)
            log.warning(
                "analytics write failed rows=%d error=%s", len(batch), type(exc).__name__
            )

    async def close(self) -> None:
        if self._worker is None:
            return
        try:
            await asyncio.wait_for(self._queue.join(), timeout=self._drain_timeout_s)
        except TimeoutError:
            log.warning("analytics drain timeout, pending=%d", self._queue.qsize())
        self._worker.cancel()
        await asyncio.gather(self._worker, return_exceptions=True)
        self._worker = None

    def stats(self) -> dict[str, object]:
        return {
            "queue_depth": self.queue_depth,
            "written": self.written,
            "dropped": self.dropped,
            "failed": self.failed,
            "last_flush_at": self.last_flush_at,
        }
