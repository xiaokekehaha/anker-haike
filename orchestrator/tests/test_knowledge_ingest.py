"""票 26：知识库 bootstrap / 官方 Q&A 幂等导入 / 元数据 / 分块配置 / manifest（内存版 WeKnora）。

2026-10-08 起只导入官方 Q&A，一条 Q&A 一个 knowledge；旧的手册 / FAQ / 工单库已删除。
"""

from __future__ import annotations

import pytest

from app.knowledge import WeKnoraClient, WeKnoraError
from app.knowledge.ingest import (
    EMBEDDING_DIM,
    KB_QA,
    LEGACY_KBS,
    QA_CHUNK,
    Ingestor,
    qa_content,
    qa_metadata,
    verify_metadata,
    write_manifest,
)
from app.official.qa_index import QAIndex
from app.settings import REPO_ROOT
from tests.fake_weknora import FakeWeKnora

FULL = QAIndex.build()
SAMPLE = ("rv-0004", "rv-0147", "rv-0063", "bp-0009", "bp-0169")
EMBED = {
    "id": "emb-1",
    "name": "text-embedding-v4",
    "type": "Embedding",
    "is_default": True,
    "parameters": {"embedding_parameters": {"dimension": 1024}},
}


def _index(ids=SAMPLE, version=FULL.version) -> QAIndex:
    return QAIndex(guides={q: FULL.guides[q] for q in ids}, version=version)


@pytest.fixture
def server():
    return FakeWeKnora(models=[dict(EMBED)])


@pytest.fixture
async def client(server):
    async with WeKnoraClient("http://weknora.test", "sk-test", transport=server.transport()) as c:
        yield c


def test_qa_content_keeps_title_codes_and_drops_urls():
    g = FULL.guides["rv-0147"]
    content = qa_content(g)
    assert content.startswith(g.title) and "3212" in content and "T2352" in content
    assert "http" not in content
    meta = qa_metadata(g, "v1")
    assert meta == {
        "doc_id": "rv-0147", "doc_version": "v1", "kb": "kb_qa", "scope": "sku",
        "sku_list": "T2352,T2353", "category": "robot_vacuum", "codes": "3212", "kind": g.kind,
    }
    # custom_metadata 只能是标量
    assert all(isinstance(v, str) for v in meta.values())


async def test_ingest_creates_single_qa_kb_one_knowledge_per_entry(client, server):
    ing = Ingestor(client)
    report = ing.report
    kb = await ing.ingest_qa(embedding_model_id="emb-1", index=_index())
    assert {k["name"] for k in server.kbs.values()} == {KB_QA}
    cc = server.kbs[kb["id"]]["chunking_config"]
    assert cc["chunk_size"] == QA_CHUNK == 1500 and cc["enable_parent_child"] is False
    assert server.kbs[kb["id"]]["embedding_model_id"] == "emb-1"
    assert report.kb_ids == {"kb_qa": kb["id"]} and report.created == len(SAMPLE)
    assert report.docs == {"official_qa": FULL.version}
    items = await verify_metadata(client, kb["id"])
    by_title = {i["title"]: i["custom_metadata"] for i in items}
    assert set(by_title) == set(SAMPLE)
    assert by_title["bp-0009"]["category"] == "breast_pump" and by_title["bp-0009"]["sku_list"] == "T8D04"


async def test_ingest_is_idempotent_and_version_bump_replaces(client, server):
    await Ingestor(client).ingest_qa(embedding_model_id="emb-1", index=_index())
    again = Ingestor(client)
    await again.ingest_qa(embedding_model_id="emb-1", index=_index())
    second = again.report
    assert (second.created, second.replaced, second.skipped) == (0, 0, len(SAMPLE))
    assert len(server.knowledge) == len(SAMPLE) and len(server.kbs) == 1
    bumped = Ingestor(client)
    await bumped.ingest_qa(embedding_model_id="emb-1", index=_index(version="v-next"))
    third = bumped.report
    assert third.replaced == third.created == len(SAMPLE) and third.skipped == 0
    assert len(server.knowledge) == len(SAMPLE)
    assert {k["custom_metadata"]["doc_version"] for k in server.knowledge.values()} == {"v-next"}


async def test_prune_removes_entries_no_longer_in_source(client, server):
    await Ingestor(client).ingest_qa(embedding_model_id="emb-1", index=_index())
    ing = Ingestor(client)
    await ing.ingest_qa(embedding_model_id="emb-1", index=_index(SAMPLE[:2]))
    report = ing.report
    assert report.deleted == len(SAMPLE) - 2
    assert {k["title"] for k in server.knowledge.values()} == set(SAMPLE[:2])


async def test_manifest_records_kb_ver_bound_to_embedding(client, tmp_path):
    ing = Ingestor(client)
    embedding_id = await ing.ensure_embedding_model(None)
    await ing.ingest_qa(embedding_model_id=embedding_id, index=_index())
    manifest = write_manifest(tmp_path / "manifest.json", ing.report, source_root=REPO_ROOT / "data" / "official")
    assert manifest["kb_ver"] == f"{FULL.version}+text-embedding-v4"
    assert manifest["embedding"]["dimension"] == EMBEDDING_DIM == 1024
    assert manifest["errors"] == [] and set(manifest["knowledge_bases"]) == {"kb_qa"}
    assert manifest["chunking"]["parent_child"] is False


async def test_search_with_knowledge_ids(client, server):
    ing = Ingestor(client)
    await ing.ingest_qa(embedding_model_id="emb-1", index=_index())
    kb_ids = [ing.report.kb_ids["kb_qa"]]
    hits = await client.knowledge_search("mop", knowledge_base_ids=kb_ids)
    assert len(hits) == 2 and all("knowledge_id" in h for h in hits)
    only = [hits[0]["knowledge_id"]]
    assert {
        h["knowledge_id"]
        for h in await client.knowledge_search("mop", knowledge_base_ids=kb_ids, knowledge_ids=only)
    } == set(only)


async def test_legacy_kbs_are_dropped(client, server):
    for name in LEGACY_KBS:
        await client.create_knowledge_base({"name": name, "type": "document"})
    await client.create_knowledge_base({"name": KB_QA, "type": "document"})
    assert sorted(await Ingestor(client).drop_legacy_kbs()) == sorted(LEGACY_KBS)
    assert {k["name"] for k in server.kbs.values()} == {KB_QA}


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
