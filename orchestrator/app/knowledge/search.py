"""一轮检索的共享实现（阶段 3，design.md §3.2 S0 / S1）：图节点 retrieve 与 haike-kb eval 共用，保证评测跑的就是线上链路。

一轮 = 原 query（+ 确定性同义变体）× 两个 WeKnora 库 并发 hybrid_search → 每库按 RRF 合并多变体 → 可选适配器侧 rerank
（+ 本地 FAQ 索引作为第三个「库」kb_faq）。所有开关来自 RetrievalConfig，默认全关时行为 = 原 query 两库各一次。
返回每库 ToolResult（供 rewrite 决策读状态 / allowed_count）与 trace 条目（供 retrieval_trace / 观测）。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from app.diagnose.config import RetrievalConfig
from app.diagnose.expand import expand_queries
from app.knowledge.adapter import Hit, KnowledgeScope, ToolResult
from app.knowledge.faq import LocalFaqIndex
from app.knowledge.rerank import DashScopeReranker, rerank_trace

WEKNORA_KBS = ("kb_manual", "kb_tickets")
_STATUS_RANK = {"ok": 0, "replay": 0, "no_match": 1, "unavailable": 2}


@dataclass
class RoundOutcome:
    results: dict[str, ToolResult]
    trace: list[dict[str, Any]] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)  # 原 query 在前

    @property
    def hits(self) -> list[Hit]:
        return [h for r in self.results.values() for h in r.hits]


def rrf_merge(per_query: list[tuple[str, ToolResult]], *, k: int, top_k: int) -> ToolResult:
    """同库多变体结果按 Reciprocal Rank Fusion 合并：score = Σ 1/(k+rank)，同 evidence_id 取并集并记 source_queries。
    状态：任一 ok → ok；全部 unavailable → unavailable；否则 no_match（no_match / unavailable 混合按 unavailable，
    与 09 §4.1「部分故障不算正常无命中」一致）。"""
    if len(per_query) == 1:
        return per_query[0][1]
    fused: dict[str, Hit] = {}
    scores: dict[str, float] = {}
    sources: dict[str, list[str]] = {}
    for query, res in per_query:
        for rank, h in enumerate(res.hits, start=1):
            scores[h.evidence_id] = scores.get(h.evidence_id, 0.0) + 1.0 / (k + rank)
            sources.setdefault(h.evidence_id, []).append(query)
            fused.setdefault(h.evidence_id, h)  # 首个变体的 snippet 优先
    hits: list[Hit] = []
    for eid, h in fused.items():
        h.rrf_score = round(scores[eid], 6)
        h.score = h.rrf_score
        h.source_queries = tuple(sources[eid])
        hits.append(h)
    hits.sort(key=lambda h: (h.counter_evidence, -h.score))
    fused_total = len(hits)
    hits = hits[:top_k]
    statuses = [r.status for _, r in per_query]
    if any(s in ("ok", "replay") for s in statuses):
        status = "ok"
    elif any(s == "unavailable" for s in statuses):  # 全部或部分故障都算 unavailable
        status = "unavailable"
    else:
        status = "no_match"
    base = per_query[0][1]
    return ToolResult(
        status,
        hits if status == "ok" else [],
        hint=base.hint if status != "ok" else None,
        truncated=any(r.truncated for _, r in per_query) or fused_total > len(hits),
        total_hits=fused_total,
        kb=base.kb,
        query=per_query[0][0],
        allowed_count=max(r.allowed_count for _, r in per_query),
        latency_ms=max(r.latency_ms for _, r in per_query),
        detail=next((r.detail for _, r in per_query if r.detail), None),
    )


def _kb_trace(
    kb: str,
    query: str,
    scope: KnowledgeScope,
    r: ToolResult,
    *,
    round_no: int,
    variant_idx: int,
    session_id: str,
    run_id: str,
) -> dict[str, Any]:
    return {
        "round": round_no,
        "kb": kb,
        "query": query,
        "variant_idx": variant_idx,
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
    faq_index: LocalFaqIndex | None = None,
    reranker: DashScopeReranker | None = None,
    allow_rerank: bool = True,
) -> RoundOutcome:
    queries = [query]
    trace: list[dict[str, Any]] = []
    if cfg.multi_query.enabled and scope.category in cfg.multi_query.categories:
        variants = expand_queries(query, cfg.query_rewrite.synonyms, cfg.multi_query.max_variants)
        # 请求数上限：变体数 × 库数 ≤ max_requests_per_round
        max_variants = max(0, cfg.multi_query.max_requests_per_round // len(WEKNORA_KBS) - 1)
        variants = variants[:max_variants]
        queries += variants
        if variants:
            trace.append(
                {
                    "round": round_no,
                    "kb": "*",
                    "event": "query_expanded",
                    "query": query,
                    "variants": variants,
                    "session_id": session_id,
                    "run_id": run_id,
                }
            )
    # 变体 × 库 并发（P0-1 的两库并发是其特例）
    pairs = [(kb, q) for q in queries for kb in WEKNORA_KBS]
    raw = await asyncio.gather(*(adapter.hybrid_search(kb, q, top_k, scope) for kb, q in pairs))
    per_kb: dict[str, list[tuple[str, ToolResult]]] = {kb: [] for kb in WEKNORA_KBS}
    for (kb, q), r in zip(pairs, raw, strict=True):
        for h in r.hits:
            h.round = round_no
            if not h.source_queries:
                h.source_queries = (q,)
        per_kb[kb].append((q, r))
    for kb in WEKNORA_KBS:
        for idx, (q, r) in enumerate(per_kb[kb]):
            trace.append(
                _kb_trace(
                    kb,
                    q,
                    scope,
                    r,
                    round_no=round_no,
                    variant_idx=idx,
                    session_id=session_id,
                    run_id=run_id,
                )
            )
    results: dict[str, ToolResult] = {}
    for kb in WEKNORA_KBS:
        results[kb] = rrf_merge(per_kb[kb], k=cfg.multi_query.rrf_k, top_k=top_k)
        if len(per_kb[kb]) > 1:
            trace.append(
                {
                    "round": round_no,
                    "kb": kb,
                    "event": "fused",
                    "merged_from": len(per_kb[kb]),
                    "kept": [h.evidence_id for h in results[kb].hits],
                    "status": results[kb].status,
                    "session_id": session_id,
                    "run_id": run_id,
                }
            )
    if cfg.faq.enabled and faq_index is not None:
        fr = faq_index.search(query, cfg.faq.top_k, scope)
        for h in fr.hits:
            h.round = round_no
            h.source_queries = (query,)
        results["kb_faq"] = fr
        trace.append(
            _kb_trace(
                "kb_faq",
                query,
                scope,
                fr,
                round_no=round_no,
                variant_idx=0,
                session_id=session_id,
                run_id=run_id,
            )
        )
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


KB_PRIORITY = {"kb_manual": 0, "kb_faq": 1, "kb_tickets": 2}


def interleave_kbs(
    results: dict[str, ToolResult], *, k: int = 60, top_k: int | None = None
) -> list[Hit]:
    """跨库合并：各库分值量纲不同（WeKnora RRF ≈ 0.016、本地 FAQ 相似度 0.3–1、rerank relevance 0–1），
    不能按原始分混排。按库内名次做 RRF（1/(k+rank)），同名次按 kb_manual > kb_faq > kb_tickets 破平，
    反证工单仍排最后。图内进 synthesize 的顺序与评测 top-k 用同一函数。"""
    scored: list[tuple[float, int, int, Hit]] = []
    for kb, r in results.items():
        for rank, h in enumerate(r.hits, start=1):
            scored.append((1.0 / (k + rank), KB_PRIORITY.get(kb, 9), rank, h))
    scored.sort(key=lambda x: (x[3].counter_evidence, -x[0], x[1], x[2]))
    hits = [x[3] for x in scored]
    return hits[:top_k] if top_k else hits


def merge_status(a: str, b: str) -> str:
    return min((a, b), key=lambda x: _STATUS_RANK.get(x, 3))
