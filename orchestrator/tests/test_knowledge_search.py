"""search_round（阶段 3）：变体并发与请求上限、RRF 合并与状态、FAQ 第三库、rerank 失败回退；开关全关 = 现状。"""

from __future__ import annotations

import asyncio

from app.diagnose.config import RetrievalConfig, get_retrieval_config
from app.knowledge.adapter import HINTS, Hit, KnowledgeScope, ToolResult
from app.knowledge.faq import LocalFaqIndex
from app.knowledge.rerank import RerankOutcome
from app.knowledge.search import rrf_merge, search_round

SCOPE = KnowledgeScope("confirmed_sku", "robot_vacuum", "EUFY-X10-PRO-OMNI")


def _hit(eid: str, score: float, *, kb="kb_manual", counter=False) -> Hit:
    return Hit(eid, "k", eid, "manual_rv_v1", "v", kb, f"s-{eid}", score, counter_evidence=counter)


def _cfg(**flags) -> RetrievalConfig:
    cfg = get_retrieval_config().model_copy(deep=True)
    for block, values in flags.items():
        setattr(cfg, block, getattr(cfg, block).model_copy(update=values))
    return cfg


class RecordingAdapter:
    """按 (kb, query) 返回预设；记录并发起点。"""

    def __init__(self, table: dict[tuple[str, str], ToolResult], delay_s: float = 0.0):
        self.table, self.delay_s = table, delay_s
        self.calls: list[tuple[str, str]] = []
        self.in_flight = 0
        self.max_in_flight = 0

    async def hybrid_search(self, kb, query, top_k, allow):
        self.calls.append((kb, query))
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(self.delay_s)
        self.in_flight -= 1
        r = self.table.get(
            (kb, query),
            ToolResult("no_match", hint=HINTS["no_match"], kb=kb, query=query, allowed_count=2),
        )
        r.kb, r.query = kb, query
        return r


class FakeReranker:
    def __init__(self, fail: bool = False):
        self.fail, self.calls = fail, []

    async def rerank(self, query, hits):
        self.calls.append((query, [h.evidence_id for h in hits]))
        before = [h.evidence_id for h in hits]
        if self.fail:
            return hits, RerankOutcome("failed", "HTTPError", "fake", 5, before, before)
        ordered = list(reversed(hits))
        return ordered, RerankOutcome(
            "ok", None, "fake", 5, before, [h.evidence_id for h in ordered]
        )


# ---- rrf_merge ----


def test_rrf_merge_single_variant_passthrough_and_fusion_order():
    r1 = ToolResult("ok", [_hit("a", 0.9), _hit("b", 0.5)], allowed_count=2)
    assert rrf_merge([("q", r1)], k=60, top_k=5) is r1
    r2 = ToolResult("ok", [_hit("b", 0.9), _hit("c", 0.5)], allowed_count=2)
    merged = rrf_merge([("q", r1), ("q2", r2)], k=60, top_k=5)
    ids = [h.evidence_id for h in merged.hits]
    assert ids[0] == "b"  # 两个变体都命中 → 融合分最高
    assert set(ids) == {"a", "b", "c"} and merged.status == "ok"
    b = merged.hits[0]
    assert b.source_queries == ("q", "q2") and abs(b.rrf_score - (1 / 62 + 1 / 61)) < 1e-5
    assert b.snippet == "s-b"  # 首个变体的 snippet 保留


def test_rrf_merge_statuses_and_counter_evidence_last():
    nm = ToolResult("no_match", hint=HINTS["no_match"], allowed_count=2)
    un = ToolResult("unavailable", hint=HINTS["unavailable"], allowed_count=2)
    assert rrf_merge([("q", nm), ("q2", nm)], k=60, top_k=5).status == "no_match"
    assert rrf_merge([("q", nm), ("q2", un)], k=60, top_k=5).status == "unavailable"
    ok = ToolResult(
        "ok", [_hit("t", 0.9, kb="kb_tickets", counter=True), _hit("s", 0.1, kb="kb_tickets")]
    )
    m = rrf_merge([("q", ok), ("q2", un)], k=60, top_k=5)
    assert m.status == "ok" and [h.evidence_id for h in m.hits] == ["s", "t"]


def test_interleave_kbs_uses_rank_not_raw_score_with_kb_priority():
    from app.knowledge.search import interleave_kbs

    results = {
        "kb_tickets": ToolResult(
            "ok", [_hit("t1", 0.9, kb="kb_tickets"), _hit("t2", 0.8, kb="kb_tickets", counter=True)]
        ),
        "kb_faq": ToolResult("ok", [_hit("f1", 0.95, kb="kb_faq")]),
        "kb_manual": ToolResult("ok", [_hit("m1", 0.016), _hit("m2", 0.015)]),
    }
    ids = [h.evidence_id for h in interleave_kbs(results)]
    assert ids == ["m1", "f1", "t1", "m2", "t2"]  # 名次交错 + 手册>FAQ>工单 破平 + 反证最后
    assert [h.evidence_id for h in interleave_kbs(results, top_k=2)] == ["m1", "f1"]


# ---- search_round ----


async def test_flags_off_is_two_concurrent_calls_only():
    ad = RecordingAdapter(
        {("kb_manual", "X 不吸"): ToolResult("ok", [_hit("a", 0.9)])}, delay_s=0.05
    )
    out = await search_round(
        ad, "X 不吸", SCOPE, 5, cfg=_cfg(), round_no=1, session_id="s", run_id="r"
    )
    assert ad.calls == [("kb_manual", "X 不吸"), ("kb_tickets", "X 不吸")] and ad.max_in_flight == 2
    assert set(out.results) == {"kb_manual", "kb_tickets"} and out.queries == ["X 不吸"]
    assert not any(t.get("event") for t in out.trace)  # 无 expanded / fused / rerank 事件
    assert out.results["kb_manual"].hits[0].round == 1


async def test_multi_query_expands_concurrently_and_fuses_with_request_cap():
    syn = {"吸力下降": ["不吸"], "尘盒": ["垃圾盒"], "边刷": ["侧刷"]}
    cfg = _cfg(
        multi_query={"enabled": True, "max_variants": 4, "max_requests_per_round": 4},
        query_rewrite={"synonyms": syn},
    )
    q = "X 不吸 垃圾盒"
    ad = RecordingAdapter(
        {
            ("kb_manual", q): ToolResult("ok", [_hit("a", 0.9), _hit("b", 0.5)]),
            ("kb_manual", "X 吸力下降 垃圾盒"): ToolResult("ok", [_hit("b", 0.9), _hit("c", 0.4)]),
        },
        delay_s=0.05,
    )
    out = await search_round(ad, q, SCOPE, 5, cfg=cfg, round_no=1, session_id="s", run_id="r")
    # 3 个候选变体，但请求上限 4 → 只保留 1 个变体；2 变体 × 2 库 = 4 次并发
    assert out.queries == [q, "X 吸力下降 垃圾盒"] and len(ad.calls) == 4 and ad.max_in_flight == 4
    exp = next(t for t in out.trace if t.get("event") == "query_expanded")
    assert exp["variants"] == ["X 吸力下降 垃圾盒"]
    fused = [t for t in out.trace if t.get("event") == "fused"]
    assert {t["kb"] for t in fused} == {"kb_manual", "kb_tickets"}
    ids = [h.evidence_id for h in out.results["kb_manual"].hits]
    assert ids[0] == "b" and set(ids) == {"a", "b", "c"}
    assert out.results["kb_tickets"].status == "no_match"
    kb_traces = [t for t in out.trace if "event" not in t and t["kb"] == "kb_manual"]
    assert [t["variant_idx"] for t in kb_traces] == [0, 1]


async def test_faq_index_added_as_third_kb_when_enabled():
    idx = LocalFaqIndex(
        entries=[],
        doc_id="faq_rv",
        doc_version="v",
        category="robot_vacuum",
    )
    from app.knowledge.faq import FaqEntry

    idx.entries.append(FaqEntry("q35", "App 连不上机器", ("连不上",), "重新配网"))
    ad = RecordingAdapter({})
    cfg = _cfg(faq={"enabled": True})
    out = await search_round(
        ad,
        "X App 连不上机器",
        SCOPE,
        5,
        cfg=cfg,
        round_no=1,
        session_id="s",
        run_id="r",
        faq_index=idx,
    )
    assert (
        out.results["kb_faq"].status == "ok"
        and out.results["kb_faq"].hits[0].chunk_id == "faq_rv#q35"
    )
    assert out.results["kb_faq"].hits[0].round == 1
    assert any(t.get("kb") == "kb_faq" and "event" not in t for t in out.trace)
    # 开关关：不出现 kb_faq
    out2 = await search_round(
        ad,
        "X App 连不上机器",
        SCOPE,
        5,
        cfg=_cfg(),
        round_no=1,
        session_id="s",
        run_id="r",
        faq_index=idx,
    )
    assert "kb_faq" not in out2.results


async def test_rerank_applies_per_kb_and_falls_back_on_failure():
    table = {("kb_manual", "X 不吸"): ToolResult("ok", [_hit("a", 0.9), _hit("b", 0.5)])}
    cfg = _cfg(rerank={"enabled": True})
    rr = FakeReranker()
    out = await search_round(
        RecordingAdapter(dict(table)),
        "X 不吸",
        SCOPE,
        5,
        cfg=cfg,
        round_no=1,
        session_id="s",
        run_id="r",
        reranker=rr,
    )
    assert [h.evidence_id for h in out.results["kb_manual"].hits] == ["b", "a"]
    assert rr.calls == [("X 不吸", ["a", "b"])]  # 单命中 / 无命中的库不调
    tr = [t for t in out.trace if t.get("event") == "rerank"]
    assert (
        tr[0]["kb"] == "kb_manual"
        and tr[0]["status"] == "ok"
        and tr[0]["order_after"] == ["b", "a"]
    )
    # 失败回退原序
    table2 = {("kb_manual", "X 不吸"): ToolResult("ok", [_hit("a", 0.9), _hit("b", 0.5)])}
    out2 = await search_round(
        RecordingAdapter(table2),
        "X 不吸",
        SCOPE,
        5,
        cfg=cfg,
        round_no=1,
        session_id="s",
        run_id="r",
        reranker=FakeReranker(fail=True),
    )
    assert [h.evidence_id for h in out2.results["kb_manual"].hits] == ["a", "b"]
    assert next(t for t in out2.trace if t.get("event") == "rerank")["status"] == "failed"
    # allow_rerank=False（第二轮 / 预算不足）不调
    rr3 = FakeReranker()
    table3 = {("kb_manual", "X 不吸"): ToolResult("ok", [_hit("a", 0.9), _hit("b", 0.5)])}
    await search_round(
        RecordingAdapter(table3),
        "X 不吸",
        SCOPE,
        5,
        cfg=cfg,
        round_no=2,
        session_id="s",
        run_id="r",
        reranker=rr3,
        allow_rerank=False,
    )
    assert rr3.calls == []
