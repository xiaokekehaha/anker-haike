"""管理员观测台的事实采集与查询（docs/planning/2026-09-13_admin-observability-console）。

旁路写入：所有采集经 AnalyticsSink 的有界队列异步落库，主链路不等待、不因写库失败改变行为。
"""

from app.analytics.hooks import get_sink, observe, set_sink
from app.analytics.sink import AnalyticsSink
from app.analytics.store import InMemoryAnalyticsStore, PostgresAnalyticsStore
from app.analytics.trace import RunTrace

__all__ = [
    "AnalyticsSink",
    "InMemoryAnalyticsStore",
    "PostgresAnalyticsStore",
    "RunTrace",
    "get_sink",
    "observe",
    "set_sink",
]
