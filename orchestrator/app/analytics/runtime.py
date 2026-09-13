"""analytics 生命周期：随应用启动建 sink，关闭时排空队列。

数据库不可用时不启用（沉默降级）：观测台没有数据，但业务完全不受影响。
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from app.analytics.hooks import set_sink
from app.analytics.sink import AnalyticsSink
from app.analytics.store import PostgresAnalyticsStore
from app.settings import settings

log = logging.getLogger("analytics.runtime")


async def open_analytics(app: FastAPI) -> None:
    app.state.analytics_sink = None
    if not settings.analytics_enabled:
        log.info("analytics disabled")
        return
    pool = getattr(app.state, "session_pool", None)
    if pool is None:
        log.warning("analytics unavailable: session pool not ready")
        return
    sink = AnalyticsSink(
        PostgresAnalyticsStore(pool),
        capacity=settings.analytics_queue_capacity,
        flush_ms=settings.analytics_flush_ms,
    )
    sink.start()
    set_sink(sink)
    app.state.analytics_sink = sink
    log.info(
        "analytics ready capacity=%d flush_ms=%d store_text=%s",
        settings.analytics_queue_capacity,
        settings.analytics_flush_ms,
        settings.analytics_store_text,
    )


async def close_analytics(app: FastAPI) -> None:
    sink = getattr(app.state, "analytics_sink", None)
    set_sink(None)
    if sink is not None:
        log.info("analytics shutdown %s", sink.stats())
        await sink.close()
    app.state.analytics_sink = None
