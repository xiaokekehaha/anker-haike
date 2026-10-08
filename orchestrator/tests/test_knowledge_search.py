"""search_round：单库 kb_qa 一次请求、rerank 失败回退、跨库合并按名次。"""

from __future__ import annotations

import asyncio

from app.diagnose.config import RetrievalConfig, get_retrieval_config
from app.knowledge.adapter import HINTS, Hit, KnowledgeScope, ToolResult
from app.knowledge.rerank import RerankOutcome
from app.knowledge.search import interleave_kbs, search_round

SCOPE = KnowledgeScope("confirmed_sku", "robot_vacuum", "T2351")


def _hit(eid: str, score: float, *, kb="kb_qa") -> Hit:
    return Hit(eid, "k", eid, "rv-0001", "v", kb, f"s-{eid}", score)


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


# ---- interleave_kbs ----


def test_interleave_kbs_uses_rank_not_raw_score():
    # 分值量纲因 rerank 与否而不同：按库内名次合并，不比原始分
    results = {"kb_qa": ToolResult("ok", [_hit("q1", 0.016), _hit("q2", 0.9), _hit("q3", 0.5)])}
    assert [h.evidence_id for h in interleave_kbs(results)] == ["q1", "q2", "q3"]
    assert [h.evidence_id for h in interleave_kbs(results, top_k=2)] == ["q1", "q2"]


# ---- search_round ----


async def test_flags_off_is_single_kb_qa_call_only():
    ad = RecordingAdapter(
        {("kb_qa", "X 不吸"): ToolResult("ok", [_hit("a", 0.9)])}, delay_s=0.05
    )
    out = await search_round(
        ad, "X 不吸", SCOPE, 5, cfg=_cfg(), round_no=1, session_id="s", run_id="r"
    )
    assert ad.calls == [("kb_qa", "X 不吸")] and ad.max_in_flight == 1
    assert set(out.results) == {"kb_qa"} and out.queries == ["X 不吸"]
    assert not any(t.get("event") for t in out.trace)  # 无 rerank 事件
    assert out.results["kb_qa"].hits[0].round == 1


async def test_rerank_applies_per_kb_and_falls_back_on_failure():
    table = {("kb_qa", "X 不吸"): ToolResult("ok", [_hit("a", 0.9), _hit("b", 0.5)])}
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
    assert [h.evidence_id for h in out.results["kb_qa"].hits] == ["b", "a"]
    assert rr.calls == [("X 不吸", ["a", "b"])]  # 单命中 / 无命中的库不调
    tr = [t for t in out.trace if t.get("event") == "rerank"]
    assert (
        tr[0]["kb"] == "kb_qa"
        and tr[0]["status"] == "ok"
        and tr[0]["order_after"] == ["b", "a"]
    )
    # 失败回退原序
    table2 = {("kb_qa", "X 不吸"): ToolResult("ok", [_hit("a", 0.9), _hit("b", 0.5)])}
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
    assert [h.evidence_id for h in out2.results["kb_qa"].hits] == ["a", "b"]
    assert next(t for t in out2.trace if t.get("event") == "rerank")["status"] == "failed"
    # allow_rerank=False（第二轮 / 预算不足）不调
    rr3 = FakeReranker()
    table3 = {("kb_qa", "X 不吸"): ToolResult("ok", [_hit("a", 0.9), _hit("b", 0.5)])}
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
