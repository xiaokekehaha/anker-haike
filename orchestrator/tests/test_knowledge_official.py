"""官方资料采集仅使用静态样本；来源漂移和切块不完整不能静默入库。"""

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.knowledge.ingest import Ingestor, parse_front_matter
from app.knowledge.official import Collection, Source, Unit, build, extract_article, render_source
from app.knowledge.official_verify import complete_unit
from app.knowledge.weknora_client import WeKnoraClient
from tests.fake_weknora import FakeWeKnora


@pytest.fixture
def reviewed(tmp_path: Path) -> tuple[Collection, Path]:
    text = "Charging contacts: disconnect power before cleaning. " * 3
    digest = hashlib.sha256(text.encode()).hexdigest()
    source = Source(
        id="official_sample",
        url="https://service.eufy.com/article-description/example",
        product="X10 Pro Omni",
        category="robot_vacuum",
        sku_list=["EUFY-X10-PRO-OMNI"],
        reviewed_source_sha256=digest,
        units=[
            Unit(
                id="c1",
                title="无法充电的触点检查",
                anchor="Charging contacts",
                summary="充电触点需要清洁时，应先关闭机器人并断开基站电源，再清洁双方触点。",
                query="机器人不充电怎么清理触点",
            )
        ],
    )
    (tmp_path / "official_sample.txt").write_text(text)
    (tmp_path / "official_sample.json").write_text(
        json.dumps(
            {
                "url": source.url,
                "source_sha256": digest,
                "title": "Charging troubleshooting",
                "fetched_at": "2026-09-17T00:00:00Z",
            }
        )
    )
    return Collection(batch_id="test", version="2026-09-17.2", sources=[source]), tmp_path


def test_extract_only_article_and_keep_paragraph_boundaries():
    payload = {
        "props": {
            "pageProps": {
                "sfArticleInfo": {
                    "data": {
                        "article": {
                            "title": "Charging",
                            "content": "<p>First step: turn off the robot before cleaning.</p>"
                            "<p>Second step: disconnect the station power supply before cleaning contacts.</p>",
                        }
                    }
                }
            }
        }
    }
    html = '<nav>Unrelated warranty promotion</nav><script id="__NEXT_DATA__" '
    html += 'type="application/json">' + json.dumps(payload) + "</script><footer>Copyright</footer>"
    title, text = extract_article(html)
    assert title == "Charging"
    assert "robot before cleaning.\nSecond step" in text
    assert "warranty" not in text and "Copyright" not in text


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/article-description/example",
        "http://service.eufy.com/article-description/example",
        "https://service.eufy.com/article-description/example?token=secret",
        "https://service.eufy.com:9999/article-description/example",
        "https://service.eufy.com/login",
    ],
)
def test_disallow_non_public_article_urls(reviewed, url):
    collection, _ = reviewed
    with pytest.raises(ValidationError):
        Source.model_validate({**collection.sources[0].model_dump(), "url": url})


def test_changed_source_requires_summary_review(reviewed):
    collection, cache = reviewed
    (cache / "official_sample.txt").write_text("The article has changed.")
    with pytest.raises(ValueError, match="来源正文未核对或已变化"):
        render_source(collection.sources[0], collection, cache)


def test_missing_review_and_missing_anchor_block_generation(reviewed):
    collection, cache = reviewed
    source = collection.sources[0]
    unreviewed = source.model_copy(update={"reviewed_source_sha256": ""})
    with pytest.raises(ValueError, match="未核对"):
        render_source(unreviewed, collection, cache)
    source.units[0].anchor = "nonexistent instruction"
    with pytest.raises(ValueError, match="原文定位词不存在"):
        render_source(source, collection, cache)


def test_do_not_silently_cut_long_operation(reviewed):
    collection, cache = reviewed
    collection.sources[0].units[0].summary *= 8
    with pytest.raises(ValueError, match="超过子块预算"):
        render_source(collection.sources[0], collection, cache)


def test_complete_unit_requires_model_anchor_and_final_precaution(reviewed):
    collection, cache = reviewed
    source = collection.sources[0]
    _, document = render_source(source, collection, cache)
    _, body = parse_front_matter(document)
    unit = source.units[0]
    assert complete_unit(source, unit, body)
    assert not complete_unit(source, unit, body.replace("X10 Pro Omni", "Another Model"))
    assert not complete_unit(source, unit, body.replace("（c1）", ""))
    assert not complete_unit(source, unit, body.replace("再清洁双方触点。", ""))


def test_scope_change_versions_document_and_unknown_sku_blocks_all_writes(reviewed, tmp_path):
    collection, cache = reviewed
    source = collection.sources[0]
    _, first = render_source(source, collection, cache)
    source.sku_list = ["EUFY-S1-PRO"]
    _, second = render_source(source, collection, cache)
    assert (
        parse_front_matter(first)[0]["doc_version"] != parse_front_matter(second)[0]["doc_version"]
    )
    source.sku_list = ["UNKNOWN"]
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="不存在或品类错误"):
        build(collection, cache, output)
    assert not output.exists()


async def test_incomplete_metadata_readback_is_reported(monkeypatch):
    server = FakeWeKnora()
    async with WeKnoraClient(
        "http://weknora.test", "sk-test", transport=server.transport()
    ) as client:
        kb = await client.create_knowledge_base({"name": "sample", "type": "document"})
        item = await client.create_manual_knowledge(kb["id"], title="sample", content="body")
        get = client.get_knowledge

        async def partial_metadata(knowledge_id):
            data = await get(knowledge_id)
            data["custom_metadata"].pop("source_url", None)
            return data

        monkeypatch.setattr(client, "get_knowledge", partial_metadata)
        ingestor = Ingestor(client)
        await ingestor._set_metadata(
            item["id"],
            "sample",
            {
                "scope": "sku",
                "source_url": "https://service.eufy.com/article-description/example",
            },
        )
        assert ingestor.report.errors == ["metadata not persisted: sample"]
