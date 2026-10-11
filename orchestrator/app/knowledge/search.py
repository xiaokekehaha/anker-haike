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


EXTRA_WEIGHT = 0.5


def fuse_queries(primary: ToolResult, extra: ToolResult, top_k: int, *, k: int = 60, extra_weight: float = EXTRA_WEIGHT) -> ToolResult:
    """同一库两条查询的结果按名次做加权 RRF 合并（w/(k+rank) 相加）：原文为主，英文描述为辅。
    英文描述是模型的转述，会丢掉原文里的推送文字等信号（T18「De mop met rol is verstopt」被概括成 mop obstructed，
    等权合并时把原文排第 1 的金标挤出前 5）。降权后两路都命中的条目靠前，英文独有的条目补到原文前几名之后，
    不顶掉原文已经排在前面的条目（T39 / T57 / T59：原文没召回的离线 / 连接条目由英文补进来）。"""
    if extra.status != "ok" or not extra.hits:
        return primary
    if primary.status != "ok" or not primary.hits:
        return extra
    scores: dict[str, float] = {}
    first: dict[str, Hit] = {}
    for weight, r in ((1.0, primary), (extra_weight, extra)):
        for rank, h in enumerate(r.hits, start=1):
            scores[h.evidence_id] = scores.get(h.evidence_id, 0.0) + weight / (k + rank)
            if h.evidence_id in first:
                kept = first[h.evidence_id]
                kept.source_queries = tuple(dict.fromkeys((*kept.source_queries, *h.source_queries)))
            else:
                first[h.evidence_id] = h
    ordered = sorted(first, key=lambda eid: -scores[eid])[:top_k]
    return ToolResult(
        primary.status, [first[eid] for eid in ordered], hint=primary.hint, truncated=primary.truncated or extra.truncated,
        total_hits=max(primary.total_hits, extra.total_hits), kb=primary.kb, query=primary.query,
        allowed_count=primary.allowed_count, latency_ms=primary.latency_ms + extra.latency_ms,
        raw_hits=primary.raw_hits + extra.raw_hits,
    )


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
    english: str | None = None,
) -> RoundOutcome:
    """english：intake 给的英文现象描述（官方 Q&A 是英文）。与原文查询各检索一次后按名次合并；与原文相同时不重复查。"""
    results: dict[str, ToolResult] = {}
    trace: list[dict[str, Any]] = []
    queries = [query, *([english] if english and english.casefold() != query.casefold() else [])]
    for kb in WEKNORA_KBS:
        per_query = []
        for q in queries:
            r = await adapter.hybrid_search(kb, q, top_k, scope)
            for h in r.hits:
                h.round = round_no
                if not h.source_queries:
                    h.source_queries = (q,)
            per_query.append(r)
            trace.append(_kb_trace(kb, q, scope, r, round_no=round_no, session_id=session_id, run_id=run_id))
        results[kb] = per_query[0] if len(per_query) == 1 else fuse_queries(per_query[0], per_query[1], top_k)
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
    return RoundOutcome(results=results, trace=trace, queries=queries)


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
