"""返回真实官方 Q&A 命中的假知识库适配器：单测不连 WeKnora，又需要「检索有结果 → 步骤卡」的路径时用。
多个 qa_id 时依次返回多条命中（候选指南不止一条的场景，如 T36 rv-0341 + rv-0316）。"""

from __future__ import annotations

from app.knowledge.adapter import Hit, KnowledgeScope, ToolResult
from app.official.qa_index import get_qa_index


class QAHitAdapter:
    def __init__(self, qa_id: str = "rv-0272", *more: str):
        self.qa_ids = (qa_id, *more)
        self.calls: list[tuple[str, str, KnowledgeScope]] = []

    async def hybrid_search(self, kb, query, top_k, allow):
        self.calls.append((kb, query, allow))
        hits = [
            Hit(
                evidence_id=f"chunk-{qa_id}",
                knowledge_id=f"k-{qa_id}",
                chunk_id=f"chunk-{qa_id}",
                doc_id=qa_id,
                doc_version="test",
                source="kb_qa",
                snippet=get_qa_index().guides[qa_id].title,
                score=0.8,
            )
            for qa_id in self.qa_ids
        ]
        return ToolResult("ok", hits, kb=kb, query=query)
