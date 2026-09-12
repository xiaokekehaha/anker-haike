"""KnowledgeAdapter（票 27，09 §2.3 / §2.4 / §4；07 §14；03 §2.3）。

IV-1 核对结论（2026-09-12，WeKnora v0.8.0 本机实测，见 findings）：
- `POST /knowledge-search` 忽略 `knowledge_ids`（传不存在的 id 仍返回全部命中）→ 不用。
- `POST /knowledge-bases/{id}/hybrid-search` 遵守 `knowledge_ids`；但空列表等于不过滤 → 允许集合为空时必须在本地直接 no_match。
- 命中带 `knowledge_custom_metadata`（YAML 文本）、`parent_chunk_id`、`match_type`；适配器再按 knowledge_id 后过滤一次兜底，match_count 放大 3 倍。

四态：ok / no_match / unavailable（/ replay 由票 43 的 ReplayKnowledgeAdapter 提供）。hint 面向模型可读。
单次返回 ≤ 2k token（按 2000 字符近似），超出取前若干命中并标 truncated。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import httpx
import yaml

from app.knowledge.ingest import KB_MANUAL, KB_TICKETS, sku_list_of
from app.knowledge.weknora_client import WeKnoraClient, WeKnoraError

log = logging.getLogger("knowledge.adapter")

ProductState = Literal["confirmed_sku", "category_only", "unknown"]
Status = Literal["ok", "no_match", "unavailable", "replay"]
KbName = Literal["kb_manual", "kb_tickets"]

MAX_CHARS = 2000  # ≈ 2k token（中文近似 1 字 1 token）
SNIPPET_CHARS = 400
HINTS = {
    "no_match": "当前产品范围内没有匹配内容；若有适用的预写排障计划请按计划默认顺序执行，否则升级（R5）。",
    "no_match_empty_scope": "当前产品状态下没有任何允许检索的知识（允许集合为空），未发起检索；按标准排障流程或升级（R5）。",
    "unavailable": "知识库暂不可用（WeKnora 不可达或超时）；按标准排障流程，不得用常识补假设。",
}


@dataclass(frozen=True)
class KnowledgeScope:
    product_state: ProductState
    category: str
    sku: str | None = None


@dataclass(frozen=True)
class IndexEntry:
    knowledge_id: str
    kb: KbName
    doc_id: str
    title: str
    scope: str  # sku | category_generic
    sku_list: tuple[str, ...]
    category: str
    doc_version: str
    result: str | None = None  # 工单：solved / unsolved / escalated


@dataclass
class Hit:
    evidence_id: str
    knowledge_id: str
    chunk_id: str
    doc_id: str
    doc_version: str
    source: str
    snippet: str
    score: float
    counter_evidence: bool = False
    knowledge_title: str | None = None
    parent_chunk_id: str | None = None
    status: Literal["ok", "replay"] = "ok"  # 票 43：回放命中的证据标 replay

    def as_evidence_item(self) -> dict[str, Any]:
        """契约 evidence.items[] 形状（status：真实检索 ok，回放命中 replay）。"""
        return {
            "evidence_id": self.evidence_id,
            "source": self.source,
            "doc_id": self.doc_id,
            "doc_version": self.doc_version,
            "chunk_id": self.chunk_id,
            "snippet": self.snippet,
            "score": max(0.0, min(1.0, self.score)),
            "status": self.status,
        }


@dataclass
class ToolResult:
    status: Status
    hits: list[Hit] = field(default_factory=list)
    hint: str | None = None
    truncated: bool = False
    kb: str | None = None
    query: str | None = None
    allowed_count: int = 0
    latency_ms: int = 0
    detail: str | None = None

    def for_model(self) -> dict[str, Any]:
        """给模型看的紧凑形状（07 §14：错误面向模型可读，不暴露 HTTP 细节）。"""
        out: dict[str, Any] = {"status": self.status}
        if self.hint:
            out["hint"] = self.hint
        if self.hits:
            out["hits"] = [
                {
                    "evidence_id": h.evidence_id,
                    "snippet": h.snippet,
                    "score": round(h.score, 3),
                    **({"counter_evidence": True} if h.counter_evidence else {}),
                }
                for h in self.hits
            ]
        if self.truncated:
            out["truncated"] = True
        return out


class KnowledgeAdapter(Protocol):
    async def hybrid_search(
        self, kb: KbName, query: str, top_k: int, allow: KnowledgeScope
    ) -> ToolResult: ...


def parse_custom_metadata(raw: Any) -> dict[str, Any]:
    """WeKnora 列表接口给 dict，hybrid-search 命中里的 knowledge_custom_metadata 是 YAML 文本。"""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        data = yaml.safe_load(str(raw))
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def entry_from_knowledge(kb: KbName, k: dict[str, Any]) -> IndexEntry | None:
    meta = parse_custom_metadata(k.get("custom_metadata") or k.get("metadata"))
    if not meta or "scope" not in meta:
        return None
    return IndexEntry(
        knowledge_id=k["id"],
        kb=kb,
        doc_id=str(meta.get("doc_id") or k.get("title") or k["id"]),
        title=k.get("title") or "",
        scope=str(meta["scope"]),
        sku_list=tuple(sku_list_of(meta)),
        category=str(meta.get("category") or ""),
        doc_version=str(meta.get("doc_version") or ""),
        result=meta.get("result"),
    )


def allowed_entries(entries: list[IndexEntry], allow: KnowledgeScope) -> list[IndexEntry]:
    """09 §2.3：confirmed_sku → sku_list ∋ sku ∪ category_generic∧category；category_only → 仅 category_generic∧category；unknown → 空。"""
    if allow.product_state == "unknown":
        return []
    out = []
    for e in entries:
        generic_ok = e.scope == "category_generic" and e.category == allow.category
        sku_ok = (
            allow.product_state == "confirmed_sku"
            and e.scope == "sku"
            and allow.sku is not None
            and allow.sku in e.sku_list
            and e.category == allow.category
        )
        if generic_ok or sku_ok:
            out.append(e)
    return out


class WeKnoraKnowledgeAdapter:
    def __init__(
        self,
        client: WeKnoraClient,
        kb_ids: dict[str, str],
        *,
        max_chars: int = MAX_CHARS,
        snippet_chars: int = SNIPPET_CHARS,
    ):
        self.client = client
        self.kb_ids = {k: v for k, v in kb_ids.items() if k in (KB_ALIASES)}
        self.max_chars = max_chars
        self.snippet_chars = snippet_chars
        self.index: dict[KbName, list[IndexEntry]] = {"kb_manual": [], "kb_tickets": []}
        self.index_loaded_at: float | None = None

    # ---- 索引 ----
    async def refresh_index(self) -> dict[str, int]:
        """启动时拉取全部 knowledge 元数据，按 (scope, sku_list, category) 建索引；知识入库后需重刷。"""
        counts: dict[str, int] = {}
        for kb in ("kb_manual", "kb_tickets"):
            kb_id = self.kb_ids.get(kb)
            if not kb_id:
                continue
            entries = []
            for k in await self.client.list_knowledge(kb_id):
                e = entry_from_knowledge(kb, k)  # type: ignore[arg-type]
                if e is not None and k.get("parse_status", "completed") == "completed":
                    entries.append(e)
            self.index[kb] = entries  # type: ignore[index]
            counts[kb] = len(entries)
        self.index_loaded_at = time.time()
        log.info("knowledge index refreshed %s", counts)
        return counts

    def allowed_ids(self, kb: KbName, allow: KnowledgeScope) -> list[str]:
        return [e.knowledge_id for e in allowed_entries(self.index[kb], allow)]

    # ---- 检索 ----
    async def hybrid_search(
        self, kb: KbName, query: str, top_k: int, allow: KnowledgeScope
    ) -> ToolResult:
        start = time.perf_counter()
        kb_id = self.kb_ids.get(kb)
        if not kb_id:
            return ToolResult(
                "unavailable",
                hint=HINTS["unavailable"],
                kb=kb,
                query=query,
                detail=f"{kb} not configured",
            )
        allowed = {e.knowledge_id: e for e in allowed_entries(self.index[kb], allow)}
        if not allowed:
            # 允许集合为空：不发请求（hybrid-search 的空 knowledge_ids 等于不过滤，禁止退化为整库搜索）
            return ToolResult(
                "no_match", hint=HINTS["no_match_empty_scope"], kb=kb, query=query, allowed_count=0
            )
        try:
            raw = await self.client.hybrid_search(
                kb_id, query, match_count=max(top_k * 3, top_k), knowledge_ids=list(allowed)
            )
        except (httpx.TransportError, TimeoutError) as exc:
            return self._unavailable(kb, query, len(allowed), start, f"{type(exc).__name__}: {exc}")
        except WeKnoraError as exc:
            if exc.status >= 500 or exc.status in (401, 403, 404):
                return self._unavailable(kb, query, len(allowed), start, str(exc))
            raise
        hits: list[Hit] = []
        for r in raw:
            kid = r.get("knowledge_id")
            if kid not in allowed:  # 后过滤兜底（IV-1）
                continue
            entry = allowed[kid]
            meta = parse_custom_metadata(r.get("knowledge_custom_metadata"))
            chunk_id = str(r.get("id"))
            snippet = (r.get("content") or "").strip()
            hits.append(
                Hit(
                    evidence_id=chunk_id,
                    knowledge_id=kid,
                    chunk_id=chunk_id,
                    doc_id=str(meta.get("doc_id") or entry.doc_id),
                    doc_version=str(meta.get("doc_version") or entry.doc_version),
                    source=kb,
                    snippet=snippet[: self.snippet_chars],
                    score=float(r.get("score") or 0.0),
                    counter_evidence=bool(
                        kb == "kb_tickets"
                        and (meta.get("result") or entry.result) not in (None, "solved")
                    ),
                    knowledge_title=r.get("knowledge_title") or entry.title,
                    parent_chunk_id=r.get("parent_chunk_id") or None,
                )
            )
        hits.sort(key=lambda h: (h.counter_evidence, -h.score))
        hits = hits[:top_k]
        ms = int((time.perf_counter() - start) * 1000)
        if not hits:
            return ToolResult(
                "no_match",
                hint=HINTS["no_match"],
                kb=kb,
                query=query,
                allowed_count=len(allowed),
                latency_ms=ms,
            )
        hits, truncated = self._truncate(hits)
        return ToolResult(
            "ok",
            hits,
            kb=kb,
            query=query,
            truncated=truncated,
            allowed_count=len(allowed),
            latency_ms=ms,
        )

    def _truncate(self, hits: list[Hit]) -> tuple[list[Hit], bool]:
        used = 0
        kept: list[Hit] = []
        for h in hits:
            if used + len(h.snippet) > self.max_chars:
                if not kept:  # 至少保留一条，截断其正文
                    h.snippet = h.snippet[: max(0, self.max_chars - used)]
                    kept.append(h)
                return kept, True
            used += len(h.snippet)
            kept.append(h)
        return kept, False

    def _unavailable(
        self, kb: str, query: str, allowed: int, start: float, detail: str
    ) -> ToolResult:
        log.warning("knowledge unavailable kb=%s detail=%s", kb, detail[:200])
        return ToolResult(
            "unavailable",
            hint=HINTS["unavailable"],
            kb=kb,
            query=query,
            allowed_count=allowed,
            latency_ms=int((time.perf_counter() - start) * 1000),
            detail=detail[:300],
        )


KB_ALIASES = {"kb_manual", "kb_tickets", "kb_faq", KB_MANUAL, KB_TICKETS}
