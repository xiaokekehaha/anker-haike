"""进程级 KnowledgeAdapter 取用（图节点用；测试可注入 FakeAdapter）。

真实适配器需要 WEKNORA_API_KEY 与 data/knowledge/manifest.json（知识库 id）；缺任一项则返回 None，
检索节点按 unavailable 处理（tool_call failed，流程继续）。索引在首次使用时拉取。
REPLAY_CASE_ID 设置时（票 43）返回 ReplayKnowledgeAdapter：按录制包命中，不连 WeKnora；未命中 → unavailable。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from app.knowledge.adapter import KnowledgeAdapter, WeKnoraKnowledgeAdapter
from app.knowledge.weknora_client import WeKnoraClient

log = logging.getLogger("knowledge.runtime")
_adapter: KnowledgeAdapter | None = None
_built = False


def set_knowledge_adapter(adapter: KnowledgeAdapter | None) -> None:
    global _adapter, _built
    _adapter = adapter
    _built = adapter is not None


def manifest_path() -> Path:
    from app.settings import settings

    return Path(settings.kb_manifest_path)


def get_knowledge_adapter() -> KnowledgeAdapter | None:
    global _adapter, _built
    if _built:
        return _adapter
    _built = True
    if os.environ.get("HAIKE_KNOWLEDGE", "on").lower() in ("off", "0", "false"):
        log.info("HAIKE_KNOWLEDGE=off: knowledge adapter disabled")
        return None
    from app.replay.runtime import get_replay_package
    from app.settings import settings

    pkg = get_replay_package()
    if pkg is not None:
        from app.replay.knowledge import ReplayKnowledgeAdapter

        _adapter = ReplayKnowledgeAdapter(pkg)
        log.info("REPLAY_CASE_ID=%s: ReplayKnowledgeAdapter in place of WeKnora", pkg.case_id)
        return _adapter
    mp = manifest_path()
    if not settings.weknora_api_key or not mp.is_file():
        log.warning(
            "knowledge adapter disabled: %s",
            "no WEKNORA_API_KEY" if not settings.weknora_api_key else "no manifest",
        )
        return None
    kb_ids = json.loads(mp.read_text(encoding="utf-8")).get("knowledge_bases")
    if not kb_ids:  # 票 43：replay/kb_manifest.json 只有 kb_ver 快照，不含知识库 id
        log.warning("knowledge adapter disabled: manifest %s has no knowledge_bases", mp)
        return None
    client = WeKnoraClient(settings.weknora_base_url, settings.weknora_api_key, timeout_s=8)
    _adapter = WeKnoraKnowledgeAdapter(client, kb_ids)
    return _adapter


async def ensure_index(adapter: KnowledgeAdapter) -> None:
    real = getattr(adapter, "inner", adapter)  # 票 43：录制包装器透传到真实适配器
    if isinstance(real, WeKnoraKnowledgeAdapter) and real.index_loaded_at is None:
        await real.refresh_index()
