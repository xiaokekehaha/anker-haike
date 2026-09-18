"""票 27：scope → 允许集合、空集合不发请求、后过滤、四态、截断、反证标记；真实集成测试需显式开启。"""

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
)
from app.knowledge.ingest import Ingestor
from app.settings import REPO_ROOT, settings
from tests.fake_weknora import FakeWeKnora

DATA = REPO_ROOT / "data" / "knowledge"
MANUAL_COUNT = len(list((DATA / "kb_manual").glob("*.md")))
X10 = KnowledgeScope("confirmed_sku", "robot_vacuum", "EUFY-X10-PRO-OMNI")
# manual_rv_v1 已降为品类级（通用维护流程），机型级手册只剩 v2，范围控制改由它来体现
L60 = KnowledgeScope("confirmed_sku", "robot_vacuum", "EUFY-L60-HYBRID")
CAT_ONLY = KnowledgeScope("category_only", "robot_vacuum")
# 该型号的官方资料摘要（data/knowledge/sources/anker_official.yaml 里 sku_list 含 X10 的那些）
X10_OFFICIAL = {
    "official_x10_suction", "official_x10_charging", "official_x10_wifi", "official_x10_voice",
    "official_x10_station_leak", "official_x10_mop_water", "official_x10_dock_return",
    "official_x10_map_lost", "official_x10_loud_noise",
}
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
        assert counts == {"kb_manual": MANUAL_COUNT, "kb_tickets": 380}
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
    generic = {"troubleshooting_rv", "manual_rv_v1"}
    assert {e.doc_id for e in allowed_entries(manual, CAT_ONLY)} == generic
    # 官方资料必须确认到 X10 型号后才可见；其他机型的官方资料仍被隔离。
    assert {e.doc_id for e in allowed_entries(manual, X10)} == generic | X10_OFFICIAL
    # 机型专属手册仍然只对自己的 sku 可见
    assert {e.doc_id for e in allowed_entries(manual, L60)} == generic | {"manual_rv_v2"}
    assert allowed_entries(manual, UNKNOWN) == []
    tickets_x10 = allowed_entries(ad.index["kb_tickets"], X10)
    assert tickets_x10 and all(e.sku_list == ("EUFY-X10-PRO-OMNI",) for e in tickets_x10)
    assert allowed_entries(ad.index["kb_tickets"], CAT_ONLY) == []  # 工单都是 scope=sku
    # 目录级品类（拓展坞）没有任何资料；吸奶器等深度品类自 2026-09-17 起有自己的手册
    assert allowed_entries(manual, KnowledgeScope("category_only", "hub")) == []
    assert {e.doc_id for e in allowed_entries(manual, KnowledgeScope("category_only", "breast_pump"))} == {"manual_bp"}


async def test_category_only_results_exclude_sku_scope(adapter):
    ad, server = adapter
    res = await ad.hybrid_search("kb_manual", "滚刷", 5, CAT_ONLY)
    assert res.status == "ok" and res.hits
    assert {h.doc_id for h in res.hits} <= {"troubleshooting_rv", "manual_rv_v1"}
    assert "manual_rv_v2" not in {h.doc_id for h in res.hits}
    assert all(h.source == "kb_manual" and h.evidence_id == h.chunk_id for h in res.hits)
    # 请求确实带了 knowledge_ids（只含 generic 条目）
    assert ("POST", f"/knowledge-bases/{ad.kb_ids['kb_manual']}/hybrid-search") in server.calls


async def test_confirmed_sku_includes_own_manual_and_generic(adapter):
    ad, _ = adapter
    res = await ad.hybrid_search("kb_manual", "滚刷", 5, L60)
    assert res.status == "ok" and {h.doc_id for h in res.hits} == {
        "troubleshooting_rv",
        "manual_rv_v1",
        "manual_rv_v2",
    }
    assert res.hits[0].as_evidence_item()["status"] == "ok"


async def test_empty_allowed_set_sends_no_request(adapter):
    ad, server = adapter
    before = len(server.calls)
    for scope in (UNKNOWN, KnowledgeScope("category_only", "hub")):
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
    assert res.status == "no_match" and res.hint == HINTS["no_match"]
    assert res.allowed_count == len(X10_OFFICIAL) + 2  # 两条品类通用手册
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


async def test_candidate_content_is_independent_of_display_snippets(adapter):
    ad, _ = adapter
    ad.snippet_chars = 30
    res = await ad.hybrid_search("kb_manual", "滚刷", 5, X10)
    assert len(res.hits) == res.total_hits == res.raw_hits and len(res.hits) > 1
    assert all(len(h.snippet) <= 30 for h in res.hits)
    assert any(len(h.content) > 400 for h in res.hits)
    assert all("content" not in h.as_evidence_item() for h in res.hits)


async def test_post_filter_drops_hits_outside_allowed(adapter):
    """即使服务端忽略 knowledge_ids（knowledge-search 的行为），适配器也按允许集合后过滤。"""
    ad, _server = adapter
    orig = ad.client.hybrid_search

    async def leaky(kb_id, query, **kw):
        kw.pop("knowledge_ids", None)
        return await orig(kb_id, query, **kw)

    ad.client.hybrid_search = leaky  # type: ignore[method-assign]
    res = await ad.hybrid_search("kb_manual", "滚刷", 5, CAT_ONLY)
    assert {h.doc_id for h in res.hits} <= {"troubleshooting_rv", "manual_rv_v1"}
    assert "manual_rv_v2" not in {h.doc_id for h in res.hits}


# ---- 本机 WeKnora 集成（显式开启且有 key 时；普通单测不连真实服务）----


async def test_live_category_only_excludes_sku_docs():
    if os.environ.get("HAIKE_KNOWLEDGE", "off").lower() in ("off", "0", "false"):
        pytest.skip("set HAIKE_KNOWLEDGE=on explicitly for live integration")
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
            res_sku = await ad.hybrid_search("kb_manual", "滚刷缠绕毛发怎么清理", 5, L60)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"weknora not reachable: {type(exc).__name__}")
    assert counts["kb_manual"] == MANUAL_COUNT and counts["kb_tickets"] == 380
    # 适配器把超时 / 不可达转成 status='unavailable' 返回值而非异常，上面的 except 接不住：
    # 冷启动时首次检索要等 WeKnora 加载 embedding 模型，常超过 timeout_s=5（实测 5008 ms）。
    if "unavailable" in (res.status, res_sku.status):
        pytest.skip(f"weknora unavailable: {res.detail or res_sku.detail}")
    assert res.status in ("ok", "no_match")
    if res.status == "ok":
        # 通用维护手册降级后品类会话也能拿到；机型专属手册仍被挡在外面
        assert {h.doc_id for h in res.hits} <= {"troubleshooting_rv", "manual_rv_v1"}
        assert "manual_rv_v2" not in {h.doc_id for h in res.hits}
    assert res_sku.status == "ok" and {h.doc_id for h in res_sku.hits} <= {
        "troubleshooting_rv",
        "manual_rv_v1",
        "manual_rv_v2",
    }
