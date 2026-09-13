"""本地 FAQ 索引（阶段 3，design.md §14）。

WeKnora v0.8.0 实测：FAQ 条目导入成功、KB 状态 available，但 faq/search、hybrid-search、knowledge-search 对 FAQ 库
全部返回空。FAQ 只有 50 条、全部 category_generic，故在适配器侧用源文件 faq_rv.yaml 做确定性匹配：
字符二元组 Dice 相似度 + 子串加分，阈值以下不返回（避免「无知识」样例泄漏）。命中形状与 WeKnora 命中一致（Hit），
source=kb_faq，doc_id=faq_rv，chunk_id=faq_rv#q7。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.diagnose.query import normalize_query
from app.knowledge.adapter import HINTS, Hit, KnowledgeScope, ToolResult

log = logging.getLogger("knowledge.faq")

_STRIP = re.compile(r"[\s　，。！？、,.!?;；:：\-—「」『』（）()《》\"']+")
_SKU_TOKEN = re.compile(r"\b[A-Z]{2,}(?:-[A-Z0-9]+)+\b|\beufy\b", re.IGNORECASE)
_GENERIC = (
    "扫地机器人",
    "扫地机",
    "机器人",
    "机器",
    "怎么办",
    "怎么",
    "什么意思",
    "是什么",
    "了",
    "吗",
    "呢",
    "的",
)


@dataclass(frozen=True)
class FaqEntry:
    id: str
    question: str
    similar: tuple[str, ...]
    answer: str

    @property
    def surfaces(self) -> tuple[str, ...]:
        return (self.question, *self.similar)


def _clean(text: str) -> str:
    t = _STRIP.sub("", normalize_query(text))
    for g in _GENERIC:
        t = t.replace(g, "")
    return t


def _bigrams(t: str) -> set[str]:
    return {t[i : i + 2] for i in range(len(t) - 1)} if len(t) > 1 else ({t} if t else set())


def similarity(query: str, surface: str) -> float:
    """Dice(二元组) 加子串加分，范围 0–1。"""
    q, s = _clean(query), _clean(surface)
    if not q or not s:
        return 0.0
    if s in q or q in s:
        base = 0.85 + 0.15 * min(len(q), len(s)) / max(len(q), len(s))
        return round(base, 4)
    bq, bs = _bigrams(q), _bigrams(s)
    if not bq or not bs:
        return 0.0
    return round(2 * len(bq & bs) / (len(bq) + len(bs)), 4)


class LocalFaqIndex:
    def __init__(
        self,
        entries: list[FaqEntry],
        *,
        doc_id: str,
        doc_version: str,
        category: str,
        threshold: float = 0.3,
    ):
        self.entries = entries
        self.doc_id, self.doc_version, self.category = doc_id, doc_version, category
        self.threshold = threshold

    @classmethod
    def from_yaml(cls, path: str | Path, *, threshold: float = 0.3) -> LocalFaqIndex:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        entries = [
            FaqEntry(
                id=str(e["id"]),
                question=str(e["q"]),
                similar=tuple(str(s) for s in (e.get("similar") or [])),
                answer=str(e.get("a") or ""),
            )
            for e in data.get("entries") or []
        ]
        return cls(
            entries,
            doc_id=str(data.get("doc_id") or "faq_rv"),
            doc_version=str(data.get("doc_version") or ""),
            category=str(data.get("category") or "robot_vacuum"),
            threshold=threshold,
        )

    def allowed(self, scope: KnowledgeScope) -> bool:
        """FAQ 全部 category_generic：品类一致且产品状态不是 unknown 即可见（09 §2.3）。"""
        return scope.product_state in ("confirmed_sku", "category_only") and (
            scope.category == self.category
        )

    def search(self, query: str, top_k: int, scope: KnowledgeScope) -> ToolResult:
        if not self.allowed(scope):
            return ToolResult(
                "no_match", hint=HINTS["no_match_empty_scope"], kb="kb_faq", query=query
            )
        # build_query 把产品词放在最前（SKU 或名称）；FAQ 是品类通用问答，产品词只会稀释相似度
        q = _SKU_TOKEN.sub(" ", query)
        if scope.sku:
            q = q.replace(scope.sku, " ")
        scored: list[tuple[float, FaqEntry]] = []
        for e in self.entries:
            best = max(similarity(q, s) for s in e.surfaces)
            if best >= self.threshold:
                scored.append((best, e))
        scored.sort(key=lambda x: -x[0])
        hits = [
            Hit(
                evidence_id=f"{self.doc_id}#{e.id}",
                knowledge_id="local-faq",
                chunk_id=f"{self.doc_id}#{e.id}",
                doc_id=self.doc_id,
                doc_version=self.doc_version,
                source="kb_faq",
                snippet=f"问：{e.question}\n答：{e.answer}",
                score=score,
            )
            for score, e in scored[:top_k]
        ]
        if not hits:
            return ToolResult(
                "no_match",
                hint=HINTS["no_match"],
                kb="kb_faq",
                query=query,
                allowed_count=len(self.entries),
            )
        return ToolResult("ok", hits, kb="kb_faq", query=query, allowed_count=len(self.entries))


_index: LocalFaqIndex | None = None
_built = False


def set_faq_index(index: LocalFaqIndex | None) -> None:
    global _index, _built
    _index, _built = index, True


def get_faq_index() -> LocalFaqIndex | None:
    """进程级本地 FAQ 索引：从 data/knowledge/kb_manual/faq_rv.yaml 加载；文件缺失返回 None。"""
    global _index, _built
    if _built:
        return _index
    _built = True
    import os

    from app.settings import REPO_ROOT

    path = Path(
        os.environ.get("FAQ_SOURCE_PATH")
        or REPO_ROOT / "data" / "knowledge" / "kb_manual" / "faq_rv.yaml"
    )
    if not path.is_file():
        log.warning("local faq index disabled: %s missing", path)
        return None
    _index = LocalFaqIndex.from_yaml(path)
    log.info("local faq index loaded entries=%d", len(_index.entries))
    return _index


def faq_meta(index: LocalFaqIndex) -> dict[str, Any]:
    return {"doc_id": index.doc_id, "doc_version": index.doc_version, "entries": len(index.entries)}
