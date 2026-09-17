"""定向采集公开官方正文，按已核对的中文语义单元生成可追溯知识文件。

fetch 只获取来源；build 必须与清单中审核时固定的正文哈希一致，不会把网页变化自动发布。
正式入库仍使用 make kb-ingest，沿用快照、父子分块和型号范围过滤。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.catalog.service import ProductCatalog
from app.knowledge.ingest import CHILD_CHUNK
from app.settings import CONFIG_DIR, REPO_ROOT

HOSTS = {"service.anker.com", "service.eufy.com", "service.soundcore.com"}
SOURCE_FILE = REPO_ROOT / "data/knowledge/sources/anker_official.yaml"
CACHE = REPO_ROOT / "tmp/official-knowledge"
OUTPUT = REPO_ROOT / "data/knowledge/kb_manual"
NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.DOTALL)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Unit(Strict):
    id: str = Field(pattern=r"^c[0-9]+$")
    title: str
    summary: str = Field(min_length=20)
    anchor: str = Field(min_length=3)
    query: str


class Source(Strict):
    id: str = Field(pattern=r"^official_[a-z0-9_]+$")
    url: str
    product: str
    category: str
    sku_list: list[str] = Field(min_length=1)
    reviewed_source_sha256: str = Field(default="", pattern=r"^(|[a-f0-9]{64})$")
    units: list[Unit] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_source(self) -> Source:
        parsed = urlsplit(self.url)
        if parsed.scheme != "https" or parsed.hostname not in HOSTS:
            raise ValueError("仅允许清单内的官方 HTTPS 支持站")
        if parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment:
            raise ValueError("来源必须为无认证参数的规范 URL")
        if not parsed.path.startswith("/article-description/"):
            raise ValueError("本批仅接受默认站点技术文章，不接地区政策或其他页面")
        if len({u.id for u in self.units}) != len(self.units):
            raise ValueError("重复语义单元 id")
        return self


class Collection(Strict):
    batch_id: str
    version: str
    sources: list[Source] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_sources(self) -> Collection:
        if len({s.id for s in self.sources}) != len(self.sources):
            raise ValueError("重复来源 id")
        if len({s.url for s in self.sources}) != len(self.sources):
            raise ValueError("重复来源 URL")
        return self


class Article(BaseModel):
    title: str
    content: str


class TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"p", "li", "br", "tr", "h1", "h2", "h3", "td"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "li", "tr", "h1", "h2", "h3", "td"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def extract_article(html: str) -> tuple[str, str]:
    match = NEXT_DATA.search(html)
    if match is None:
        raise ValueError("页面没有可识别的官方文章结构")
    data = json.loads(match.group(1))
    article = Article.model_validate(data["props"]["pageProps"]["sfArticleInfo"]["data"]["article"])
    parser = TextParser()
    parser.feed(article.content)
    lines = [" ".join(line.split()) for line in "".join(parser.parts).splitlines()]
    text = "\n".join(line for line in lines if line)
    if len(text) < 80:
        raise ValueError("正文不足；下载入口、视频占位或空页面不能作为文字依据")
    return article.title, text


def load_collection(path: Path = SOURCE_FILE) -> Collection:
    return Collection.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


async def fetch(collection: Collection, cache: Path) -> list[dict[str, str | int]]:
    cache.mkdir(parents=True, exist_ok=True)
    report = []
    async with httpx.AsyncClient(timeout=40, follow_redirects=False) as client:
        for source in collection.sources:
            response = await client.get(source.url)
            response.raise_for_status()
            title, text = extract_article(response.text)
            stamp = datetime.now(UTC).isoformat()
            row = {
                "id": source.id,
                "url": source.url,
                "title": title,
                "fetched_at": stamp,
                "source_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "html_sha256": hashlib.sha256(response.content).hexdigest(),
                "characters": len(text),
            }
            (cache / f"{source.id}.html").write_bytes(response.content)
            (cache / f"{source.id}.txt").write_text(text, encoding="utf-8")
            (cache / f"{source.id}.json").write_text(
                json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            report.append(row)
            print(f"fetched {source.id}: {len(text)} characters", flush=True)
            await asyncio.sleep(0.3)
    return report


def render_source(source: Source, collection: Collection, cache: Path) -> tuple[str, str]:
    record = json.loads((cache / f"{source.id}.json").read_text(encoding="utf-8"))
    text = (cache / f"{source.id}.txt").read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode()).hexdigest()
    if not source.reviewed_source_sha256 or digest != source.reviewed_source_sha256:
        raise ValueError(f"{source.id}: 来源正文未核对或已变化，需复核中文摘要")
    if record["url"] != source.url or record["source_sha256"] != digest:
        raise ValueError(f"{source.id}: 缓存与来源清单不一致")
    blocks = []
    for unit in source.units:
        if unit.anchor.casefold() not in text.casefold():
            raise ValueError(f"{source.id}/{unit.id}: 原文定位词不存在")
        block = f"## {source.product}：{unit.title}（{unit.id}）\n官方资料中文整理：{unit.summary}"
        if len(block) > CHILD_CHUNK:
            raise ValueError(f"{source.id}/{unit.id}: {len(block)} 字符超过子块预算，需按语义复编")
        blocks.append(block)
    body = "\n\n".join(blocks) + "\n"
    content_hash = hashlib.sha256(body.encode()).hexdigest()
    meta = {
        "doc_id": source.id,
        "title": f"官方资料整理｜{source.product}｜{source.units[0].title}",
        "scope": "sku",
        "category": source.category,
        "sku_list": source.sku_list,
        "source_type": "official_support_summary",
        "source_url": source.url,
        "source_title": record["title"],
        "source_language": "en",
        "language": "zh-CN",
        "region_list": [],
        "source_sha256": digest,
        "content_sha256": content_hash,
        "fetched_at": record["fetched_at"],
        "batch_id": collection.batch_id,
        "publish_state": "published",
        "review_status": "agent_source_checked",
        "scope_note": "型号技术支持摘要；不包含地区质保、召回、航空或医疗结论",
        "section_ids": [u.id for u in source.units],
    }
    # 正文、来源、适用范围变化均产生新版本；仅重新抓取的时间变化不重建向量。
    versioned = {k: v for k, v in meta.items() if k != "fetched_at"}
    revision = hashlib.sha256(json.dumps(versioned, sort_keys=True).encode()).hexdigest()
    meta["doc_version"] = f"{collection.version}-{revision[:12]}"
    return source.id, "---\n" + yaml.safe_dump(
        meta, allow_unicode=True, sort_keys=False
    ) + "---\n\n" + body


def build(collection: Collection, cache: Path, output: Path) -> int:
    catalog = ProductCatalog.from_yaml(CONFIG_DIR / "products.yaml")
    rendered = []
    for source in collection.sources:
        for sku in source.sku_list:
            product = catalog.get(sku)
            if product is None or product.category != source.category:
                raise ValueError(f"{source.id}: 型号 {sku} 不存在或品类错误")
        rendered.append(render_source(source, collection, cache))
    output.mkdir(parents=True, exist_ok=True)
    for doc_id, document in rendered:
        (output / f"{doc_id}.md").write_text(document, encoding="utf-8")
    return len(rendered)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["fetch", "build"])
    parser.add_argument("--sources", type=Path, default=SOURCE_FILE)
    parser.add_argument("--cache", type=Path, default=CACHE)
    args = parser.parse_args()
    collection = load_collection(args.sources)
    if args.command == "fetch":
        rows = asyncio.run(fetch(collection, args.cache))
        print(f"fetched {len(rows)} sources; review hashes and summaries before build")
    else:
        print(f"built {build(collection, args.cache, OUTPUT)} knowledge documents")


if __name__ == "__main__":
    main()
