"""一轮检索的共享实现：图节点 retrieve 与 haike-kb eval 共用，保证评测跑的就是线上链路。

一轮 = 查询 × 官方 Q&A 库（kb_qa）hybrid_search → 可选适配器侧 rerank。开关来自 RetrievalConfig。
返回每库 ToolResult（供补查决策读状态 / allowed_count）与 trace 条目（供 retrieval_trace / 观测）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.diagnose.config import RetrievalConfig
from app.knowledge.adapter import Hit, KnowledgeScope, ToolResult
from app.knowledge.rerank import DashScopeReranker, rerank_trace

WEKNORA_KBS = ("kb_qa",)
_STATUS_RANK = {"ok": 0, "replay": 0, "no_match": 1, "unavailable": 2}


@dataclass
class RoundOutcome:
    results: dict[str, ToolResult]
    trace: list[dict[str, Any]] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)

    @property
    def hits(self) -> list[Hit]:
        return [h for r in self.results.values() for h in r.hits]


def _kb_trace(
    kb: str,
    query: str,
    scope: KnowledgeScope,
    r: ToolResult,
    *,
    round_no: int,
    session_id: str,
    run_id: str,
) -> dict[str, Any]:
    return {
        "round": round_no,
        "kb": kb,
        "query": query,
        "scope": {
            "product_state": scope.product_state,
            "category": scope.category,
            "sku": scope.sku,
        },
        "status": r.status,
        "allowed_count": r.allowed_count,
        "hit_ids": [h.evidence_id for h in r.hits],
        "scores": [round(h.score, 4) for h in r.hits],
        "truncated": r.truncated,
        "returned_count": r.raw_hits,
        "allowed_hit_count": r.total_hits,
        "candidate_count": len(r.hits),
        "latency_ms": r.latency_ms,
        "session_id": session_id,
        "run_id": run_id,
    }


async def search_round(
    adapter,
    query: str,
    scope: KnowledgeScope,
    top_k: int,
    *,
    cfg: RetrievalConfig,
    round_no: int,
    session_id: str,
    run_id: str,
    reranker: DashScopeReranker | None = None,
    allow_rerank: bool = True,
) -> RoundOutcome:
    results: dict[str, ToolResult] = {}
    trace: list[dict[str, Any]] = []
    for kb in WEKNORA_KBS:
        r = await adapter.hybrid_search(kb, query, top_k, scope)
        for h in r.hits:
            h.round = round_no
            if not h.source_queries:
                h.source_queries = (query,)
        results[kb] = r
        trace.append(_kb_trace(kb, query, scope, r, round_no=round_no, session_id=session_id, run_id=run_id))
    if cfg.rerank.enabled and allow_rerank and reranker is not None:
        for kb in WEKNORA_KBS:
            r = results[kb]
            if len(r.hits) < 2:
                continue
            ordered, outcome = await reranker.rerank(query, list(r.hits))
            r.hits = ordered
            trace.append(
                rerank_trace(kb, outcome, round=round_no, session_id=session_id, run_id=run_id)
            )
    return RoundOutcome(results=results, trace=trace, queries=[query])


def interleave_kbs(
    results: dict[str, ToolResult], *, k: int = 60, top_k: int | None = None
) -> list[Hit]:
    """合并各库结果：按库内名次做 RRF（1/(k+rank)）。只有 kb_qa 一个库时即库内顺序；
    图内进 synthesize 的顺序与评测 top-k 用同一函数。"""
    scored: list[tuple[float, int, Hit]] = []
    for r in results.values():
        for rank, h in enumerate(r.hits, start=1):
            scored.append((1.0 / (k + rank), rank, h))
    scored.sort(key=lambda x: (-x[0], x[1]))
    hits = [x[2] for x in scored]
    return hits[:top_k] if top_k else hits


def merge_status(a: str, b: str) -> str:
    return min((a, b), key=lambda x: _STATUS_RANK.get(x, 3))
