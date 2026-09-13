"""阶段 4 父块扩展：重叠拼接、同父子块还原、无父尾块用邻块、上限与非手册跳过、synthesize 用 full_text、图内接线。"""

from __future__ import annotations

import json

from app.diagnose.synthesize import _evidence_text
from app.knowledge.adapter import Hit, ToolResult, WeKnoraKnowledgeAdapter, merge_overlapping
from tests.test_diagnose import NO_MATCH, ScriptedAdapter, _rcfg, hit, make_router, run_text


def test_merge_overlapping_removes_chunk_overlap_and_handles_no_overlap():
    a = "翻转主机，按下滚刷盖两侧卡扣取出滚刷，用附带清洁刀具割断缠绕的毛发后装回。"
    b = "割断缠绕的毛发后装回。建议每周检查一次。"
    assert merge_overlapping([a, b]) == a + "建议每周检查一次。"
    assert merge_overlapping(["abc", "xyz"]) == "abcxyz"
    assert merge_overlapping([]) == "" and merge_overlapping(["only"]) == "only"
    # 重叠超过 max_overlap 不再识别（防止误吞正文）
    assert merge_overlapping(["x" * 200, "x" * 200], max_overlap=50) == "x" * 350


def _chunks(kid: str):
    return [
        {
            "id": "k0",
            "knowledge_id": kid,
            "parent_chunk_id": "P1",
            "chunk_index": 0,
            "content": "第一章 维护。滚刷清理步骤一二三，",
        },
        {
            "id": "k1",
            "knowledge_id": kid,
            "parent_chunk_id": "P1",
            "chunk_index": 1,
            "content": "步骤一二三，然后装回并试运行。滤网",
        },
        {
            "id": "k2",
            "knowledge_id": kid,
            "parent_chunk_id": "P1",
            "chunk_index": 2,
            "content": "滤网两周清洁一次。",
        },
        {
            "id": "k3",
            "knowledge_id": kid,
            "parent_chunk_id": None,
            "chunk_index": 3,
            "pre_chunk_id": "k2",
            "next_chunk_id": None,
            "content": "| 现象 | 含义 |",
        },
    ]


def _adapter_with_chunks() -> WeKnoraKnowledgeAdapter:
    ad = WeKnoraKnowledgeAdapter(client=None, kb_ids={"kb_manual": "m", "kb_tickets": "t"})  # type: ignore[arg-type]
    ad.chunks = {"K": _chunks("K")}
    ad.chunks_loaded_at = 1.0
    return ad


def _mhit(chunk: str, snippet: str, *, kid: str = "K", source: str = "kb_manual") -> Hit:
    return Hit(chunk, kid, chunk, "manual_rv_v1", "v", source, snippet, 0.5)


def test_expand_parents_rebuilds_parent_from_siblings_in_order():
    ad = _adapter_with_chunks()
    h = _mhit("k1", "步骤一二三，然后装回并试运行。滤网")
    done = ad.expand_parents([h], max_items=3, max_chars=800)
    assert done == ["k1"] and h.expanded_from == "k1" and h.context_chunk_ids == ("k0", "k1", "k2")
    assert h.full_text == "第一章 维护。滚刷清理步骤一二三，然后装回并试运行。滤网两周清洁一次。"
    assert h.snippet == "步骤一二三，然后装回并试运行。滤网"  # SSE 用的子块不变
    item = h.as_internal_item()
    assert item["full_text"] == h.full_text and item["expanded_from"] == "k1"
    assert "full_text" not in h.as_evidence_item()


def test_expand_parents_orphan_uses_neighbors_and_respects_limits():
    ad = _adapter_with_chunks()
    orphan = _mhit("k3", "| 现象 |")
    ad.expand_parents([orphan], max_items=3, max_chars=800)
    assert orphan.full_text == "滤网两周清洁一次。| 现象 | 含义 |" and orphan.context_chunk_ids == (
        "k2",
        "k3",
    )
    # max_chars 截断；max_items 上限；非手册 / 未缓存 / 未知块跳过；已扩展不重复
    h1, h2 = _mhit("k0", "第一章"), _mhit("k2", "滤网两周")
    ticket = _mhit("t1", "工单", kid="T", source="kb_tickets")
    unknown = _mhit("zz", "未知", kid="K")
    other = _mhit("k0", "第一章", kid="NOPE")
    done = ad.expand_parents([ticket, unknown, other, h1, h2], max_items=1, max_chars=20)
    assert done == ["k0"] and len(h1.full_text) == 20 and h2.full_text is None
    assert ticket.full_text is None and unknown.full_text is None and other.full_text is None
    assert ad.expand_parents([h1], max_items=3, max_chars=800) == []  # 已扩展


def test_expand_parents_dedupes_same_parent_group():
    ad = _adapter_with_chunks()
    a, b, c = _mhit("k0", "第一章"), _mhit("k1", "步骤"), _mhit("k2", "滤网")
    done = ad.expand_parents([a, b, c], max_items=3, max_chars=800)
    assert done == ["k0"] and a.full_text and b.full_text is None and c.full_text is None
    assert b.expanded_from == "k0" and c.expanded_from == "k0"  # 指向已带正文的那条


def test_expand_skips_when_parent_not_longer_than_snippet():
    ad = _adapter_with_chunks()
    ad.chunks["K"] = [
        {"id": "s", "knowledge_id": "K", "parent_chunk_id": "P", "chunk_index": 0, "content": "短"}
    ]
    h = _mhit("s", "短")
    assert ad.expand_parents([h], max_items=3, max_chars=800) == [] and h.full_text is None


def test_synthesize_prefers_full_text_with_800_cap():
    assert _evidence_text({"snippet": "x" * 500}) == "x" * 300
    assert _evidence_text({"snippet": "x", "full_text": "y" * 1000}) == "y" * 800


class ExpandingAdapter(ScriptedAdapter):
    """模拟真实适配器的父块扩展接口（图内经 getattr 探测）。"""

    chunks_loaded_at = None

    def __init__(self, plan):
        super().__init__(plan)
        self.refreshed = 0

    async def refresh_chunks(self):
        self.refreshed += 1
        self.chunks_loaded_at = 1.0
        return 3

    def expand_parents(self, hits, *, max_items, max_chars):
        done = []
        for h in hits:
            if h.source == "kb_manual" and len(done) < max_items:
                h.full_text = ("父块正文：" + h.snippet + "。后续步骤……")[:max_chars]
                h.expanded_from = h.chunk_id
                done.append(h.evidence_id)
        return done


async def test_graph_expands_parents_and_feeds_full_text_to_synthesize(mem_runtime, tmp_path):
    intake = json.dumps(
        {
            "emotion_level": "calm",
            "product_hints": ["X9 Pro"],
            "symptoms": ["不吸"],
            "wants_human": False,
        },
        ensure_ascii=False,
    )
    synth = json.dumps(
        {
            "hypotheses": [
                {"plan_id": "rv_suction_hair_wrap", "confidence": 0.8, "evidence_ids": ["c12"]}
            ]
        }
    )
    router, fakes = make_router(tmp_path, fast=[intake], main=[synth, ["清理滚刷。"]])
    ok = ToolResult("ok", [hit("c12", "manual_rv_v1", "翻转主机取出滚刷")], allowed_count=2)
    adapter = ExpandingAdapter({"kb_manual": [ok], "kb_tickets": [NO_MATCH()]})
    cfg = _rcfg(enabled=False)
    cfg.parent_expand = cfg.parent_expand.model_copy(update={"enabled": True, "max_items": 2})
    events, values = await run_text(router, adapter, "eufy X9 Pro 不吸了", rcfg=cfg)
    assert adapter.refreshed == 1
    tr = next(t for t in values["retrieval_trace"] if t.get("event") == "parent_expanded")
    assert tr["ids"] == ["c12"]
    scall = next(c for c in fakes["main"].calls if c["metadata"]["task"] == "diagnose.synthesize")
    human = next(m for m in scall["messages"] if getattr(m, "type", "") == "human").content
    assert "父块正文：翻转主机取出滚刷。后续步骤" in human
    ev = next(e for e in events if e["type"] == "evidence")
    assert ev["items"][0]["snippet"] == "翻转主机取出滚刷" and "full_text" not in ev["items"][0]
    assert values["evidence"]["c12"].get("full_text") is None  # 快照里的 evidence 仍是契约形状


async def test_graph_without_expand_support_is_unchanged(mem_runtime, tmp_path):
    intake = json.dumps(
        {
            "emotion_level": "calm",
            "product_hints": ["X9 Pro"],
            "symptoms": ["不吸"],
            "wants_human": False,
        },
        ensure_ascii=False,
    )
    router, _ = make_router(tmp_path, fast=[intake], main=[["清理滚刷。"]])
    ok = ToolResult("ok", [hit("c12", "manual_rv_v1", "翻转主机取出滚刷")], allowed_count=2)
    cfg = _rcfg(enabled=False)
    cfg.parent_expand = cfg.parent_expand.model_copy(update={"enabled": True})
    _, values = await run_text(
        router,
        ScriptedAdapter({"kb_manual": [ok], "kb_tickets": [NO_MATCH()]}),
        "eufy X9 Pro 不吸了",
        rcfg=cfg,
    )
    assert not any(t.get("event") == "parent_expanded" for t in values["retrieval_trace"])
