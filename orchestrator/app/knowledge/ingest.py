"""kb_manual / kb_tickets 的 bootstrap 与幂等导入（03 §3.2、09 §2.2）。

- 知识库：按名称查找已存在则复用；新建时父子分块 800 / 200、混合检索（BM25 + 向量默认开启）、图谱关闭。
- 文档（说明书 / 排障手册）：Markdown 源文件带 front-matter 元数据，以在线文本入库；以 title 幂等，
  doc_version 相同则跳过，不同则删旧建新；元数据写入 custom_metadata。
- FAQ：faq 类型知识库，批量 replace 模式整体覆盖（天然幂等）。
- 工单：CSV 每行一条 manual 知识（WeKnora 原生 CSV 上传会整表变一份文档，不满足逐条元数据），title=ticket_id。
- 结果写 manifest（kb_ver：知识库 id、embedding 模型与维度、各文档 doc_version、条数）。
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from app.knowledge.weknora_client import WeKnoraClient, WeKnoraError

log = logging.getLogger("knowledge.ingest")

KB_MANUAL = "haike_kb_manual"
KB_TICKETS = "haike_kb_tickets"
KB_FAQ = "haike_kb_faq"
PARENT_CHUNK = 800
CHILD_CHUNK = 200
EMBEDDING_DIM = 1024


def chunking_config() -> dict[str, Any]:
    return {
        "chunk_size": PARENT_CHUNK,
        "chunk_overlap": 80,
        "separators": ["\n\n", "\n", "。", "！", "？", ".", " "],
        "enable_multimodal": False,
        "enable_parent_child": True,
        "parent_chunk_size": PARENT_CHUNK,
        "child_chunk_size": CHILD_CHUNK,
    }


def kb_payload(
    name: str,
    kb_type: str,
    embedding_model_id: str | None,
    description: str,
    rerank_model_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "description": description,
        "type": kb_type,
        "chunking_config": chunking_config(),
        "storage_provider_config": {"provider": "local"},
    }
    if embedding_model_id:
        payload["embedding_model_id"] = embedding_model_id
    if rerank_model_id:
        # WeKnora v0.8.0 实测：知识库对象没有 rerank_model_id 字段，创建 / 更新都静默忽略；hybrid-search 只做
        # BM25 + 向量的 RRF 融合（分值 ≈ 1/(60+rank)），重排属于其 chat 会话管线。保留字段以备升级后生效。
        payload["rerank_model_id"] = rerank_model_id
    return payload


# ---- 源文件 ----


@dataclass
class ManualDoc:
    doc_id: str
    title: str
    content: str
    metadata: dict[str, Any]
    path: Path


def parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    _, fm, body = text.split("---", 2)
    return yaml.safe_load(fm) or {}, body.lstrip("\n")


def load_manual_docs(root: Path) -> list[ManualDoc]:
    docs = []
    for path in sorted((root / "kb_manual").glob("*.md")):
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        required = {"doc_id", "title", "scope", "category", "doc_version"}
        missing = required - set(meta)
        if missing:
            raise ValueError(f"{path}: front-matter missing {sorted(missing)}")
        docs.append(
            ManualDoc(
                doc_id=meta["doc_id"],
                title=meta["title"],
                content=body,
                metadata={
                    "doc_id": meta["doc_id"],
                    "scope": meta["scope"],
                    # WeKnora custom_metadata 只接受标量：sku_list 以逗号串存，读取时 split
                    "sku_list": ",".join(meta.get("sku_list") or []),
                    "category": meta["category"],
                    "doc_version": str(meta["doc_version"]),
                    "kb": "kb_manual",
                },
                path=path,
            )
        )
    return docs


def load_faq(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = yaml.safe_load((root / "kb_manual" / "faq_rv.yaml").read_text(encoding="utf-8"))
    meta = {
        "doc_id": data["doc_id"],
        "scope": data["scope"],
        "category": data["category"],
        "doc_version": str(data["doc_version"]),
        "kb": "kb_manual",
    }
    entries = [
        {
            "standard_question": e["q"],
            "similar_questions": list(e.get("similar") or []),
            "answers": [e["a"]],
            "answer_strategy": "all",
            "tag_name": f"{data['category']}/{data['scope']}",
            "is_enabled": True,
        }
        for e in data["entries"]
    ]
    return meta, entries


def load_tickets(root: Path) -> list[dict[str, str]]:
    with (root / "kb_tickets" / "tickets.csv").open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def ticket_content(row: dict[str, str]) -> str:
    return (
        f"工单 {row['ticket_id']}｜产品 {row['sku']}\n"
        f"现象：{row['symptom']}\n原因：{row['root_cause']}\n处理步骤：{row['steps']}\n"
        f"结果：{row['result']}"
    )


def sku_list_of(metadata: dict[str, Any] | None) -> list[str]:
    raw = (metadata or {}).get("sku_list") or ""
    return [s for s in str(raw).split(",") if s]


def ticket_metadata(row: dict[str, str]) -> dict[str, Any]:
    return {
        "doc_id": row["ticket_id"],
        "scope": "sku",
        "sku_list": row["sku"],
        "category": row["category"],
        "doc_version": row["doc_version"],
        "result": row["result"],
        "kb": "kb_tickets",
    }


# ---- 导入 ----


@dataclass
class IngestReport:
    kb_ids: dict[str, str] = field(default_factory=dict)
    created: int = 0
    replaced: int = 0
    skipped: int = 0
    deleted: int = 0
    faq_entries: int = 0
    embedding: dict[str, Any] = field(default_factory=dict)
    recreated_kbs: list[str] = field(default_factory=list)
    rerank: dict[str, Any] = field(default_factory=dict)
    docs: dict[str, str] = field(default_factory=dict)  # doc_id -> doc_version
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


class Ingestor:
    def __init__(
        self,
        client: WeKnoraClient,
        *,
        embedding_model_id: str | None = None,
        recreate_on_embedding_change: bool = False,
    ):
        self.client = client
        self.embedding_model_id = embedding_model_id
        self.rerank_model_id: str | None = None
        self.recreate_on_embedding_change = recreate_on_embedding_change
        self.report = IngestReport()

    async def ensure_kb(self, name: str, kb_type: str, description: str) -> dict:
        """按名称复用；embedding 模型与目标不同且允许重建时删旧建新（知识库 embedding 在创建时绑定，不能改）。"""
        for kb in await self.client.list_knowledge_bases():
            if kb.get("name") != name:
                continue
            bound = kb.get("embedding_model_id")
            if (
                self.recreate_on_embedding_change
                and self.embedding_model_id
                and bound
                and bound != self.embedding_model_id
            ):
                log.warning(
                    "kb %s bound to embedding %s != %s: recreating",
                    name,
                    bound,
                    self.embedding_model_id,
                )
                await self.client.delete_knowledge_base(kb["id"])
                self.report.recreated_kbs.append(name)
                break
            return kb
        kb = await self.client.create_knowledge_base(
            kb_payload(name, kb_type, self.embedding_model_id, description, self.rerank_model_id)
        )
        log.info("created kb %s id=%s rerank=%s", name, kb.get("id"), self.rerank_model_id)
        return kb

    async def ensure_rerank_model(self, spec: dict[str, Any] | None) -> str | None:
        """按名称复用已登记的 Rerank 模型；spec 为 None 时不绑定（WeKnora 走默认或不重排）。"""
        if spec is None:
            return None
        models = await self.client.list_models()
        chosen = next(
            (m for m in models if m.get("type") == "Rerank" and m.get("name") == spec["name"]), None
        )
        if chosen is None:
            chosen = await self.client.create_model(spec)
            log.info("created rerank model %s", spec["name"])
        self.rerank_model_id = chosen.get("id")
        self.report.rerank = {"id": chosen.get("id"), "name": chosen.get("name")}
        return self.rerank_model_id

    async def ensure_embedding_model(self, spec: dict[str, Any] | None) -> str | None:
        """按名称复用已登记的 Embedding 模型；spec 为 None 时不管模型（沿用 builtin_models）。"""
        models = await self.client.list_models()
        embed = [m for m in models if str(m.get("type", "")).lower() == "embedding"]
        if spec is None:
            chosen = next((m for m in embed if m.get("is_default")), embed[0] if embed else None)
        else:
            chosen = next((m for m in embed if m.get("name") == spec["name"]), None)
            if chosen is None:
                chosen = await self.client.create_model(spec)
                log.info("created embedding model %s", spec["name"])
        if chosen is None:
            return None
        dim = (chosen.get("parameters") or {}).get("embedding_parameters", {}).get("dimension")
        self.report.embedding = {
            "id": chosen.get("id"),
            "name": chosen.get("name"),
            "dimension": dim,
        }
        if dim is not None and int(dim) != EMBEDDING_DIM:
            self.report.errors.append(
                f"embedding dimension {dim} != {EMBEDDING_DIM} (pgvector/kb_ver 约定)"
            )
        return chosen.get("id")

    async def upsert_manual(
        self, kb_id: str, title: str, content: str, metadata: dict[str, Any]
    ) -> str:
        existing = await self.client.list_knowledge(kb_id)
        same_title = [k for k in existing if k.get("title") == title]
        current = next(
            (
                k
                for k in same_title
                if (k.get("custom_metadata") or k.get("metadata") or {}).get("doc_version")
                == metadata["doc_version"]
            ),
            None,
        )
        if current is not None:
            self.report.skipped += 1
            return current["id"]
        for k in same_title:  # 版本不同：删旧建新
            await self.client.delete_knowledge(k["id"])
            self.report.replaced += 1
        created = await self.client.create_manual_knowledge(kb_id, title=title, content=content)
        await self._set_metadata(created["id"], title, metadata)
        self.report.created += 1 if not same_title else 0
        return created["id"]

    async def _set_metadata(self, knowledge_id: str, title: str, metadata: dict[str, Any]) -> None:
        """写 custom_metadata 并回读校验，缺失重试一次。2026-09-13 实测：批量导入后立即 list 有 1/200 条元数据
        读到空（列表视图滞后，稍后再读已存在）；回读用 get 单条，避免把滞后误判成丢失。"""
        for attempt in (1, 2):
            await self.client.update_knowledge(knowledge_id, custom_metadata=metadata)
            full = await self.client.get_knowledge(knowledge_id)
            meta = full.get("custom_metadata") or full.get("metadata") or {}
            if meta.get("scope"):
                return
            log.warning("custom_metadata missing after update title=%s attempt=%d", title, attempt)
        self.report.errors.append(f"metadata not persisted: {title}")

    async def ingest_all(self, root: Path, *, prune: bool = False) -> IngestReport:
        r = self.report
        kb_manual = await self.ensure_kb(
            KB_MANUAL, "document", "说明书 / 排障手册（scope 元数据见 custom_metadata）"
        )
        kb_faq = await self.ensure_kb(KB_FAQ, "faq", "扫地机 FAQ")
        kb_tickets = await self.ensure_kb(KB_TICKETS, "document", "历史工单，每行一条")
        r.kb_ids = {
            "kb_manual": kb_manual["id"],
            "kb_faq": kb_faq["id"],
            "kb_tickets": kb_tickets["id"],
        }

        wanted_titles = {kb_manual["id"]: set(), kb_tickets["id"]: set()}
        for doc in load_manual_docs(root):
            wanted_titles[kb_manual["id"]].add(doc.title)
            await self.upsert_manual(kb_manual["id"], doc.title, doc.content, doc.metadata)
            r.docs[doc.doc_id] = doc.metadata["doc_version"]

        faq_meta, entries = load_faq(root)
        await self.client.upsert_faq_entries(kb_faq["id"], entries, mode="replace")
        r.faq_entries = len(entries)
        r.docs[faq_meta["doc_id"]] = faq_meta["doc_version"]

        rows = load_tickets(root)
        for row in rows:
            title = row["ticket_id"]
            wanted_titles[kb_tickets["id"]].add(title)
            await self.upsert_manual(
                kb_tickets["id"], title, ticket_content(row), ticket_metadata(row)
            )
        if rows:
            r.docs["tickets"] = rows[0]["doc_version"]

        if prune:
            for kb_id, titles in wanted_titles.items():
                for k in await self.client.list_knowledge(kb_id):
                    if k.get("title") not in titles:
                        await self.client.delete_knowledge(k["id"])
                        r.deleted += 1
        return r


def write_manifest(path: Path, report: IngestReport, *, source_root: Path) -> dict[str, Any]:
    manifest = {
        "kb_ver": f"{max(report.docs.values(), default='0')}+{(report.embedding.get('name') or 'no-embedding')}",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_root": str(source_root),
        "chunking": {
            "parent": PARENT_CHUNK,
            "child": CHILD_CHUNK,
            "parent_child": True,
            "graph": False,
        },
        "embedding": {**report.embedding, "expected_dimension": EMBEDDING_DIM},
        "rerank": report.rerank,
        "knowledge_bases": report.kb_ids,
        "docs": report.docs,
        "counts": {
            "created": report.created,
            "replaced": report.replaced,
            "skipped": report.skipped,
            "deleted": report.deleted,
            "faq_entries": report.faq_entries,
        },
        "errors": report.errors,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


async def wait_parsed(
    client: WeKnoraClient, kb_id: str, *, timeout_s: float = 120, poll_s: float = 3
) -> dict[str, int]:
    """等待知识库内解析完成，返回各 parse_status 计数（embedding 失败会体现在 failed）。"""
    deadline = asyncio.get_event_loop().time() + timeout_s
    while True:
        items = await client.list_knowledge(kb_id)
        counts: dict[str, int] = {}
        for k in items:
            counts[k.get("parse_status", "unknown")] = (
                counts.get(k.get("parse_status", "unknown"), 0) + 1
            )
        pending = (
            counts.get("pending", 0) + counts.get("processing", 0) + counts.get("finalizing", 0)
        )
        if pending == 0 or asyncio.get_event_loop().time() > deadline:
            return counts
        await asyncio.sleep(poll_s)


async def verify_metadata(client: WeKnoraClient, kb_id: str) -> list[dict[str, Any]]:
    """导出知识及其 custom_metadata，供验收「元数据在 WeKnora 中可查」。"""
    out = []
    for k in await client.list_knowledge(kb_id):
        try:
            full = await client.get_knowledge(k["id"])
        except WeKnoraError:
            full = k
        out.append(
            {
                "id": k["id"],
                "title": k.get("title"),
                "parse_status": full.get("parse_status"),
                "custom_metadata": full.get("custom_metadata") or full.get("metadata"),
            }
        )
    return out
