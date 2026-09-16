"""证据可达性基线（离线，不需要人工标注集）。

回答三个确定性问题，全部可进 CI：

- B 分块未截断：锚点标记与它那段正文有没有被切到不同子块。这是 G2′ 主引用能否按标记
  认人的前提——标记落单了，运行时就只能退回按已审核原文匹配。
- A 锚点可达：用步骤标题当 query 检索，锚点那一段进不进 top-k。入库了但检索不到的内容，
  等于没有。
- C 元数据完整：doc_version / sku_list 缺失即 KnowledgeScope 过滤失效。

对标外部方案提到的 ParseBench：我们没有 PDF 解析环节，等价的天花板在分块与元数据。
详见 docs/claude/spec_grounded_citation_20260916.md §5。
"""

from __future__ import annotations

from typing import Any

from app.knowledge.adapter import KnowledgeScope, WeKnoraKnowledgeAdapter
from app.knowledge.anchors import TEXT_PROBE_CHARS, anchor_marker
from app.plans.library import PlanLibrary


def plan_anchors(library: PlanLibrary) -> list[dict[str, Any]]:
    """plans.yaml 里每个被步骤引用的锚点，带上它的已审核原文与一个步骤标题（当检索 query）。"""
    out: dict[str, dict[str, Any]] = {}
    for plan in library.plans:
        for step in plan.steps:
            key = step.evidence_key
            src = library.evidence.get(key)
            if src is None or key in out:
                continue
            doc_id, _, chunk_id = key.partition("#")
            out[key] = {
                "evidence_key": key,
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "source": src.source,
                "text": src.snippet,
                "query": step.title,
                "plan_id": plan.plan_id,
                "step_id": step.step_id,
            }
    return [out[k] for k in sorted(out)]


def check_chunking(
    anchors: list[dict[str, Any]], chunks_by_doc: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """B(i)：标记与正文同块吗。

    verdict:
    - same_chunk    标记与正文首句在同一子块 → 运行时可按标记认主引用
    - split         两者都在库里但不同块 → 只能按已审核原文认，标记不可靠
    - text_only     语料本来就没有标记（troubleshooting_rv#eN），正文在 → 按原文认
    - text_missing  已审核原文在库里找不到 → plans.yaml 与语料已经不同步
    - no_chunks     该 doc 不走 WeKnora 子块（FAQ 走独立索引）
    """
    rows = []
    for a in anchors:
        chunks = chunks_by_doc.get(a["doc_id"]) or []
        probe = (a["text"] or "").strip()[:TEXT_PROBE_CHARS]
        marker = anchor_marker(a["chunk_id"])
        row = {**a, "marker": marker}
        if not chunks:
            rows.append({**row, "verdict": "no_chunks"})
            continue
        with_marker = [c for c in chunks if marker and marker in (c.get("content") or "")]
        with_text = [c for c in chunks if probe and probe in (c.get("content") or "")]
        row["marker_chunks"] = [c["id"] for c in with_marker]
        row["text_chunks"] = [c["id"] for c in with_text]
        if not with_text:
            row["verdict"] = "text_missing"
        elif marker is None:
            row["verdict"] = "text_only"
        elif not with_marker:
            row["verdict"] = "marker_missing"
        elif {c["id"] for c in with_marker} & {c["id"] for c in with_text}:
            row["verdict"] = "same_chunk"
        else:
            row["verdict"] = "split"
        rows.append(row)
    return rows


def _scope_for_doc(doc_id: str, adapter: WeKnoraKnowledgeAdapter) -> KnowledgeScope | None:
    """锚点所在文档可见的最小 scope。

    计划大多是 category_generic，而 manual_rv_v1 是 sku 文档——只有确认到型号的会话才看得见它。
    不按文档 scope 取，整份手册的锚点都会被判不可达，那测的是范围控制而不是可达性。
    """
    for kb in ("kb_manual", "kb_tickets"):
        for e in adapter.index.get(kb, []):
            if e.doc_id != doc_id:
                continue
            if e.scope == "sku":
                return KnowledgeScope("confirmed_sku", e.category, e.sku_list[0] if e.sku_list else None)
            return KnowledgeScope("category_only", e.category, None)
    return None


async def check_reachable(
    anchors: list[dict[str, Any]], adapter: WeKnoraKnowledgeAdapter, *, top_k: int = 6
) -> list[dict[str, Any]]:
    """A：用步骤标题当 query 跑线上同款检索，锚点那一段进不进 top-k。

    走 search_round 而不是裸 hybrid_search，是为了让多变体、FAQ 与 rerank 的开关与线上一致——
    锚点在实验室能召回、线上召不回，这个基线就没有意义。

    每个锚点在它所属文档可见的 scope 下测；文档不在 WeKnora 索引里（FAQ 走独立索引）时，
    FAQ 关闭则记 skipped_faq_off，不算红。
    """
    from app.diagnose.config import get_retrieval_config
    from app.knowledge.anchors import match_anchor
    from app.knowledge.faq import get_faq_index
    from app.knowledge.search import interleave_kbs, search_round

    cfg = get_retrieval_config()
    faq_index = get_faq_index() if cfg.faq.enabled else None
    rows = []
    for a in anchors:
        scope = _scope_for_doc(a["doc_id"], adapter)
        if scope is None:
            verdict = "reachable" if faq_index else "skipped_faq_off"
            if faq_index is None:
                rows.append({**a, "scope": "-", "match": "none", "hit_rank": None, "verdict": verdict})
                continue
            scope = KnowledgeScope("category_only", "robot_vacuum", None)
        out = await search_round(
            adapter,
            a["query"],
            scope,
            top_k,
            cfg=cfg,
            round_no=1,
            session_id="anchors",
            run_id=a["evidence_key"],
            faq_index=faq_index,
        )
        hits = interleave_kbs(out.results, top_k=top_k)
        evidence = {h.evidence_id: h.as_internal_item() for h in hits}
        eid, how = match_anchor(a["evidence_key"], a["text"], evidence)
        rows.append(
            {
                **a,
                "scope": scope.sku or scope.category,
                "n_hits": len(hits),
                "hit_rank": next(
                    (i + 1 for i, h in enumerate(hits) if h.evidence_id == eid), None
                ),
                "match": how,
                "verdict": "reachable" if eid else "unreachable",
            }
        )
    return rows
