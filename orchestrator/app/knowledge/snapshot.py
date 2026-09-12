"""知识库快照：导出 = 源文件 + manifest + 远端知识清单；导入 = 从快照目录重新幂等导入并清理多余条目（回滚）。"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.knowledge.ingest import Ingestor, verify_metadata, write_manifest
from app.knowledge.weknora_client import WeKnoraClient


async def export_snapshot(
    client: WeKnoraClient, source_root: Path, manifest_path: Path, out_dir: Path
) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = out_dir / stamp
    target.mkdir(parents=True, exist_ok=False)
    for sub in ("kb_manual", "kb_tickets"):
        shutil.copytree(source_root / sub, target / sub)
    if manifest_path.is_file():
        shutil.copy(manifest_path, target / "manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        remote: dict[str, Any] = {}
        for name, kb_id in (manifest.get("knowledge_bases") or {}).items():
            if name == "kb_faq":
                remote[name] = {"faq_entries": len(await client.list_faq_entries(kb_id))}
            else:
                remote[name] = {"knowledge": await verify_metadata(client, kb_id)}
        (target / "remote.json").write_text(
            json.dumps(remote, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return target


async def import_snapshot(
    client: WeKnoraClient,
    snapshot_dir: Path,
    manifest_path: Path,
    *,
    embedding_model_id: str | None,
) -> dict[str, Any]:
    """用快照里的源文件重新导入；快照外的知识删除，使远端回到快照状态。"""
    ing = Ingestor(client, embedding_model_id=embedding_model_id)
    report = await ing.ingest_all(snapshot_dir, prune=True)
    return write_manifest(manifest_path, report, source_root=snapshot_dir)
