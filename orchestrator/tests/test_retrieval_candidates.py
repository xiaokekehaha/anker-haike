"""候选正文、重排与最终上下文的回归：正确片段不能在重排前因条数/摘要预算丢失。"""

from app.diagnose.config import RerankConfig, RetrievalConfig
from app.knowledge.adapter import Hit, KnowledgeScope, WeKnoraKnowledgeAdapter, context_window
from app.knowledge.context import pack_hits, render_evidence, select_hits
from app.knowledge.rerank import DashScopeReranker
from app.knowledge.search import search_round
from app.knowledge.weknora_client import WeKnoraClient
from tests.fake_weknora import FakeWeKnora


class ContentReranker(DashScopeReranker):
    """只替代远端评分I/O，真实rerank与候选编排照常执行。"""

    async def scores(self, query: str, documents: list[str]) -> list[float]:
        self.documents = documents
        return [1.0 if "唯一支持缠绕处置" in document else 0.1 for document in documents]


async def test_eighth_candidate_and_text_beyond_snippet_reach_reranker():
    server = FakeWeKnora()
    server.kbs["manual"] = {"id": "manual"}
    server.kbs["tickets"] = {"id": "tickets"}
    for index in range(12):
        content = "滚刷维护说明。" + "前言。" * 200
        content += "唯一支持缠绕处置" if index == 7 else "无关章节"
        kid = f"{index:08d}-manual"
        server.knowledge[kid] = {
            "id": kid, "knowledge_base_id": "manual", "title": f"手册 {index}",
            "content": content, "parse_status": "completed",
            "custom_metadata": {
                "doc_id": f"manual-{index:02}", "doc_version": "v1", "scope": "category_generic",
                "category": "robot_vacuum",
            },
        }
    cfg = RetrievalConfig(rerank=RerankConfig(enabled=True))
    reranker = ContentReranker(api_key="test")
    async with WeKnoraClient("http://weknora.test", "sk-test", transport=server.transport()) as client:
        adapter = WeKnoraKnowledgeAdapter(client, {"kb_manual": "manual", "kb_tickets": "tickets"})
        await adapter.refresh_index()
        result = await search_round(
            adapter, "滚刷", KnowledgeScope("category_only", "robot_vacuum"),
            cfg.retrieval.candidate_k, cfg=cfg, round_no=1, session_id="s", run_id="r",
            reranker=reranker,
        )
    hits = result.results["kb_manual"].hits
    assert len(hits) == 12 and hits[0].doc_id == "manual-07"
    assert "手册 7" in reranker.documents[7] and "唯一支持缠绕处置" in reranker.documents[7]
    assert "唯一支持缠绕处置" not in hits[0].snippet
    packed = pack_hits(hits, max_items=5, max_chars=5000, item_chars=800)
    assert "唯一支持缠绕处置" in render_evidence(packed.hits[0].as_internal_item())


def test_context_budget_preserves_rounds_sources_and_counter_evidence():
    first = [
        Hit(f"old-{i}", "m", f"c{i}", "manual", "v1", "kb_manual", "摘要", 0.9, content="长文。" * 300)
        for i in range(15)
    ]
    fresh = Hit("new", "m", "new", "manual", "v1", "kb_manual", "新增有效证据", 0.01, round=2)
    counter = Hit("counter", "t", "counter", "ticket", "v1", "kb_tickets", "工单未解决", 0.99,
                  counter_evidence=True, case_outcome="unsolved")
    local = Hit("card", "f", "card", "card", "v1", "fault_card", "故障卡", 0.6)
    selection = pack_hits([*first, fresh, counter, local], max_items=6, max_chars=1000, item_chars=800)
    ids = [hit.evidence_id for hit in selection.hits]
    assert len(ids) == 6 and {"new", "old-0", "counter", "card"} <= set(ids)
    text = "\n".join(render_evidence(hit.as_internal_item()) for hit in selection.hits)
    assert len(text) <= selection.chars <= 1000 and "未解决工单" in text
    assert selection.excluded and selection.shortened_ids
    assert fresh.context_text is None  # 打包不能修改首轮/二轮候选原文


def test_second_round_gets_a_slot_without_displacing_the_first_hit():
    first = [Hit(f"r1-{i}", "m", f"c{i}", "manual", "v1",
                 "kb_manual" if i % 2 == 0 else "kb_tickets", "命中段落", 0.9 - i / 100)
             for i in range(10)]
    fresh = [Hit("r2", "m", "r2", "manual", "v1", "kb_manual", "补查新增", 0.01, round=2)]
    ids = [hit.evidence_id for hit in select_hits([*first, *fresh], 6)]
    # 补查 query 掺了改写或图片观察，不能假定它比首轮首条更相关；但必须拿到名额
    assert ids[0] == "r1-0" and "r2" in ids


def test_empty_body_cannot_displace_usable_evidence():
    blank = Hit("blank", "m", "blank", "manual", "v1", "kb_manual", " ", 0.9)
    useful = Hit("useful", "m", "useful", "manual", "v1", "kb_manual", "命中段落", 0.1)
    selection = pack_hits([blank, useful], max_items=1, max_chars=200, item_chars=100)
    assert [hit.evidence_id for hit in selection.hits] == ["useful"]
    assert selection.excluded == {"blank": "empty_content"}


def test_sentence_boundary_must_not_trim_the_matched_clause():
    anchor = "前面的说明。真正命中的处置"
    text = "背景。" * 30 + anchor + "后文" * 30
    window = context_window(text, anchor, 20)
    assert anchor in window
