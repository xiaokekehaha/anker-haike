"""检索评测：63 单主办方工单首封消息 → 金标官方 Q&A（data/eval/tickets/cases.yaml 的 qa_gold / qa_exact）。

只评检索层（与图内同一个 search_round）：
- 查询与线上一致：build_query（产品名 + 原文）；范围按首封 PN 锁型号，没有 PN 时按品类词 category_only。
- recall@k：金标 qa_id 任一出现在 top-k 的 doc_id 中；按客户语言分组统计（工单有英 / 荷 / 德 / 法 / 西）。
- 错误码单走确定性精确命中（qa_exact），不经过检索，这里单列「检索是否也召回」作参考。
结果写 reports/retrieval/<stamp>_<arm>.md 与 .json。
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from app.diagnose.config import RetrievalConfig, get_retrieval_config
from app.diagnose.query import build_query
from app.knowledge.adapter import Hit, KnowledgeScope, WeKnoraKnowledgeAdapter
from app.knowledge.context import select_hits
from app.knowledge.rerank import DashScopeReranker
from app.knowledge.search import interleave_kbs, search_round
from app.knowledge.weknora_client import WeKnoraClient
from app.official.message import parse_message
from app.official.models import OfficialData
from app.sessions.cards import get_catalog
from app.settings import REPO_ROOT

CASES = REPO_ROOT / "data" / "eval" / "tickets" / "cases.yaml"


def gold_of(case: dict[str, Any]) -> list[str]:
    return [*([case["qa_exact"]] if case.get("qa_exact") else []), *(case.get("qa_gold") or [])]


def case_state(case: dict[str, Any], body: str) -> tuple[dict[str, Any], KnowledgeScope | None]:
    """工单首封 → build_query 需要的最小 state 与检索范围；认不出产品返回 None（线上会先追问型号）。"""
    catalog = get_catalog()
    pn = parse_message(body).pn or case.get("pn")
    product = catalog.get(pn) if pn else None
    if product is None:
        # 与线上消歧一致：型号名唯一命中即确认（「omni c20」）；同名多命中（「S1 Pro」）线上会出产品卡，这里不计
        named = catalog.lookup_product(body)
        product = catalog.get(named[0].sku) if len(named) == 1 else None
    if product is not None:
        state = {
            "product_state": "confirmed_sku",
            "text": body,
            "product_confirmed": {"sku": product.sku, "name": product.name, "category": product.category},
        }
        return state, KnowledgeScope("confirmed_sku", product.category, product.sku)
    category = catalog.category_hint(body)
    if not category:
        return {"product_state": "unknown", "text": body}, None
    skus = tuple(p.sku for p in catalog.products if p.category == category and p.in_scope)
    if len(skus) == 1:
        # 品类下只有一款（吸奶器、SoloCam）：线上同样直接确认
        product = catalog.get(skus[0])
        state = {
            "product_state": "confirmed_sku",
            "text": body,
            "product_confirmed": {"sku": product.sku, "name": product.name, "category": category},
        }
        return state, KnowledgeScope("confirmed_sku", category, product.sku)
    state = {"product_state": "category_only", "text": body, "category": category}
    return state, KnowledgeScope("category_only", category, category_skus=skus)


def score_case(gold: list[str], hits: list[Hit], top_k: int) -> dict[str, Any]:
    docs = [h.doc_id for h in hits[:top_k]]
    rank = next((i + 1 for i, d in enumerate(docs) if d in gold), None)
    return {"doc_ids": docs, "hit": rank is not None, "first_rank": rank}


async def evaluate(
    adapter: WeKnoraKnowledgeAdapter,
    cases: list[dict[str, Any]],
    bodies: dict[str, str],
    *,
    top_k: int,
    cfg: RetrievalConfig | None = None,
    english: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """english：工单 id → intake 给的英文现象描述（search_query_en）。给了就与原文查询双路检索，与线上 retrieve 一致。"""
    cfg = cfg or get_retrieval_config()
    await adapter.refresh_index()
    reranker = (
        DashScopeReranker(model=cfg.rerank.model, timeout_s=cfg.rerank.timeout_ms / 1000)
        if cfg.rerank.enabled
        else None
    )
    rows = []
    for case in cases:
        gold = gold_of(case)
        if not gold:
            continue
        state, scope = case_state(case, bodies[case["id"]])
        row: dict[str, Any] = {
            "id": case["id"],
            "language": case.get("language"),
            "exact": bool(case.get("qa_exact")),
            "gold": gold,
        }
        query = build_query(state) if scope is not None else ""
        row["query"] = query[:120]
        row["query_en"] = (english or {}).get(case["id"])
        if not query or scope is None:
            row.update({"status": "no_scope", "hit": False, "first_rank": None, "doc_ids": [], "latency_ms": 0})
            rows.append(row)
            continue
        row["scope"] = {"product_state": scope.product_state, "category": scope.category, "sku": scope.sku}
        t0 = time.perf_counter()
        out = await search_round(
            adapter, query, scope, cfg.retrieval.candidate_k,
            cfg=cfg, round_no=1, session_id="eval", run_id=case["id"], reranker=reranker,
            english=row["query_en"],
        )
        hits = select_hits(interleave_kbs(out.results), cfg.retrieval.final_k)
        row["latency_ms"] = int((time.perf_counter() - t0) * 1000)
        statuses = [r.status for r in out.results.values()]
        row["status"] = "unavailable" if all(s == "unavailable" for s in statuses) else (
            "ok" if hits else "no_match"
        )
        row.update(score_case(gold, hits, top_k))
        rows.append(row)
    return rows


def _pct(n: float, d: float) -> str:
    return f"{100 * n / d:.0f}%" if d else "n/a"


def _p(values: list[int], q: float) -> int:
    if not values:
        return 0
    s = sorted(values)
    return s[min(len(s) - 1, round(q * (len(s) - 1)))]


def summarize(rows: list[dict[str, Any]], *, top_k: int) -> dict[str, Any]:
    semantic = [r for r in rows if not r["exact"]]
    by_lang: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in semantic:
        by_lang[r.get("language") or "?"].append(r)
    lat = [r["latency_ms"] for r in rows if r.get("latency_ms")]
    return {
        "cases": len(rows),
        "semantic_cases": len(semantic),
        f"recall@{top_k}": _pct(sum(r["hit"] for r in semantic), len(semantic)),
        f"exact_also_retrieved@{top_k}": _pct(sum(r["hit"] for r in rows if r["exact"]), sum(r["exact"] for r in rows)),
        "no_scope": sum(r["status"] == "no_scope" for r in rows),
        "no_match": sum(r["status"] == "no_match" for r in rows),
        "unavailable": sum(r["status"] == "unavailable" for r in rows),
        "latency_p50_ms": _p(lat, 0.5),
        "latency_p95_ms": _p(lat, 0.95),
        "by_language": {
            lang: {"n": len(rs), f"recall@{top_k}": _pct(sum(r["hit"] for r in rs), len(rs))}
            for lang, rs in sorted(by_lang.items(), key=lambda kv: -len(kv[1]))
        },
    }


def render_markdown(*, arm: str, summary: dict[str, Any], rows: list[dict[str, Any]], top_k: int) -> str:
    lines = [
        f"# 检索评测 {arm} 组（{datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}）",
        "",
        (
            "63 单工单首封消息打 kb_qa，金标为 data/eval/tickets/cases.yaml 的 qa_gold / qa_exact。"
            "recall 只统计无错误码的现象描述单；有错误码的单线上走精确命中，这里列出检索是否也召回作参考。"
        ),
        "",
        "## 汇总",
        "",
        "| 指标 | 值 |",
        "| --- | --- |",
    ]
    for k, v in summary.items():
        if k != "by_language":
            lines.append(f"| {k} | {v} |")
    lines += ["", "## 按语言", "", f"| 语言 | n | recall@{top_k} |", "| --- | --- | --- |"]
    for lang, v in summary["by_language"].items():
        lines.append(f"| {lang} | {v['n']} | {v[f'recall@{top_k}']} |")
    lines += [
        "",
        "## 逐单",
        "",
        "| id | 语言 | 精确码 | 状态 | hit | 首命中位 | 金标 | 命中文档 | ms |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| {r['id']} | {r.get('language')} | {'是' if r['exact'] else ''} | {r['status']} | "
            f"{'✓' if r['hit'] else '✗'} | {r.get('first_rank') or '-'} | {', '.join(r['gold'])} | "
            f"{', '.join(r.get('doc_ids') or []) or '-'} | {r.get('latency_ms', 0)} |"
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
    english_path: Path | None = None,
) -> int:
    from app.diagnose.config import load_retrieval_config
    from app.knowledge.cli import MANIFEST

    data = yaml.safe_load(cases_path.read_text(encoding="utf-8")) or {}
    bodies = {t.id: t.body for t in OfficialData().tickets}
    cfg = load_retrieval_config(config_path) if config_path else get_retrieval_config()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    async with client as c:
        adapter = WeKnoraKnowledgeAdapter(c, manifest["knowledge_bases"])
        english = json.loads(english_path.read_text(encoding="utf-8")) if english_path else None
        rows = await evaluate(adapter, data.get("cases") or [], bodies, top_k=top_k, cfg=cfg, english=english)
    summary = summarize(rows, top_k=top_k)
    summary["kb_ver"] = manifest.get("kb_ver")
    summary["rerank"] = cfg.rerank.enabled
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    md = out_dir / f"{stamp}_{arm}.md"
    md.write_text(render_markdown(arm=arm, summary=summary, rows=rows, top_k=top_k), encoding="utf-8")
    (out_dir / f"{stamp}_{arm}.json").write_text(
        json.dumps({"arm": arm, "summary": summary, "rows": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "by_language"}, ensure_ascii=False, indent=2))
    print(f"report: {md}")
    return 0
