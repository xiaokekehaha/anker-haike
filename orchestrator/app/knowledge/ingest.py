"""官方 Q&A 入库 WeKnora（haike_kb_qa）：一条 Q&A 一个 knowledge，按 qa_id + 源版本幂等。

切分：库级 chunk_size 1500、关闭父子分块。Q&A 正文中位 432 字、p90 1143 字、最长 2437 字，
基本一条一块；不在条目中间切开，否则后半块丢了标题里的错误码与 PN，召回后无法归属型号。
正文 = 标题 + 去掉 URL 的内容：标题含错误码与 PN，BM25 才能命中「4090」「T2352」；
URL 会被分词成大量噪声词，链接改由本地 QAIndex 挂到步骤卡上。

custom_metadata 只能是标量：pn / codes 用逗号串。scope / sku_list / category / doc_id / doc_version
沿用检索适配器的约定，范围过滤不用改。63 单工单是评测集，不入库。
结果写 manifest（kb_ver = 源 qa.yaml 的 sha + embedding 模型名）。
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.knowledge.weknora_client import WeKnoraClient, WeKnoraError
from app.official.qa_index import Guide, QAIndex

log = logging.getLogger("knowledge.ingest")

KB_QA = "haike_kb_qa"
QA_CHUNK = 1500
EMBEDDING_DIM = 1024
LEGACY_KBS = ("haike_kb_manual", "haike_kb_faq", "haike_kb_tickets")


@dataclass
class IngestReport:
    kb_ids: dict[str, str] = field(default_factory=dict)
    created: int = 0
    replaced: int = 0
    skipped: int = 0
    deleted: int = 0
    embedding: dict[str, Any] = field(default_factory=dict)
    rerank: dict[str, Any] = field(default_factory=dict)
    docs: dict[str, str] = field(default_factory=dict)  # 来源 -> 版本
    errors: list[str] = field(default_factory=list)


def qa_chunking_config() -> dict[str, Any]:
    return {
        "chunk_size": QA_CHUNK,
        "chunk_overlap": 0,
        "separators": ["\n\n", "\n", ". ", " "],
        "enable_multimodal": False,
        "enable_parent_child": False,
    }


def qa_content(guide: Guide) -> str:
    body = guide.answer if guide.kind != "steps" else "\n".join(f"{s.no}. {s.text}" for s in guide.steps)
    tips = f"\nTips: {guide.tips}" if guide.tips else ""
    return f"{guide.title}\n{body}{tips}".strip()


def qa_metadata(guide: Guide, version: str) -> dict[str, Any]:
    return {
        "doc_id": guide.qa_id,
        "doc_version": version,
        "kb": "kb_qa",
        "scope": "sku",
        "sku_list": ",".join(guide.pns),
        "category": guide.category,
        "codes": ",".join(guide.codes),
        "kind": guide.kind,
    }


class Ingestor:
    def __init__(self, client: WeKnoraClient):
        self.client = client
        self.report = IngestReport()

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
        self.report.rerank = {"id": chosen.get("id"), "name": chosen.get("name")}
        return chosen.get("id")

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
        self.report.embedding = {"id": chosen.get("id"), "name": chosen.get("name"), "dimension": dim}
        if dim is not None and int(dim) != EMBEDDING_DIM:
            self.report.errors.append(f"embedding dimension {dim} != {EMBEDDING_DIM} (pgvector/kb_ver 约定)")
        return chosen.get("id")

    async def ensure_qa_kb(self, embedding_model_id: str | None) -> dict:
        for kb in await self.client.list_knowledge_bases():
            if kb.get("name") == KB_QA:
                return kb
        payload: dict[str, Any] = {
            "name": KB_QA,
            "description": "主办方官方 Q&A（扫地机 / 吸奶器 / SoloCam），一条 Q&A 一个知识",
            "type": "document",
            "chunking_config": qa_chunking_config(),
            "storage_provider_config": {"provider": "local"},
        }
        if embedding_model_id:
            payload["embedding_model_id"] = embedding_model_id
        kb = await self.client.create_knowledge_base(payload)
        log.info("created kb %s id=%s", KB_QA, kb.get("id"))
        return kb

    async def ingest_qa(
        self, *, embedding_model_id: str | None, index: QAIndex | None = None, prune: bool = True
    ) -> dict:
        index = index or QAIndex.build()
        report = self.report
        kb = await self.ensure_qa_kb(embedding_model_id)
        report.kb_ids["kb_qa"] = kb["id"]
        existing: dict[str, list[dict]] = {}
        for k in await self.client.list_knowledge(kb["id"]):
            existing.setdefault(k.get("title") or "", []).append(k)
        wanted: set[str] = set()
        for guide in index.guides.values():
            if not guide.visible:
                continue
            title = guide.qa_id
            wanted.add(title)
            current = existing.get(title, [])
            if any(
                (k.get("custom_metadata") or k.get("metadata") or {}).get("doc_version") == index.version
                for k in current
            ):
                report.skipped += 1
                continue
            for k in current:
                await self.client.delete_knowledge(k["id"])
                report.replaced += 1
            created = await self.client.create_manual_knowledge(kb["id"], title=title, content=qa_content(guide))
            await self.client.update_knowledge(created["id"], custom_metadata=qa_metadata(guide, index.version))
            report.created += 1
        if prune:
            for title, items in existing.items():
                if title not in wanted:
                    for k in items:
                        await self.client.delete_knowledge(k["id"])
                        report.deleted += 1
        report.docs["official_qa"] = index.version
        return kb

    async def drop_legacy_kbs(self) -> list[str]:
        """删除自造的中文手册 / FAQ / 合成工单库（2026-10-08 起只用官方 Q&A）。"""
        dropped = []
        for kb in await self.client.list_knowledge_bases():
            if kb.get("name") in LEGACY_KBS:
                await self.client.delete_knowledge_base(kb["id"])
                dropped.append(kb["name"])
        return dropped


def write_manifest(path: Path, report: IngestReport, *, source_root: Path) -> dict[str, Any]:
    manifest = {
        "kb_ver": f"{max(report.docs.values(), default='0')}+{(report.embedding.get('name') or 'no-embedding')}",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_root": str(source_root),
        "chunking": {"chunk_size": QA_CHUNK, "parent_child": False, "unit": "one Q&A per knowledge"},
        "embedding": {**report.embedding, "expected_dimension": EMBEDDING_DIM},
        "rerank": report.rerank,
        "knowledge_bases": report.kb_ids,
        "docs": report.docs,
        "counts": {
            "created": report.created,
            "replaced": report.replaced,
            "skipped": report.skipped,
            "deleted": report.deleted,
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
            counts[k.get("parse_status", "unknown")] = counts.get(k.get("parse_status", "unknown"), 0) + 1
        pending = counts.get("pending", 0) + counts.get("processing", 0) + counts.get("finalizing", 0)
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
