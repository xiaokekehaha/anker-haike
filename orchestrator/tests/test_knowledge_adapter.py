"""票 27：scope → 允许集合、空集合不发请求、后过滤、四态、截断、反证标记；末尾一条本机 WeKnora 集成测试（可达时）。"""

from __future__ import annotations

import json

import pytest

from app.knowledge import WeKnoraClient
from app.knowledge.adapter import (
    HINTS,
    KnowledgeScope,
    WeKnoraKnowledgeAdapter,
    allowed_entries,
    parse_custom_metadata,
)
from app.knowledge.ingest import Ingestor
from app.settings import REPO_ROOT, settings
from tests.fake_weknora import FakeWeKnora

DATA = REPO_ROOT / "data" / "knowledge"
X10 = KnowledgeScope("confirmed_sku", "robot_vacuum", "EUFY-X10-PRO-OMNI")
CAT_ONLY = KnowledgeScope("category_only", "robot_vacuum")
UNKNOWN = KnowledgeScope("unknown", "robot_vacuum")


@pytest.fixture
async def adapter():
    server = FakeWeKnora(
        models=[
            {
                "id": "emb",
                "name": "e",
                "type": "Embedding",
                "is_default": True,
                "parameters": {"embedding_parameters": {"dimension": 1024}},
            }
        ]
    )
    async with WeKnoraClient("http://weknora.test", "sk-test", transport=server.transport()) as c:
        report = await Ingestor(c, embedding_model_id="emb").ingest_all(DATA)
        ad = WeKnoraKnowledgeAdapter(c, report.kb_ids)
        counts = await ad.refresh_index()
        assert counts == {"kb_manual": 3, "kb_tickets": 200}
        yield ad, server


def test_parse_custom_metadata_dict_and_yaml():
    assert parse_custom_metadata({"scope": "sku"}) == {"scope": "sku"}
    assert parse_custom_metadata("scope: sku\nsku_list: A,B\nresult: solved") == {
        "scope": "sku",
        "sku_list": "A,B",
        "result": "solved",
    }
    assert parse_custom_metadata("") == {} and parse_custom_metadata("just text") == {}


async def test_allowed_sets_follow_product_state(adapter):
    ad, _ = adapter
    manual = ad.index["kb_manual"]
    assert {e.doc_id for e in allowed_entries(manual, CAT_ONLY)} == {"troubleshooting_rv"}
    assert {e.doc_id for e in allowed_entries(manual, X10)} == {
        "troubleshooting_rv",
        "manual_rv_v1",
    }
    assert allowed_entries(manual, UNKNOWN) == []
    tickets_x10 = allowed_entries(ad.index["kb_tickets"], X10)
    assert tickets_x10 and all(e.sku_list == ("EUFY-X10-PRO-OMNI",) for e in tickets_x10)
    assert allowed_entries(ad.index["kb_tickets"], CAT_ONLY) == []  # 工单都是 scope=sku
    assert allowed_entries(manual, KnowledgeScope("category_only", "breast_pump")) == []


async def test_category_only_results_exclude_sku_scope(adapter):
    ad, server = adapter
    res = await ad.hybrid_search("kb_manual", "滚刷", 5, CAT_ONLY)
    assert res.status == "ok" and res.hits
    assert {h.doc_id for h in res.hits} == {"troubleshooting_rv"}
    assert all(h.source == "kb_manual" and h.evidence_id == h.chunk_id for h in res.hits)
    # 请求确实带了 knowledge_ids（只含 generic 条目）
    assert ("POST", f"/knowledge-bases/{ad.kb_ids['kb_manual']}/hybrid-search") in server.calls


async def test_confirmed_sku_includes_own_manual_and_generic(adapter):
    ad, _ = adapter
    res = await ad.hybrid_search("kb_manual", "滚刷", 5, X10)
    assert res.status == "ok" and {h.doc_id for h in res.hits} == {
        "troubleshooting_rv",
        "manual_rv_v1",
    }
    assert res.hits[0].as_evidence_item()["status"] == "ok"


async def test_empty_allowed_set_sends_no_request(adapter):
    ad, server = adapter
    before = len(server.calls)
    for scope in (UNKNOWN, KnowledgeScope("category_only", "breast_pump")):
        res = await ad.hybrid_search("kb_manual", "滚刷", 5, scope)
        assert (
            res.status == "no_match"
            and res.hint == HINTS["no_match_empty_scope"]
            and res.allowed_count == 0
        )
    res = await ad.hybrid_search("kb_tickets", "滚刷", 5, CAT_ONLY)  # 工单无 generic 条目
    assert res.status == "no_match"
    assert len(server.calls) == before


async def test_no_hit_is_no_match_with_hint(adapter):
    ad, _ = adapter
    res = await ad.hybrid_search("kb_manual", "量子纠缠", 5, X10)
    assert res.status == "no_match" and res.hint == HINTS["no_match"] and res.allowed_count == 2
    assert res.for_model() == {"status": "no_match", "hint": HINTS["no_match"]}


async def test_weknora_down_is_unavailable_with_hint(adapter):
    ad, server = adapter
    server.down = True
    res = await ad.hybrid_search("kb_manual", "滚刷", 5, X10)
    assert res.status == "unavailable" and res.hint == HINTS["unavailable"]
    assert "ConnectError" in (res.detail or "") and res.for_model()["status"] == "unavailable"


async def test_counter_evidence_for_unsolved_tickets(adapter):
    ad, _ = adapter
    res = await ad.hybrid_search(
        "kb_tickets", "边刷", 50, KnowledgeScope("confirmed_sku", "robot_vacuum", "EUFY-G40-HYBRID")
    )
    assert res.status == "ok"
    flags = {h.doc_id: h.counter_evidence for h in res.hits}
    assert "T0024" in flags and flags["T0024"] is True  # unsolved 工单
    assert any(v is False for v in flags.values())
    assert [h.counter_evidence for h in res.hits] == sorted(
        h.counter_evidence for h in res.hits
    )  # 反证排后
    assert res.for_model()["hits"][-1].get("counter_evidence") is True
    # P0-4：case_outcome 与 counter_evidence 一致，并通过 as_internal_item 传给 synthesize
    outcomes = {h.doc_id: h.case_outcome for h in res.hits}
    assert outcomes["T0024"] == "unsolved"
    assert all((o == "unsolved") == flags[d] for d, o in outcomes.items())
    assert res.hits[-1].as_internal_item()["case_outcome"] == "unsolved"
    assert "case_outcome" not in res.hits[-1].as_evidence_item()


async def test_truncation_marks_result(adapter):
    ad, _ = adapter
    ad.max_chars = 300
    res = await ad.hybrid_search("kb_manual", "滚刷", 5, X10)
    assert res.truncated is True and sum(len(h.snippet) for h in res.hits) <= 300 and res.hits
    assert res.for_model()["truncated"] is True


async def test_post_filter_drops_hits_outside_allowed(adapter):
    """即使服务端忽略 knowledge_ids（knowledge-search 的行为），适配器也按允许集合后过滤。"""
    ad, _server = adapter
    orig = ad.client.hybrid_search

    async def leaky(kb_id, query, **kw):
        kw.pop("knowledge_ids", None)
        return await orig(kb_id, query, **kw)

    ad.client.hybrid_search = leaky  # type: ignore[method-assign]
    res = await ad.hybrid_search("kb_manual", "滚刷", 5, CAT_ONLY)
    assert {h.doc_id for h in res.hits} == {"troubleshooting_rv"}


# ---- 本机 WeKnora 集成（有 key 且可达时）----


async def test_live_category_only_excludes_sku_docs():
    manifest = DATA / "manifest.json"
    if not settings.weknora_api_key or not manifest.is_file():
        pytest.skip("no WEKNORA_API_KEY / manifest")
    kb_ids = json.loads(manifest.read_text(encoding="utf-8"))["knowledge_bases"]
    try:
        async with WeKnoraClient(
            settings.weknora_base_url, settings.weknora_api_key, timeout_s=5
        ) as c:
            ad = WeKnoraKnowledgeAdapter(c, kb_ids)
            counts = await ad.refresh_index()
            res = await ad.hybrid_search("kb_manual", "滚刷缠绕毛发怎么清理", 5, CAT_ONLY)
            res_sku = await ad.hybrid_search("kb_manual", "滚刷缠绕毛发怎么清理", 5, X10)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"weknora not reachable: {type(exc).__name__}")
    assert counts["kb_manual"] == 3 and counts["kb_tickets"] == 200
    assert res.status in ("ok", "no_match")
    if res.status == "ok":
        assert {h.doc_id for h in res.hits} == {"troubleshooting_rv"}
    assert res_sku.status == "ok" and {h.doc_id for h in res_sku.hits} <= {
        "troubleshooting_rv",
        "manual_rv_v1",
    }
