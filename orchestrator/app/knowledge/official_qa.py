"""官方 Q&A 入库 WeKnora（haike_kb_qa）：一条 Q&A 一个 knowledge，按 qa_id + 源版本幂等。

切分：库级 chunk_size 1500、关闭父子分块。Q&A 正文中位 432 字、p90 1143 字、最长 2437 字，
基本一条一块；不在条目中间切开，否则后半块丢了标题里的错误码与 PN，召回后无法归属型号。
正文 = 标题 + 去掉 URL 的内容：标题含错误码与 PN，BM25 才能命中「4090」「T2352」；
URL 会被分词成大量噪声词，链接改由本地 QAIndex 挂到步骤卡上。

custom_metadata 只能是标量：pn / codes 用逗号串。scope / sku_list / category / doc_id / doc_version
沿用检索适配器的约定，范围过滤不用改。63 单工单是评测集，不入库。
"""

from __future__ import annotations

import logging
from typing import Any

from app.knowledge.ingest import EMBEDDING_DIM, IngestReport
from app.knowledge.weknora_client import WeKnoraClient
from app.official.qa_index import Guide, QAIndex

log = logging.getLogger("knowledge.official_qa")

KB_QA = "haike_kb_qa"
QA_CHUNK = 1500
LEGACY_KBS = ("haike_kb_manual", "haike_kb_faq", "haike_kb_tickets")


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


async def ensure_qa_kb(client: WeKnoraClient, report: IngestReport, embedding_model_id: str | None) -> dict:
    for kb in await client.list_knowledge_bases():
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
    kb = await client.create_knowledge_base(payload)
    log.info("created kb %s id=%s", KB_QA, kb.get("id"))
    return kb


async def ingest_qa(
    client: WeKnoraClient,
    report: IngestReport,
    *,
    embedding_model_id: str | None,
    index: QAIndex | None = None,
    prune: bool = True,
) -> dict[str, Any]:
    index = index or QAIndex.build()
    kb = await ensure_qa_kb(client, report, embedding_model_id)
    report.kb_ids["kb_qa"] = kb["id"]
    existing: dict[str, list[dict]] = {}
    for k in await client.list_knowledge(kb["id"]):
        existing.setdefault(k.get("title") or "", []).append(k)
    wanted: set[str] = set()
    for guide in index.guides.values():
        if not guide.visible:
            continue
        title = guide.qa_id
        wanted.add(title)
        meta = qa_metadata(guide, index.version)
        current = existing.get(title, [])
        same = [
            k for k in current
            if ((k.get("custom_metadata") or k.get("metadata") or {}).get("doc_version")) == index.version
        ]
        if same:
            report.skipped += 1
            continue
        for k in current:
            await client.delete_knowledge(k["id"])
            report.replaced += 1
        created = await client.create_manual_knowledge(kb["id"], title=title, content=qa_content(guide))
        await client.update_knowledge(created["id"], custom_metadata=meta)
        report.created += 1
    if prune:
        for title, items in existing.items():
            if title not in wanted:
                for k in items:
                    await client.delete_knowledge(k["id"])
                    report.deleted += 1
    report.docs["official_qa"] = index.version
    return kb


async def drop_legacy_kbs(client: WeKnoraClient) -> list[str]:
    """删除自造的中文手册 / FAQ / 合成工单库（2026-10-08 起只用官方 Q&A）。"""
    dropped = []
    for kb in await client.list_knowledge_bases():
        if kb.get("name") in LEGACY_KBS:
            await client.delete_knowledge_base(kb["id"])
            dropped.append(kb["name"])
    return dropped


def qa_manifest_chunking() -> dict[str, Any]:
    return {"chunk_size": QA_CHUNK, "parent_child": False, "unit": "one Q&A per knowledge", "dimension": EMBEDDING_DIM}
