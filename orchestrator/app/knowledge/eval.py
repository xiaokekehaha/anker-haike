"""检索评测（有界 Agentic RAG 阶段 2，design.md §9）：用 data/eval/retrieval/cases.yaml 直接打 KnowledgeAdapter。

只评检索层（query 规范化 → 两库 hybrid_search），不跑模型：
- hit@k：expected_doc_ids 任一出现在合并后 top-k 的 doc_id 中（expected 为空的样例不计入，另算泄漏）
- precision@k：top-k 中 doc_id ∈ expected_doc_ids 的比例（expected 为空的样例不计入）
- leak：expected 为空（无知识）却返回命中的样例数；scope_leak：命中了当前 scope 不该看见的文档
- 按 tag 分组给 hit@k；记录每样例 query、状态、命中与延迟
结果写 reports/retrieval/<stamp>_<arm>.md 与 .json。expected_outcome / expected_plan 需要 synthesize，留给后续阶段。
"""

from __future__ import annotations

import collections
import json
import os
import re
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from app.diagnose.config import RetrievalConfig, get_retrieval_config
from app.diagnose.query import build_query
from app.knowledge.adapter import KnowledgeScope, WeKnoraKnowledgeAdapter
from app.knowledge.faq import get_faq_index
from app.knowledge.rerank import DashScopeReranker
from app.knowledge.search import interleave_kbs, search_round
from app.knowledge.weknora_client import WeKnoraClient


def case_state(case: dict[str, Any]) -> dict[str, Any]:
    """把评测样例还原成 build_query / KnowledgeScope 需要的最小 state。"""
    ps = case["product_state"]
    state: dict[str, Any] = {
        "product_state": ps,
        "text": case.get("text", ""),
        "symptoms": list(case.get("symptoms") or []),
    }
    if ps == "confirmed_sku":
        state["product_confirmed"] = {
            "sku": case["sku"],
            "name": case.get("product_name") or case["sku"],
            "category": case["category"],
        }
    else:
        state["category"] = case["category"]
    return state


def case_scope(case: dict[str, Any]) -> KnowledgeScope:
    ps = case["product_state"]
    return KnowledgeScope(
        ps,
        case["category"],
        case.get("sku") if ps == "confirmed_sku" else None,
    )


def merge_top_k(results: dict[str, Any], top_k: int) -> list[Any]:
    """与图内 retrieve 相同的跨库合并（search.interleave_kbs）。"""
    return interleave_kbs(results, top_k=top_k)


_CHUNK_TOKEN = re.compile(r"c\d+|faq q\d+|第3章表|\b[A-E]\b|\b[1-5]\b")


def chunk_markers(hint: str | None) -> list[str]:
    """expected_chunk_hint → 命中正文里应出现的标记（阶段 4 分块级金标）：
    c12 → 「（c12）」；A–E → 排障手册小节「## A.」；1–5 → v2 手册小节「## 1 」；第3章表 → 指示灯表头；faq qN → FAQ 条目 id。"""
    out: list[str] = []
    for tok in _CHUNK_TOKEN.findall(hint or ""):
        if tok.startswith("c"):
            out.append(f"（{tok}）")
        elif tok.startswith("faq "):
            out.append(f"faq_rv#{tok.split()[1]}")
        elif tok == "第3章表":
            out.append("| 现象 | 含义 |")
        elif tok.isalpha():
            out.append(f"## {tok}.")
        else:
            out.append(f"## {tok} ")
    return out


def _hit_text(h: Any) -> str:
    return f"{h.evidence_id}\n{h.full_text or ''}\n{h.snippet}"


def is_gold(h: Any, case: dict[str, Any]) -> bool:
    """金标命中：doc_id 在 expected_doc_ids 里，或（工单）根因与 expected_ticket_cause 一致。
    工单同因的有好几条，逐条列 id 既繁琐又脆弱，按根因匹配更稳（标注指南见 ANNOTATION.md）。"""
    if h.doc_id in set(case.get("expected_doc_ids") or []):
        return True
    cause = case.get("expected_ticket_cause")
    return bool(cause and h.source == "kb_tickets" and f"原因：{cause}" in (h.snippet or ""))


def score_case(case: dict[str, Any], hits: list[Any]) -> dict[str, Any]:
    expected = bool(case.get("expected_doc_ids") or case.get("expected_ticket_cause"))
    docs = [h.doc_id for h in hits]
    gold = [is_gold(h, case) for h in hits]
    out: dict[str, Any] = {"doc_ids": docs, "n_hits": len(hits)}
    if expected:
        out["hit"] = any(gold)
        out["precision"] = (sum(gold) / len(gold)) if gold else 0.0
        out["first_rank"] = next((i + 1 for i, g in enumerate(gold) if g), None)
        markers = chunk_markers(case.get("expected_chunk_hint"))
        if markers:
            texts = [_hit_text(h) for h in hits]
            out["chunk_hit"] = any(m in t for m in markers for t in texts)
            out["chunk_rank"] = next(
                (i + 1 for i, t in enumerate(texts) if any(m in t for m in markers)), None
            )
    else:
        out["leak"] = bool(docs)
    return out


async def _model_side(
    case: dict[str, Any], hits: list[Any], *, cfg: RetrievalConfig, router: Any, lane: str
) -> dict[str, Any]:
    """--with-synthesize：真实模型跑 grade（若开）+ synthesize，比较 expected_plan / expected_outcome。"""
    from app.diagnose.grade import apply_assessment, grade_hits
    from app.diagnose.synthesize import synthesize
    from app.plans.runtime import get_plan_library

    state = case_state(case)
    out: dict[str, Any] = {}
    kept = hits
    if cfg.grade.enabled and hits:
        a = await grade_hits(
            router,
            hits=hits,
            user_text=state["text"],
            symptoms=state["symptoms"],
            product=(state.get("product_confirmed") or {}).get("name"),
            cfg=cfg.grade,
            budget_ms=cfg.grade.budget_ms,
            session_id=f"eval-{case['id']}",
            lane=lane,
        )
        kept = apply_assessment(list(hits), a, keep_min=cfg.grade.keep_min)
        out["grade"] = {
            "status": a.status,
            "reason": a.reason,
            "coverage": a.coverage,
            "model": a.model_used,
            "ms": a.latency_ms,
            "filtered": a.filtered_ids,
            "kept_min": a.kept_min_ids,
            # 金标文档被判 irrelevant = 评分假阴性；非金标被判 relevant 只作参考（金标是文档级）
            "false_negative": [
                h.evidence_id for h in hits if is_gold(h, case) and h.grade == "irrelevant"
            ],
            "relevant_n": len(a.relevant_ids),
        }
    scope = case_scope(case)
    allowed = get_plan_library().allowed_for(category=scope.category, sku=scope.sku)
    st = {**state, "emotion": {"strategy": "normal"}}
    t0 = time.perf_counter()
    syn = await synthesize(
        router,
        state=st,
        allowed=allowed,
        evidence=[h.as_internal_item() for h in kept],
        observations=[],
        budget_ms=cfg.synthesize.budget_ms,
        max_hypotheses=cfg.synthesize.max_hypotheses,
        session_id=f"eval-{case['id']}",
        lane=lane,
    )
    ranked = syn.get("plans_ranked") or []
    top = ranked[0]["plan_id"] if ranked else None
    outcome = (
        "escalate"
        if not ranked
        else ("standard_flow" if ranked[0].get("source") == "standard_flow" else "evidence")
    )
    exp_plan, exp_out = case.get("expected_plan"), case.get("expected_outcome")
    out["synth"] = {
        "top_plan": top,
        "ranked": [p["plan_id"] for p in ranked],
        "source": ranked[0].get("source") if ranked else None,
        "degraded": syn.get("degraded"),
        "model": (syn.get("model_trace") or {}).get("model_used"),
        "ms": int((time.perf_counter() - t0) * 1000),
        "outcome": outcome,
        "plan_match": (top == exp_plan) if exp_plan else None,
        # 安全类样例的 escalate 来自规则 R4（检索之前），synthesize 层不比较
        "outcome_match": (outcome == exp_out)
        if exp_out and "安全" not in (case.get("tags") or [])
        else None,
    }
    return out


async def evaluate(
    adapter: WeKnoraKnowledgeAdapter,
    cases: list[dict[str, Any]],
    *,
    top_k: int,
    cfg: RetrievalConfig | None = None,
    with_synthesize: bool = False,
    lane: str = "domestic",
) -> list[dict[str, Any]]:
    """每条样例跑一轮线上同款 search_round（含 multi_query / faq / rerank 开关），只评检索层；
    with_synthesize 时再用真实模型跑 grade + synthesize，比较 expected_plan / expected_outcome。"""
    cfg = cfg or get_retrieval_config()
    router = None
    if with_synthesize:
        from app.models.runtime import get_model_router

        router = get_model_router()
        if router is None:
            raise RuntimeError("--with-synthesize 需要模型路由（HAIKE_LLM=on 且有厂商 key）")
    await adapter.refresh_index()
    faq_index = get_faq_index() if cfg.faq.enabled else None
    reranker = (
        DashScopeReranker(model=cfg.rerank.model, timeout_s=cfg.rerank.timeout_ms / 1000)
        if cfg.rerank.enabled
        else None
    )
    rows = []
    for case in cases:
        state, scope = case_state(case), case_scope(case)
        query = build_query(state)
        row: dict[str, Any] = {
            "id": case["id"],
            "tags": list(case.get("tags") or []),
            "query": query,
            "scope": {
                "product_state": scope.product_state,
                "category": scope.category,
                "sku": scope.sku,
            },
        }
        if not query:
            row.update({"status": "no_query", "latency_ms": 0, **score_case(case, [])})
            rows.append(row)
            continue
        t0 = time.perf_counter()
        out = await search_round(
            adapter,
            query,
            scope,
            top_k,
            cfg=cfg,
            round_no=1,
            session_id="eval",
            run_id=case["id"],
            faq_index=faq_index,
            reranker=reranker,
        )
        results = out.results
        hits_all = interleave_kbs(results)
        if cfg.parent_expand.enabled:
            if adapter.chunks_loaded_at is None:
                await adapter.refresh_chunks()
            row["expanded"] = adapter.expand_parents(
                hits_all,
                max_items=cfg.parent_expand.max_items,
                max_chars=cfg.parent_expand.max_chars,
            )
        row["latency_ms"] = int((time.perf_counter() - t0) * 1000)
        row["queries"] = out.queries
        row["rerank"] = [
            {"kb": t["kb"], "status": t["status"], "reason": t.get("reason"), "ms": t["latency_ms"]}
            for t in out.trace
            if t.get("event") == "rerank"
        ]
        row["per_kb"] = {
            kb: {
                "status": r.status,
                "allowed": r.allowed_count,
                "hits": len(r.hits),
                "ms": r.latency_ms,
            }
            for kb, r in results.items()
        }
        statuses = [r.status for r in results.values()]
        row["status"] = (
            "unavailable"
            if all(s == "unavailable" for s in statuses)
            else ("ok" if any(r.hits for r in results.values()) else "no_match")
        )
        hits = merge_top_k(results, top_k)
        row.update(score_case(case, hits))
        if router is not None:
            row.update(await _model_side(case, hits, cfg=cfg, router=router, lane=lane))
        row["hits"] = [
            {
                "doc_id": h.doc_id,
                "chunk_id": h.chunk_id,
                "source": h.source,
                "score": round(h.score, 4),
                "case_outcome": h.case_outcome,
                "snippet": h.snippet[:60].replace("\n", " "),
                "full_len": len(h.full_text) if h.full_text else None,
            }
            for h in hits
        ]
        rows.append(row)
    return rows


def _pct(n: float, d: float) -> str:
    return f"{100 * n / d:.0f}%" if d else "n/a"


def _p(values: list[int], q: float) -> int:
    if not values:
        return 0
    s = sorted(values)
    return s[min(len(s) - 1, round(q * (len(s) - 1)))]


def _model_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    syn = [r["synth"] for r in rows if r.get("synth")]
    if not syn:
        return {}
    pm = [x["plan_match"] for x in syn if x["plan_match"] is not None]
    om = [x["outcome_match"] for x in syn if x["outcome_match"] is not None]
    out: dict[str, Any] = {
        "plan_match": f"{sum(pm)}/{len(pm)}",
        "outcome_match": f"{sum(om)}/{len(om)}",
        "synth_degraded": sum(1 for x in syn if x.get("degraded")),
        "synth_p50_ms": _p([x["ms"] for x in syn], 0.5),
    }
    gr = [r["grade"] for r in rows if r.get("grade")]
    if gr:
        out["grade_graded"] = f"{sum(g['status'] == 'graded' for g in gr)}/{len(gr)}"
        out["grade_fail_reasons"] = dict(
            collections.Counter(g.get("reason") for g in gr if g["status"] != "graded")
        )
        out["grade_coverage"] = dict(
            sorted(
                {
                    c: sum(g.get("coverage") == c for g in gr)
                    for c in ("sufficient", "insufficient", "none")
                }.items()
            )
        )
        out["grade_filtered_total"] = sum(len(g["filtered"]) for g in gr)
        out["grade_false_negative"] = sum(len(g["false_negative"]) for g in gr)
        out["grade_p50_ms"] = _p([g["ms"] for g in gr if g["ms"]], 0.5)
    return out


def summarize(rows: list[dict[str, Any]], *, top_k: int) -> dict[str, Any]:
    scored = [r for r in rows if "hit" in r]
    leak_rows = [r for r in rows if "leak" in r]
    lat = [r["latency_ms"] for r in rows if r.get("latency_ms")]
    by_tag: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in scored:
        for t in r["tags"] or ["(untagged)"]:
            by_tag[t].append(r)
    return {
        "cases": len(rows),
        "scored": len(scored),
        f"hit@{top_k}": _pct(sum(r["hit"] for r in scored), len(scored)),
        f"precision@{top_k}": _pct(sum(r["precision"] for r in scored), len(scored)),
        f"chunk_hit@{top_k}": _pct(
            sum(r["chunk_hit"] for r in rows if "chunk_hit" in r),
            sum("chunk_hit" in r for r in rows),
        ),
        "chunk_scored": sum("chunk_hit" in r for r in rows),
        "no_match": sum(r.get("status") == "no_match" for r in rows),
        "unavailable": sum(r.get("status") == "unavailable" for r in rows),
        "leak": f"{sum(r['leak'] for r in leak_rows)}/{len(leak_rows)}",
        "latency_p50_ms": _p(lat, 0.5),
        "latency_p95_ms": _p(lat, 0.95),
        **_model_summary(rows),
        "by_tag": {
            t: {"n": len(rs), f"hit@{top_k}": _pct(sum(r["hit"] for r in rs), len(rs))}
            for t, rs in sorted(by_tag.items(), key=lambda kv: -len(kv[1]))
        },
    }


def _mark(v: bool | None) -> str:
    return "-" if v is None else ("✓" if v else "✗")


def _plan_cell(r: dict[str, Any]) -> str:
    s = r.get("synth")
    if not s:
        return "-"
    g = r.get("grade") or {}
    cov = f" g={g.get('coverage')}" if g else ""
    return f"{_mark(s['plan_match'])} {s.get('top_plan') or '∅'}{cov}"


def _outcome_cell(r: dict[str, Any]) -> str:
    s = r.get("synth")
    return "-" if not s else f"{_mark(s['outcome_match'])} {s['outcome']}"


def render_markdown(
    *,
    arm: str,
    cases_meta: dict[str, Any],
    summary: dict[str, Any],
    rows: list[dict[str, Any]],
    top_k: int,
) -> str:
    lines = [
        f"# 检索评测 {arm} 组（{datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}）",
        "",
        (
            f"评测集 version={cases_meta.get('version')}，"
            f"annotated_count={cases_meta.get('annotated_count', 0)}。"
            "只评检索层（不跑模型）；未标注样例的结果只用于回归对比。"
        ),
        "",
        "## 汇总",
        "",
        "| 指标 | 值 |",
        "| --- | --- |",
    ]
    for k, v in summary.items():
        if k != "by_tag":
            lines.append(f"| {k} | {v} |")
    lines += ["", "## 按标签", "", f"| 标签 | n | hit@{top_k} |", "| --- | --- | --- |"]
    for t, v in summary["by_tag"].items():
        lines.append(f"| {t} | {v['n']} | {v[f'hit@{top_k}']} |")
    lines += [
        "",
        "## 逐样例",
        "",
        "| id | 状态 | hit | 首命中位 | chunk | 命中文档 | ms | query（+变体数） | plan | outcome |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        hit = "leak" if r.get("leak") else ("✓" if r.get("hit") else ("✗" if "hit" in r else "-"))
        chunk = (
            f"✓@{r.get('chunk_rank')}" if r.get("chunk_hit") else ("✗" if "chunk_hit" in r else "-")
        )
        nv = len(r.get("queries") or []) - 1
        lines.append(
            f"| {r['id']} | {r.get('status')} | {hit} | {r.get('first_rank') or '-'} | {chunk} | "
            f"{', '.join(r.get('doc_ids') or []) or '-'} | {r.get('latency_ms', 0)} | "
            f"{r['query'] or '(空)'}{f' (+{nv})' if nv > 0 else ''} | {_plan_cell(r)} | {_outcome_cell(r)} |"
        )
    return "\n".join(lines) + "\n"


async def run_eval(
    client: WeKnoraClient,
    cases_path: Path,
    *,
    arm: str,
    top_k: int,
    out_dir: Path,
    config_path: Path | None = None,
    with_synthesize: bool = False,
) -> int:
    from app.diagnose.config import load_retrieval_config
    from app.knowledge.cli import MANIFEST

    data = yaml.safe_load(cases_path.read_text(encoding="utf-8")) or {}
    cases = data.get("cases") or []
    cfg = load_retrieval_config(config_path) if config_path else get_retrieval_config()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    async with client as c:
        adapter = WeKnoraKnowledgeAdapter(c, manifest["knowledge_bases"])
        rows = await evaluate(
            adapter,
            cases,
            top_k=top_k,
            cfg=cfg,
            with_synthesize=with_synthesize,
            lane=os.environ.get("MODEL_LANE", "domestic"),
        )
    summary = summarize(rows, top_k=top_k)
    summary["kb_ver"] = manifest.get("kb_ver")
    summary["flags"] = {
        "multi_query": cfg.multi_query.enabled,
        "faq": cfg.faq.enabled,
        "rerank": cfg.rerank.enabled,
        "parent_expand": cfg.parent_expand.enabled,
        "grade": cfg.grade.enabled,
        "with_synthesize": with_synthesize,
        "config": str(config_path or "config/retrieval.yaml"),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    md = out_dir / f"{stamp}_{arm}.md"
    md.write_text(
        render_markdown(arm=arm, cases_meta=data, summary=summary, rows=rows, top_k=top_k),
        encoding="utf-8",
    )
    (out_dir / f"{stamp}_{arm}.json").write_text(
        json.dumps({"arm": arm, "summary": summary, "rows": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k != "by_tag"}, ensure_ascii=False, indent=2
        )
    )
    print(f"report: {md}")
    return 0
