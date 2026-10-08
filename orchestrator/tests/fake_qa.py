"""返回一条真实官方 Q&A 命中的假知识库适配器：单测不连 WeKnora，又需要「检索有结果 → 步骤卡」的路径时用。"""

from __future__ import annotations

from app.knowledge.adapter import Hit, KnowledgeScope, ToolResult
from app.official.qa_index import get_qa_index


class QAHitAdapter:
    def __init__(self, qa_id: str = "rv-0272"):
        self.qa_id = qa_id
        self.calls: list[tuple[str, str, KnowledgeScope]] = []

    async def hybrid_search(self, kb, query, top_k, allow):
        self.calls.append((kb, query, allow))
        guide = get_qa_index().guides[self.qa_id]
        hit = Hit(
            evidence_id=f"chunk-{self.qa_id}",
            knowledge_id=f"k-{self.qa_id}",
            chunk_id=f"chunk-{self.qa_id}",
            doc_id=self.qa_id,
            doc_version="test",
            source="kb_qa",
            snippet=guide.title,
            score=0.8,
        )
        return ToolResult("ok", [hit], kb=kb, query=query)
