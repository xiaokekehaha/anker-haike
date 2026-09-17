"""票 26：知识库 bootstrap / 幂等导入 / 元数据 / 分块配置 / manifest / 快照回滚（内存版 WeKnora）。"""

from __future__ import annotations

import json
import shutil

import pytest

from app.knowledge import WeKnoraClient, WeKnoraError
from app.knowledge.ingest import (
    CHILD_CHUNK,
    EMBEDDING_DIM,
    KB_FAQ,
    KB_MANUAL,
    KB_TICKETS,
    PARENT_CHUNK,
    Ingestor,
    load_faq,
    load_manual_docs,
    load_tickets,
    verify_metadata,
    write_manifest,
)
from app.knowledge.snapshot import export_snapshot, import_snapshot
from app.settings import REPO_ROOT
from tests.fake_weknora import FakeWeKnora

DATA = REPO_ROOT / "data" / "knowledge"
DOCUMENT_COUNT = len(list((DATA / "kb_manual").glob("*.md"))) + 380
EMBED = {
    "id": "emb-1",
    "name": "text-embedding-v4",
    "type": "Embedding",
    "is_default": True,
    "parameters": {"embedding_parameters": {"dimension": 1024}},
}


@pytest.fixture
def server():
    return FakeWeKnora(models=[dict(EMBED)])


@pytest.fixture
async def client(server):
    async with WeKnoraClient("http://weknora.test", "sk-test", transport=server.transport()) as c:
        yield c


def test_seed_sources_are_complete():
    docs = load_manual_docs(DATA)
    assert {"manual_rv_v1", "manual_rv_v2", "troubleshooting_rv"} <= {d.doc_id for d in docs}
    assert all({"scope", "sku_list", "category", "doc_version"} <= set(d.metadata) for d in docs)
    assert any(d.metadata["scope"] == "category_generic" for d in docs)
    faq_docs = load_faq(DATA)  # 每品类一份 faq_*.yaml
    by_id = {meta["doc_id"]: (meta, entries) for meta, entries in faq_docs}
    assert len(by_id["faq_rv"][1]) >= 50 and by_id["faq_rv"][0]["scope"] == "category_generic"
    assert all(meta["category"] and meta["doc_version"] for meta, _ in faq_docs)
    rows = load_tickets(DATA)
    assert len(rows) >= 200 and {r["result"] for r in rows} == {"solved", "unsolved", "escalated"}


async def test_ingest_creates_kbs_with_parent_child_chunking(client, server):
    ing = Ingestor(client)
    ing.embedding_model_id = await ing.ensure_embedding_model(None)
    report = await ing.ingest_all(DATA)
    names = {kb["name"] for kb in server.kbs.values()}
    assert names == {KB_MANUAL, KB_FAQ, KB_TICKETS}
    for kb in server.kbs.values():
        cc = kb["chunking_config"]
        assert cc["enable_parent_child"] is True
        assert (
            cc["parent_chunk_size"] == PARENT_CHUNK == 800
            and cc["child_chunk_size"] == CHILD_CHUNK == 200
        )
        assert "graph" not in json.dumps(kb).lower()  # 图谱不开启
        assert kb["embedding_model_id"] == "emb-1"
    assert server.kbs[report.kb_ids["kb_faq"]]["type"] == "faq"
    assert report.created == DOCUMENT_COUNT and report.faq_entries >= 50 + 6 * 10
    assert report.embedding == {"id": "emb-1", "name": "text-embedding-v4", "dimension": 1024}


async def test_ingest_is_idempotent_and_metadata_queryable(client, server):
    ing = Ingestor(client, embedding_model_id="emb-1")
    first = await ing.ingest_all(DATA)
    n_calls = len(server.calls)
    ing2 = Ingestor(client, embedding_model_id="emb-1")
    second = await ing2.ingest_all(DATA)
    assert second.created == 0 and second.replaced == 0 and second.skipped == DOCUMENT_COUNT
    assert len(server.knowledge) == DOCUMENT_COUNT and len(server.kbs) == 3
    assert len(server.faq[first.kb_ids["kb_faq"]]) >= 50
    assert len(server.calls) > n_calls  # 确实重跑了
    items = await verify_metadata(client, first.kb_ids["kb_manual"])
    by_title = {i["title"]: i["custom_metadata"] for i in items}
    # 该手册内容是通用维护流程，已降为品类级，好让未确认型号的会话也检索得到（spec §9.6）
    m = by_title["扫地机器人通用用户手册（排障节选）"]
    assert m["scope"] == "category_generic" and m["doc_version"] == "2026-09-12.1"
    assert not m["sku_list"]
    # 机型专属手册仍是 sku 级，范围控制本身没有放开
    v2 = by_title["eufy L60 / G 系列 用户手册（排障节选）"]
    assert v2["scope"] == "sku" and "EUFY-L60-HYBRID" in v2["sku_list"]
    official = next(d for d in load_manual_docs(DATA) if d.doc_id == "official_x10_wifi")
    assert by_title[official.title] == official.metadata
    assert len(official.metadata) <= 20  # WeKnora v0.8.0 实际写入限制
    assert by_title[official.title]["source_url"].startswith("https://service.eufy.com/")
    assert by_title[official.title]["section_ids"] == "c1,c2"
    tickets = await verify_metadata(client, first.kb_ids["kb_tickets"])
    t1 = next(i for i in tickets if i["title"] == "T0001")["custom_metadata"]
    assert (
        t1["result"] in {"solved", "unsolved", "escalated"}
        and t1["scope"] == "sku"
        and t1["kb"] == "kb_tickets"
    )


async def test_version_bump_replaces_old_knowledge(client, server, tmp_path):
    ing = Ingestor(client, embedding_model_id="emb-1")
    await ing.ingest_all(DATA)
    root = tmp_path / "data"
    shutil.copytree(DATA, root)
    p = root / "kb_manual" / "manual_rv_v1.md"
    p.write_text(
        p.read_text(encoding="utf-8").replace(
            "doc_version: 2026-09-12.1", "doc_version: 2026-09-13.1"
        ),
        encoding="utf-8",
    )
    ing2 = Ingestor(client, embedding_model_id="emb-1")
    r = await ing2.ingest_all(root)
    assert r.replaced == 1 and r.skipped == DOCUMENT_COUNT - 1
    assert len(server.knowledge) == DOCUMENT_COUNT
    assert r.docs["manual_rv_v1"] == "2026-09-13.1"


async def test_manifest_records_kb_ver_bound_to_embedding(client, tmp_path):
    ing = Ingestor(client)
    ing.embedding_model_id = await ing.ensure_embedding_model(None)
    report = await ing.ingest_all(DATA)
    manifest = write_manifest(tmp_path / "manifest.json", report, source_root=DATA)
    latest = max(d.metadata["doc_version"] for d in load_manual_docs(DATA))
    assert manifest["kb_ver"] == f"{latest}+text-embedding-v4"
    assert manifest["embedding"]["dimension"] == EMBEDDING_DIM == 1024
    assert manifest["chunking"] == {
        "parent": 800,
        "child": 200,
        "parent_child": True,
        "graph": False,
    }
    assert manifest["errors"] == [] and set(manifest["knowledge_bases"]) == {
        "kb_manual",
        "kb_faq",
        "kb_tickets",
    }


async def test_new_version_with_renamed_title_replaces_same_source(client):
    ingestor = Ingestor(client, embedding_model_id="emb-1")
    kb = await ingestor.ensure_kb(KB_MANUAL, "document", "source updates")
    metadata = {"doc_id": "official_sample", "doc_version": "v1", "scope": "sku"}
    first_id = await ingestor.upsert_manual(kb["id"], "旧标题", "旧内容", metadata)
    await ingestor.upsert_manual(kb["id"], "新标题", "新内容", {**metadata, "doc_version": "v2"})
    items = await client.list_knowledge(kb["id"])
    assert len(items) == 1 and items[0]["id"] != first_id
    assert items[0]["title"] == "新标题"
    assert items[0]["custom_metadata"]["doc_version"] == "v2"


async def test_refetch_updates_provenance_without_reembedding(client):
    ingestor = Ingestor(client, embedding_model_id="emb-1")
    kb = await ingestor.ensure_kb(KB_MANUAL, "document", "source updates")
    metadata = {"doc_id": "official_sample", "doc_version": "v1", "scope": "sku", "fetched_at": "old"}
    first_id = await ingestor.upsert_manual(kb["id"], "标题", "内容", metadata)
    second_id = await ingestor.upsert_manual(kb["id"], "标题", "内容", {**metadata, "fetched_at": "new"})
    assert first_id == second_id and ingestor.report.skipped == 1
    assert ingestor.report.created == 1 and ingestor.report.replaced == 0
    item = await client.get_knowledge(first_id)
    assert item["custom_metadata"]["fetched_at"] == "new"


async def test_dimension_mismatch_reported(server):
    server.models = [{**EMBED, "parameters": {"embedding_parameters": {"dimension": 768}}}]
    async with WeKnoraClient("http://weknora.test", "sk-test", transport=server.transport()) as c:
        ing = Ingestor(c)
        await ing.ensure_embedding_model(None)
    assert ing.report.errors and "768" in ing.report.errors[0]


async def test_embedding_model_created_when_missing(server):
    server.models = []
    spec = {
        "name": "text-embedding-v4",
        "type": "Embedding",
        "source": "remote",
        "parameters": {
            "provider": "openai",
            "base_url": "u",
            "api_key": "k",
            "embedding_parameters": {"dimension": 1024},
        },
    }
    async with WeKnoraClient("http://weknora.test", "sk-test", transport=server.transport()) as c:
        ing = Ingestor(c)
        mid = await ing.ensure_embedding_model(spec)
        assert mid and server.models[0]["name"] == "text-embedding-v4"
        assert await ing.ensure_embedding_model(spec) == mid  # 复用不重复创建


async def test_search_with_knowledge_ids_and_without_rerank(client, server):
    ing = Ingestor(client, embedding_model_id="emb-1")
    r = await ing.ingest_all(DATA)
    kb_ids = [r.kb_ids["kb_manual"], r.kb_ids["kb_tickets"]]
    hits = await client.knowledge_search("滚刷", knowledge_base_ids=kb_ids)
    assert hits and all("knowledge_id" in h for h in hits)
    only = [hits[0]["knowledge_id"]]
    assert {
        h["knowledge_id"]
        for h in await client.knowledge_search(
            "滚刷", knowledge_base_ids=kb_ids, knowledge_ids=only
        )
    } == set(only)


async def test_snapshot_export_and_rollback(client, server, tmp_path):
    ing = Ingestor(client, embedding_model_id="emb-1")
    report = await ing.ingest_all(DATA)
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path, report, source_root=DATA)
    snap = await export_snapshot(client, DATA, manifest_path, tmp_path / "snapshots")
    assert (snap / "kb_manual" / "manual_rv_v1.md").exists() and (
        snap / "kb_tickets" / "tickets.csv"
    ).exists()
    remote = json.loads((snap / "remote.json").read_text(encoding="utf-8"))
    assert len(remote["kb_tickets"]["knowledge"]) == 380 and remote["kb_faq"]["faq_entries"] >= 50
    # 模拟事后误操作：多加一条、删一条
    kb_manual = report.kb_ids["kb_manual"]
    extra = await client.create_manual_knowledge(kb_manual, title="误加文档", content="x")
    victim = next(k for k in server.knowledge.values() if k["title"] == "T0007")
    await client.delete_knowledge(victim["id"])
    assert len(server.knowledge) == DOCUMENT_COUNT
    manifest = await import_snapshot(client, snap, manifest_path, embedding_model_id="emb-1")
    titles = {k["title"] for k in server.knowledge.values()}
    assert "误加文档" not in titles and "T0007" in titles
    assert len(server.knowledge) == DOCUMENT_COUNT
    assert manifest["counts"]["deleted"] == 1 and manifest["counts"]["created"] == 1
    assert extra["id"] not in server.knowledge


async def test_client_errors_do_not_leak_key(server):
    async with WeKnoraClient("http://weknora.test", "sk-WRONG", transport=server.transport()) as c:
        with pytest.raises(WeKnoraError) as ei:
            await c.list_knowledge_bases()
    assert ei.value.status == 401 and "sk-WRONG" not in str(ei.value)


async def test_bootstrap_register_then_login(server):
    async with WeKnoraClient("http://weknora.test", transport=server.transport()) as c:
        assert (await c.auth_config())["registration_mode"] == "self_serve"
        data = await c.register("haike", "h@local.dev", "pw")
        assert data["tenant"]["api_key"] == "sk-test"
        with pytest.raises(WeKnoraError) as ei:
            await c.register("haike", "h@local.dev", "pw")
        assert ei.value.status == 400
        login = await c.login("h@local.dev", "pw")
        assert login["active_tenant"]["id"] == 10001 and login["token"] == "jwt"
        scoped = await c.create_api_key(
            10001, "jwt", name="k", full_access=False
        )  # 自动补默认 capabilities
        assert scoped["full_access"] is False
        with pytest.raises(WeKnoraError, match="owner jwt"):
            await c.create_api_key(10001, "bad", name="k")
        created = await c.create_api_key(10001, "jwt", name="k", full_access=True)
        assert created["api_key"].startswith("sk-") and created["full_access"] is True
