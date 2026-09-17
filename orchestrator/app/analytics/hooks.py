"""采集接入点：把既有埋点旁路成 analytics 行。

① `observability.runtime.record()` 尾部调用 `observe()`：model_call / knowledge_search。
② 运行器用 `RunTrace` 收集节点轨迹与 run 事实（见 sessions/runner.py）。

规则命中不单独建表：R 编号与 verify 判定已随节点状态更新进入 node_runs.summary 与
session_facts.outcome_reason（02_hackathon-scope.md 的取舍）。

本模块任何异常都不得外溢到业务路径——全部调用点包 try/except。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.analytics.context import observe_context
from app.analytics.schema import ModelCall, RetrievalCall
from app.analytics.sink import AnalyticsSink

log = logging.getLogger("analytics.hooks")

_sink: AnalyticsSink | None = None
# run_id -> 本 run 的模型 / token 累计，run 结束时由 RunTrace 取走
_counters: dict[str, dict[str, int]] = {}
_COUNTERS_MAX = 500


def set_sink(sink: AnalyticsSink | None) -> None:
    global _sink
    _sink = sink


def get_sink() -> AnalyticsSink | None:
    return _sink


def current_node() -> str | None:
    """当前 LangGraph 节点名；在节点执行上下文之外返回 None。"""
    try:
        from langgraph.config import get_config

        return get_config()["metadata"].get("langgraph_node")
    except Exception:  # noqa: BLE001 - 不在图内调用属正常情况
        return None


def take_counters(run_id: str) -> dict[str, int]:
    return _counters.pop(run_id, {})


def _bump(run_id: str | None, **delta: int) -> None:
    if not run_id:
        return
    if run_id not in _counters and len(_counters) >= _COUNTERS_MAX:
        _counters.clear()  # 防御：run 异常退出时的残留，丢弃计数不影响业务
    bucket = _counters.setdefault(run_id, {})
    for key, value in delta.items():
        bucket[key] = bucket.get(key, 0) + value


def observe(event: str, data: dict[str, Any]) -> None:
    """record() 的旁路分发。data 已脱敏。"""
    sink = _sink
    if sink is None:
        return
    try:
        observe_context(event, data, current_node())
        if event == "model_call":
            sink.put("model_call", _model_call(data))
        elif event == "knowledge_search":
            sink.put("retrieval_call", _retrieval_call(data))
    except Exception:
        log.debug("analytics observe failed event=%s", event, exc_info=True)


def _ts(data: dict[str, Any]) -> datetime:
    raw = data.get("timestamp")
    try:
        return datetime.fromisoformat(raw) if isinstance(raw, str) else datetime.now(UTC)
    except ValueError:
        return datetime.now(UTC)


def _model_call(data: dict[str, Any]) -> ModelCall:
    attempts = [a for a in (data.get("attempts") or []) if isinstance(a, dict)]
    tried = [a for a in attempts if a.get("outcome") != "skipped"]
    usage = data.get("usage") or {}
    tokens_in = _int(usage.get("input_tokens"))
    tokens_out = _int(usage.get("output_tokens"))
    run_id = data.get("run_id")
    _bump(run_id, model_calls=1, tokens_in=tokens_in or 0, tokens_out=tokens_out or 0)
    error = next((a.get("error") for a in reversed(tried) if a.get("error")), None)
    return ModelCall(
        task=str(data.get("task") or "unknown"),
        session_id=data.get("session_id"),
        run_id=run_id,
        node=current_node(),
        model_used=data.get("model_used"),
        lane=data.get("lane"),
        status=str(data.get("status") or "ok"),
        attempts=max(1, len(tried)),
        # 降级：不止一次真正发出的尝试（首选失败后换模型 / 换厂商）
        fallback_used=len(tried) > 1,
        stream=bool(data.get("stream")),
        latency_ms=_int(data.get("latency_ms")),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        error_type=str(error)[:80] if error else None,
        created_at=_ts(data),
    )


def _retrieval_call(data: dict[str, Any]) -> RetrievalCall:
    scope = data.get("scope") or {}
    scores = [s for s in (data.get("scores") or []) if isinstance(s, (int, float))]
    hit_ids = data.get("hit_ids") or []
    run_id = data.get("run_id")
    _bump(run_id, retrievals=1)
    return RetrievalCall(
        status=str(data.get("status") or "unknown"),
        session_id=data.get("session_id"),
        run_id=run_id,
        node=current_node(),
        round=_int(data.get("round")),
        kb=data.get("kb"),
        product_state=scope.get("product_state"),
        sku=scope.get("sku"),
        category=scope.get("category"),
        allowed_count=_int(data.get("allowed_count")),
        hits=len(hit_ids) if isinstance(hit_ids, list) else None,
        top_score=float(scores[0]) if scores else None,
        latency_ms=_int(data.get("latency_ms")),
        query=str(data.get("query"))[:500] if data.get("query") else None,
        created_at=_ts(data),
    )


def _int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)
