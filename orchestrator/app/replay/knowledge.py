"""ReplayKnowledgeAdapter / RecordingKnowledgeAdapter（票 43，09 §4 四态之 replay）。

- 回放命中：status=replay（录制为 ok 时），hits 每条 status=replay → evidence.status=replay，前端显示「演示回放」；
  录制时是 no_match / unavailable 的结果原样重放（不用其他案例补）。
- 回放未命中：status=unavailable + 模型可读 hint，检索节点按既有 unavailable 路径处理。
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from app.knowledge.adapter import (
    HINTS,
    Hit,
    KbName,
    KnowledgeAdapter,
    KnowledgeScope,
    ToolResult,
)
from app.replay.package import Recorder, ReplayPackage, knowledge_key

log = logging.getLogger("replay.knowledge")

REPLAY_HINT = "演示回放数据（录制时的检索结果）。"
REPLAY_MISS_HINT = "回放包未收录此检索，知识库按不可用处理；按标准排障流程，不得用常识补假设。"


def _hit_record(h: Hit) -> dict[str, Any]:
    d = asdict(h)
    d.pop("status", None)
    return d


class ReplayKnowledgeAdapter:
    def __init__(self, package: ReplayPackage):
        self.package = package
        self.hits = 0
        self.misses: list[dict[str, Any]] = []

    @property
    def case_id(self) -> str:
        return self.package.case_id

    async def hybrid_search(
        self, kb: KbName, query: str, top_k: int, allow: KnowledgeScope
    ) -> ToolResult:
        key = knowledge_key(kb, query, allow, top_k)
        rec = self.package.knowledge.get(key)
        if rec is None:
            self.misses.append({"kb": kb, "key": key})
            log.warning("replay knowledge miss case=%s kb=%s key=%s", self.case_id, kb, key[:12])
            return ToolResult(
                "unavailable",
                hint=REPLAY_MISS_HINT,
                kb=kb,
                query=query,
                detail=f"replay_miss case={self.case_id}",
            )
        self.hits += 1
        status = str(rec.get("status") or "no_match")
        hits = [Hit(**{**h, "status": "replay"}) for h in rec.get("hits") or []]
        if status == "ok":
            status = "replay"
        return ToolResult(
            status,  # type: ignore[arg-type]
            hits,
            hint=REPLAY_HINT if status == "replay" else (rec.get("hint") or HINTS.get(status)),
            truncated=bool(rec.get("truncated")),
            kb=kb,
            query=query,
            allowed_count=int(rec.get("allowed_count") or 0),
            latency_ms=0,
            detail=f"replay case={self.case_id}",
        )


class RecordingKnowledgeAdapter:
    def __init__(self, inner: KnowledgeAdapter, recorder: Recorder):
        self.inner = inner
        self.recorder = recorder

    def __getattr__(self, name: str) -> Any:  # refresh_index / index_loaded_at 等透传
        return getattr(self.inner, name)

    async def hybrid_search(
        self, kb: KbName, query: str, top_k: int, allow: KnowledgeScope
    ) -> ToolResult:
        res = await self.inner.hybrid_search(kb, query, top_k, allow)
        if res.status == "unavailable":
            self.recorder.misses.append({"kb": kb, "mode": "knowledge", "reason": res.detail})
            return res  # 录制阶段的故障不入包：回放时未命中即同样 unavailable
        self.recorder.add_knowledge(
            knowledge_key(kb, query, allow, top_k),
            {
                "kb": kb,
                "status": res.status,
                "hits": [_hit_record(h) for h in res.hits],
                "hint": res.hint,
                "truncated": res.truncated,
                "allowed_count": res.allowed_count,
                "scope": {
                    "product_state": allow.product_state,
                    "category": allow.category,
                    "sku": allow.sku,
                },
                "query": query,
                "top_k": top_k,
            },
        )
        return res
