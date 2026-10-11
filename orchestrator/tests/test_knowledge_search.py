"""search_round：单库 kb_qa 一次请求、rerank 失败回退、跨库合并按名次。"""

from __future__ import annotations

import asyncio

from app.diagnose.config import RetrievalConfig, get_retrieval_config
from app.knowledge.adapter import HINTS, Hit, KnowledgeScope, ToolResult
from app.knowledge.rerank import RerankOutcome
from app.knowledge.search import fuse_queries, interleave_kbs, search_round

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


# ---- 原文 + 英文现象描述双路（intake 的 search_query_en，2026-10-11） ----


async def test_english_description_adds_a_second_query_and_fuses_by_rank():
    """T57 / T59：原文没召回的连接条目由英文描述补进来；两路都命中的条目排前。"""
    ad = RecordingAdapter({
        ("kb_qa", "Mijn robot is losgekoppeld"): ToolResult("ok", [_hit("a", 0.9), _hit("b", 0.8), _hit("c", 0.7)]),
        ("kb_qa", "robot shows offline in the app"): ToolResult("ok", [_hit("wifi", 0.9), _hit("b", 0.8)]),
    })
    out = await search_round(ad, "Mijn robot is losgekoppeld", SCOPE, 5, cfg=_cfg(), round_no=1, session_id="s",
                             run_id="r", english="robot shows offline in the app")
    assert ad.calls == [("kb_qa", "Mijn robot is losgekoppeld"), ("kb_qa", "robot shows offline in the app")]
    ids = [h.evidence_id for h in out.results["kb_qa"].hits]
    assert ids[0] == "b" and "wifi" in ids and set(ids) == {"a", "b", "c", "wifi"}
    assert out.queries == ["Mijn robot is losgekoppeld", "robot shows offline in the app"]
    # trace 里两路各一条，能分别看到各自的命中（评审 §7：区分原文与英文两路）
    by_query = {t["query"]: t["hit_ids"] for t in out.trace if t.get("kb") == "kb_qa"}
    assert by_query == {"Mijn robot is losgekoppeld": ["a", "b", "c"], "robot shows offline in the app": ["wifi", "b"]}
    b = next(h for h in out.results["kb_qa"].hits if h.evidence_id == "b")
    assert b.source_queries == ("Mijn robot is losgekoppeld", "robot shows offline in the app")


def test_original_query_outranks_the_english_paraphrase():
    """T18：英文转述丢了原文推送里的信号，等权合并会把原文第 1 的金标挤出前 5。原文为主：原文第 1 仍在英文第 1 之前。"""
    primary = ToolResult("ok", [_hit("gold", 0.9), _hit("p2", 0.8), _hit("p3", 0.7)])
    extra = ToolResult("ok", [_hit("e1", 0.9), _hit("e2", 0.8), _hit("e3", 0.7)])
    ids = [h.evidence_id for h in fuse_queries(primary, extra, 5).hits]
    assert ids[0] == "gold" and len(ids) == 5


async def test_same_or_missing_english_does_not_add_a_query():
    for english in (None, "", "robot offline", "ROBOT OFFLINE"):
        ad = RecordingAdapter({("kb_qa", "robot offline"): ToolResult("ok", [_hit("a", 0.9)])})
        out = await search_round(ad, "robot offline", SCOPE, 5, cfg=_cfg(), round_no=1, session_id="s", run_id="r", english=english)
        assert ad.calls == [("kb_qa", "robot offline")] and out.queries == ["robot offline"]


def test_one_empty_side_keeps_the_other():
    hits = ToolResult("ok", [_hit("a", 0.9)])
    empty = ToolResult("no_match", hint=HINTS["no_match"])
    assert fuse_queries(hits, empty, 5) is hits
    assert fuse_queries(empty, hits, 5) is hits
