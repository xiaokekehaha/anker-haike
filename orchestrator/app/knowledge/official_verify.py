"""官方资料批次的真实验收：逐条回读来源、完整切块、型号隔离与 Top-5 检索。"""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from app.knowledge.adapter import KnowledgeScope, WeKnoraKnowledgeAdapter
from app.knowledge.ingest import load_manual_docs
from app.knowledge.official import Collection, Source, Unit, load_collection
from app.knowledge.weknora_client import WeKnoraClient
from app.settings import REPO_ROOT, settings


def complete_unit(source: Source, unit: Unit, content: str) -> bool:
    """标题（含产品、锚点）与完整操作必须同在一个子块；仅忽略空白差异。"""
    expected = f"{source.product}：{unit.title}（{unit.id}）官方资料中文整理：{unit.summary}"
    return "".join(expected.split()) in "".join(content.split())


async def verify(
    client: WeKnoraClient, collection: Collection, kb_ids: dict[str, str], source_root: Path
) -> dict[str, object]:
    adapter = WeKnoraKnowledgeAdapter(client, kb_ids)
    index_counts = await adapter.refresh_index()
    kb = await client.get_knowledge_base(kb_ids["kb_manual"])
    expected = {d.doc_id: d for d in load_manual_docs(source_root)}
    errors: list[str] = []
    documents = []
    retrieval = []
    for source in collection.sources:
        entries = [e for e in adapter.index["kb_manual"] if e.doc_id == source.id]
        if len(entries) != 1:
            errors.append(f"{source.id}: parsed index has {len(entries)} matching documents")
            continue
        entry = entries[0]
        full = await client.get_knowledge(entry.knowledge_id)
        metadata = full.get("custom_metadata") or {}
        mismatches = [
            key for key, value in expected[source.id].metadata.items() if metadata.get(key) != value
        ]
        if mismatches:
            errors.append(f"{source.id}: metadata mismatch {mismatches}")
        chunks = await client.list_chunks(entry.knowledge_id)
        split = [
            unit.id
            for unit in source.units
            if not any(complete_unit(source, unit, c.get("content") or "") for c in chunks)
        ]
        if split:
            errors.append(f"{source.id}: incomplete semantic units {split}")
        scopes_ok = all(
            entry.knowledge_id
            in adapter.allowed_ids(
                "kb_manual", KnowledgeScope("confirmed_sku", source.category, sku)
            )
            for sku in source.sku_list
        )
        scopes_ok = scopes_ok and all(
            entry.knowledge_id not in adapter.allowed_ids("kb_manual", scope)
            for scope in (
                KnowledgeScope("category_only", source.category),
                KnowledgeScope("unknown", source.category),
                KnowledgeScope("confirmed_sku", source.category, "UNRELATED-SKU"),
                KnowledgeScope("confirmed_sku", "UNRELATED-CATEGORY", source.sku_list[0]),
            )
        )
        if not scopes_ok:
            errors.append(f"{source.id}: scope isolation failed")
        documents.append(
            {
                "doc_id": source.id,
                "knowledge_id": entry.knowledge_id,
                "source_url": source.url,
                "doc_version": entry.doc_version,
                "parse_status": full.get("parse_status"),
                "metadata_mismatches": mismatches,
                "scope_isolation_ok": scopes_ok,
                "units": len(source.units),
                "incomplete_units": split,
                "chunks": len(chunks),
                "chunk_lengths": [len(c.get("content") or "") for c in chunks],
                "chunks_with_parent": sum(bool(c.get("parent_chunk_id")) for c in chunks),
            }
        )
        scope = KnowledgeScope("confirmed_sku", source.category, source.sku_list[0])
        for unit in source.units:
            result = await adapter.hybrid_search("kb_manual", unit.query, 5, scope)
            rank = next(
                (
                    i
                    for i, h in enumerate(result.hits, 1)
                    if h.doc_id == source.id and complete_unit(source, unit, h.snippet)
                ),
                None,
            )
            retrieval.append(
                {
                    "doc_id": source.id,
                    "unit": unit.id,
                    "query": unit.query,
                    "sku": scope.sku,
                    "status": result.status,
                    "hit_rank": rank,
                    "returned_docs": [h.doc_id for h in result.hits],
                }
            )
            if rank is None:
                errors.append(f"{source.id}/{unit.id}: full unit not retrieved in Top-5")
        print(f"verified {source.id}: {len(chunks)} chunks, {len(source.units)} units", flush=True)
    return {
        "batch_id": collection.batch_id,
        "checked_at": datetime.now(UTC).isoformat(),
        "index_counts": index_counts,
        "chunking_config": kb.get("chunking_config"),
        "documents": documents,
        "retrieval": retrieval,
        "errors": errors,
        "summary": {
            "documents": len(documents),
            "units": sum(len(s.units) for s in collection.sources),
            "queries": len(retrieval),
            "top5_passed": sum(r["hit_rank"] is not None for r in retrieval),
            "errors": len(errors),
        },
    }


async def main() -> int:
    collection = load_collection()
    manifest = json.loads(Path(settings.kb_manifest_path).read_text(encoding="utf-8"))
    async with WeKnoraClient(settings.weknora_base_url, settings.weknora_api_key) as client:
        report = await verify(
            client, collection, manifest["knowledge_bases"], REPO_ROOT / "data/knowledge"
        )
    path = REPO_ROOT / "reports/knowledge" / f"{collection.batch_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    print(f"report: {path}")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
