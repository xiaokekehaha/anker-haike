"""适配器侧重排（阶段 3）：直接调百炼 gte-rerank-v2（models.yaml rerank-primary，D17）。

WeKnora v0.8.0 的 hybrid-search 不做 rerank（findings），因此在多变体 RRF 合并之后、进入 synthesize 之前，
可选对每库 top 命中做一次重排。失败 / 超时 / 无 key 一律回退到原顺序并在 trace 记录，不影响主流程。
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.knowledge.adapter import Hit

log = logging.getLogger("knowledge.rerank")
DEFAULT_URL = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"


@dataclass
class RerankOutcome:
    status: str  # ok | skipped | failed
    reason: str | None = None
    model: str | None = None
    latency_ms: int = 0
    order_before: list[str] = field(default_factory=list)
    order_after: list[str] = field(default_factory=list)


class DashScopeReranker:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "gte-rerank-v2",
        base_url: str | None = None,
        timeout_s: float = 2.0,
    ):
        self.api_key = (
            api_key or os.environ.get("RERANK_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
        )
        self.model = model
        self.base_url = base_url or os.environ.get("RERANK_BASE_URL") or DEFAULT_URL
        self.timeout_s = timeout_s

    async def scores(self, query: str, documents: list[str]) -> list[float]:
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "input": {"query": query, "documents": documents},
                    "parameters": {"return_documents": False, "top_n": len(documents)},
                },
            )
            resp.raise_for_status()
            results = (resp.json().get("output") or {}).get("results") or []
        out = [0.0] * len(documents)
        for r in results:
            idx = r.get("index")
            if isinstance(idx, int) and 0 <= idx < len(out):
                out[idx] = float(r.get("relevance_score") or 0.0)
        return out

    async def rerank(self, query: str, hits: list[Hit]) -> tuple[list[Hit], RerankOutcome]:
        """返回重排后的 hits（score 换成 relevance_score，反证仍排最后）与结果记录；失败原样返回。"""
        before = [h.evidence_id for h in hits]
        if len(hits) < 2:
            return hits, RerankOutcome(
                "skipped", "lt2", self.model, order_before=before, order_after=before
            )
        if not self.api_key:
            return hits, RerankOutcome(
                "skipped", "no_api_key", self.model, order_before=before, order_after=before
            )
        start = time.perf_counter()
        try:
            scores = await self.scores(query, [h.snippet for h in hits])
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            log.warning("rerank failed: %s", str(exc)[:200])
            return hits, RerankOutcome(
                "failed",
                f"{type(exc).__name__}",
                self.model,
                int((time.perf_counter() - start) * 1000),
                before,
                before,
            )
        for h, s in zip(hits, scores, strict=True):
            h.rrf_score = h.score
            h.score = s
        ordered = sorted(hits, key=lambda h: (h.counter_evidence, -h.score))
        return ordered, RerankOutcome(
            "ok",
            None,
            self.model,
            int((time.perf_counter() - start) * 1000),
            before,
            [h.evidence_id for h in ordered],
        )


def rerank_trace(kb: str, outcome: RerankOutcome, **extra: Any) -> dict[str, Any]:
    return {
        "event": "rerank",
        "kb": kb,
        "status": outcome.status,
        "reason": outcome.reason,
        "model": outcome.model,
        "latency_ms": outcome.latency_ms,
        "order_before": outcome.order_before,
        "order_after": outcome.order_after,
        **extra,
    }
