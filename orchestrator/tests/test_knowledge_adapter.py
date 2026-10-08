"""票 27：scope → 允许集合、空集合不发请求、后过滤、四态、截断；真实集成测试需显式开启。

2026-10-08 起只有一个知识库 kb_qa：一条官方 Q&A 一个 knowledge，custom_metadata scope=sku、
sku_list=PN 逗号串、category、doc_id=qa id（app.knowledge.official_qa）。
"""

from __future__ import annotations

import json
import os

import pytest

from app.knowledge import WeKnoraClient
from app.knowledge.adapter import (
    HINTS,
    KnowledgeScope,
    WeKnoraKnowledgeAdapter,
    allowed_entries,
    parse_custom_metadata,
    sku_scoped_skus,
)
from app.knowledge.ingest import IngestReport
from app.knowledge.official_qa import ingest_qa
from app.official.qa_index import QAIndex
from app.settings import REPO_ROOT, settings
from tests.fake_weknora import FakeWeKnora

FULL = QAIndex.build()
# 每个品类 / 型号各取一条：rv-0147 同时适用 E28 / E25（T2352、T2353）
SAMPLE = ("rv-0004", "rv-0147", "rv-0063", "bp-0009", "bp-0169")
INDEX = QAIndex(guides={q: FULL.guides[q] for q in SAMPLE}, version=FULL.version)
VACUUMS = ("T2080", "T2351", "T2352", "T2353", "T2280", "T2292")
X10 = KnowledgeScope("confirmed_sku", "robot_vacuum", "T2351")
E28 = KnowledgeScope("confirmed_sku", "robot_vacuum", "T2352")
S1 = KnowledgeScope("confirmed_sku", "robot_vacuum", "T2080")
CAT_ONLY = KnowledgeScope("category_only", "robot_vacuum", category_skus=VACUUMS)
UNKNOWN = KnowledgeScope("unknown", "robot_vacuum")


@pytest.fixture
async def adapter():
    server = FakeWeKnora()
    async with WeKnoraClient("http://weknora.test", "sk-test", transport=server.transport()) as c:
        report = IngestReport()
        await ingest_qa(c, report, embedding_model_id=None, index=INDEX)
        ad = WeKnoraKnowledgeAdapter(c, report.kb_ids)
        counts = await ad.refresh_index()
        assert counts == {"kb_qa": len(SAMPLE)}
        yield ad, server


def test_parse_custom_metadata_dict_and_yaml():
    assert parse_custom_metadata({"scope": "sku"}) == {"scope": "sku"}
    assert parse_custom_metadata("scope: sku\nsku_list: A,B\nresult: solved") == {
        "scope": "sku",
        "sku_list": "A,B",
        "result": "solved",
    }
    assert parse_custom_metadata("") == {} and parse_custom_metadata("just text") == {}


async def test_index_is_one_entry_per_qa_with_pn_metadata(adapter):
    ad, _ = adapter
    by_doc = {e.doc_id: e for e in ad.index["kb_qa"]}
    assert set(by_doc) == set(SAMPLE)
    e = by_doc["rv-0147"]
    assert (e.kb, e.scope, e.sku_list, e.category, e.doc_version) == (
        "kb_qa", "sku", ("T2352", "T2353"), "robot_vacuum", FULL.version,
    )
    assert by_doc["bp-0009"].category == "breast_pump" and by_doc["bp-0169"].category == "security_cam"


async def test_allowed_sets_follow_product_state(adapter):
    ad, _ = adapter
    qa = ad.index["kb_qa"]
    assert {e.doc_id for e in allowed_entries(qa, X10)} == {"rv-0004"}
    assert {e.doc_id for e in allowed_entries(qa, E28)} == {"rv-0147"}
    assert {e.doc_id for e in allowed_entries(qa, S1)} == {"rv-0063"}
    # 品类未定到型号：没有一条扫地机 Q&A 覆盖全部六款，全是型号专属，category_only 看不到
    assert allowed_entries(qa, CAT_ONLY) == []
    assert allowed_entries(qa, UNKNOWN) == []
    # 型号对但品类不一致也不放行
    assert allowed_entries(qa, KnowledgeScope("confirmed_sku", "breast_pump", "T2352")) == []


async def test_confirmed_sku_search_is_scoped_to_its_pn(adapter):
    ad, server = adapter
    res = await ad.hybrid_search("kb_qa", "mop", 5, E28)
    assert res.status == "ok" and {h.doc_id for h in res.hits} == {"rv-0147"}
    assert all(h.source == "kb_qa" and h.evidence_id == h.chunk_id for h in res.hits)
    assert res.hits[0].as_evidence_item()["status"] == "ok"
    assert ("POST", f"/knowledge-bases/{ad.kb_ids['kb_qa']}/hybrid-search") in server.calls
    res = await ad.hybrid_search("kb_qa", "mop", 5, X10)
    assert res.status == "ok" and {h.doc_id for h in res.hits} == {"rv-0004"}


async def test_empty_allowed_set_sends_no_request(adapter):
    ad, server = adapter
    before = len(server.calls)
    for scope in (UNKNOWN, CAT_ONLY, KnowledgeScope("category_only", "hub")):
        res = await ad.hybrid_search("kb_qa", "mop", 5, scope)
        assert (
            res.status == "no_match"
            and res.hint == HINTS["no_match_empty_scope"]
            and res.allowed_count == 0
        )
    assert len(server.calls) == before


async def test_no_hit_is_no_match_with_hint(adapter):
    ad, _ = adapter
    res = await ad.hybrid_search("kb_qa", "quantum entanglement", 5, E28)
    assert res.status == "no_match" and res.hint == HINTS["no_match"]
    assert res.allowed_count == 1
    assert res.for_model() == {"status": "no_match", "hint": HINTS["no_match"]}


async def test_weknora_down_is_unavailable_with_hint(adapter):
    ad, server = adapter
    server.down = True
    res = await ad.hybrid_search("kb_qa", "mop", 5, E28)
    assert res.status == "unavailable" and res.hint == HINTS["unavailable"]
    assert "ConnectError" in (res.detail or "") and res.for_model()["status"] == "unavailable"


async def test_qa_hits_are_never_counter_evidence(adapter):
    """反证标记只属于工单；官方 Q&A 命中的 case_outcome 恒为 n/a。"""
    ad, _ = adapter
    res = await ad.hybrid_search("kb_qa", "mop", 5, X10)
    assert res.status == "ok"
    assert all(not h.counter_evidence and h.case_outcome == "n/a" for h in res.hits)
    assert "counter_evidence" not in res.for_model()["hits"][0]
    assert res.hits[0].as_internal_item()["case_outcome"] == "n/a"
    assert "case_outcome" not in res.hits[0].as_evidence_item()


async def test_candidate_content_is_independent_of_display_snippets(adapter):
    ad, _ = adapter
    ad.snippet_chars = 30
    res = await ad.hybrid_search("kb_qa", "mop", 5, X10)
    assert len(res.hits) == res.total_hits == res.raw_hits == 1
    assert all(len(h.snippet) <= 30 for h in res.hits)
    assert all(len(h.content) > 400 for h in res.hits)
    assert all("content" not in h.as_evidence_item() for h in res.hits)


async def test_post_filter_drops_hits_outside_allowed(adapter):
    """即使服务端忽略 knowledge_ids（knowledge-search 的行为），适配器也按允许集合后过滤。"""
    ad, _server = adapter
    orig = ad.client.hybrid_search

    async def leaky(kb_id, query, **kw):
        kw.pop("knowledge_ids", None)
        return await orig(kb_id, query, **kw)

    ad.client.hybrid_search = leaky  # type: ignore[method-assign]
    res = await ad.hybrid_search("kb_qa", "mop", 5, E28)
    assert res.raw_hits == 2  # rv-0004（X10）也含 mop，被后过滤掉
    assert {h.doc_id for h in res.hits} == {"rv-0147"}


async def test_sku_list_covering_whole_category_counts_as_generic(adapter):
    """spec 2026-09-19-0810 A 标签修正：sku_list 覆盖全品类的资料对每款型号一样，category_only 也放行，且不算分化。"""
    ad, _ = adapter
    qa = ad.index["kb_qa"]
    # 吸奶器目录里只有 T8D04：它的 Q&A 对 category_only 就是品类通用
    pumps = KnowledgeScope("category_only", "breast_pump", category_skus=("T8D04",))
    assert {e.doc_id for e in allowed_entries(qa, pumps)} == {"bp-0009"}
    assert allowed_entries(qa, KnowledgeScope("category_only", "breast_pump")) == []
    assert sku_scoped_skus(qa, "breast_pump", ("T8D04",)) == set()
    # 假设品类只有 E28 / E25 两款：rv-0147 覆盖全品类，不再算型号分化
    pair = ("T2352", "T2353")
    assert {e.doc_id for e in allowed_entries(qa, KnowledgeScope("category_only", "robot_vacuum", category_skus=pair))} == {"rv-0147"}
    assert sku_scoped_skus(qa, "robot_vacuum", pair) == {"T2351", "T2080"}
    # 真实目录六款扫地机：每条都只覆盖部分型号，全部算分化
    assert sku_scoped_skus(qa, "robot_vacuum", VACUUMS) == {"T2351", "T2352", "T2353", "T2080"}


# ---- 本机 WeKnora 集成（显式开启且有 key 时；普通单测不连真实服务）----


async def test_live_confirmed_sku_excludes_other_models():
    if os.environ.get("HAIKE_KNOWLEDGE", "off").lower() in ("off", "0", "false"):
        pytest.skip("set HAIKE_KNOWLEDGE=on explicitly for live integration")
    manifest = REPO_ROOT / "data" / "knowledge" / "manifest.json"
    if not settings.weknora_api_key or not manifest.is_file():
        pytest.skip("no WEKNORA_API_KEY / manifest")
    kb_ids = json.loads(manifest.read_text(encoding="utf-8"))["knowledge_bases"]
    try:
        async with WeKnoraClient(
            settings.weknora_base_url, settings.weknora_api_key, timeout_s=5
        ) as c:
            ad = WeKnoraKnowledgeAdapter(c, kb_ids)
            counts = await ad.refresh_index()
            res = await ad.hybrid_search("kb_qa", "rolling mop obstructed", 5, E28)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"weknora not reachable: {type(exc).__name__}")
    assert counts["kb_qa"] == sum(1 for g in FULL.guides.values() if g.visible)
    # 冷启动时首次检索要等 WeKnora 加载 embedding 模型，常超过 timeout_s=5：适配器返回 unavailable 而非异常。
    if res.status == "unavailable":
        pytest.skip(f"weknora unavailable: {res.detail}")
    assert res.status in ("ok", "no_match")
    allowed = {e.doc_id for e in allowed_entries(ad.index["kb_qa"], E28)}
    assert {h.doc_id for h in res.hits} <= allowed
