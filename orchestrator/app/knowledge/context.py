"""候选到模型证据的选择边界：来源/轮次平衡、正文预算及可追踪的排除原因。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from itertools import zip_longest

from app.knowledge.adapter import Hit, context_window

SOURCE_PRIORITY = {"kb_manual": 0, "kb_faq": 1, "fault_card": 2, "kb_tickets": 3}
OUTCOME_LABELS = {"solved": "，已解决工单", "unsolved": "，未解决工单", "unknown": "，结果未知工单"}


def _interleave(hits: list[Hit]) -> list[Hit]:
    groups: dict[tuple[int, str], list[Hit]] = defaultdict(list)
    for hit in hits:
        groups[(hit.round, hit.source)].append(hit)
    keys = sorted(groups, key=lambda key: (key[0], SOURCE_PRIORITY.get(key[1], 9), key[1]))
    return [hit for row in zip_longest(*(groups[key] for key in keys)) for hit in row if hit]


def select_hits(hits: list[Hit], max_items: int) -> list[Hit]:
    """保留库内排序，交错来源和轮次；补查新增证据保证获得位置，反证至少保留一个代表。

    轮次升序：首轮首条仍排最前（模型自上而下读），二轮代表靠 zip_longest 交错进前几位，
    不靠插到队首——补查 query 掺了改写或图片观察，不能假定它比首轮首条更相关。

    不比较跨库分值，不按一次 grade 的 irrelevant 判定删除证据。
    """
    unique: dict[str, Hit] = {}
    for hit in hits:
        if (hit.full_text or hit.content or hit.snippet).strip():
            unique.setdefault(hit.evidence_id, hit)
    positive = _interleave([hit for hit in unique.values() if not hit.counter_evidence])
    counter = _interleave([hit for hit in unique.values() if hit.counter_evidence])
    if not positive:
        return counter[:max_items]
    reserve = int(bool(counter) and max_items > 1)
    selected = positive[: max_items - reserve]
    return selected + counter[: max_items - len(selected)]


def evidence_text(item: Mapping[str, object]) -> str:
    if item.get("context_text") is not None:
        return str(item["context_text"])
    text = str(item.get("full_text") or item.get("content") or item.get("snippet") or "")
    return context_window(text, str(item.get("content") or item.get("snippet") or ""), 800)


def evidence_header(item: Mapping[str, object]) -> str:
    outcome = OUTCOME_LABELS.get(str(item.get("case_outcome") or ""), "")
    header = f"[{item['evidence_id']}] ({item.get('source')}{outcome})"
    if item.get("knowledge_title"):
        header += f" 标题：{str(item['knowledge_title'])[:120]}"
    if item.get("doc_version"):
        header += f" 版本：{str(item['doc_version'])[:80]}"
    if item.get("round"):
        header += f" 检索轮次：{item['round']}"
    return header + "\n"


def render_evidence(item: Mapping[str, object]) -> str:
    return evidence_header(item) + evidence_text(item)


@dataclass
class EvidenceSelection:
    hits: list[Hit] = field(default_factory=list)
    excluded: dict[str, str] = field(default_factory=dict)
    shortened_ids: list[str] = field(default_factory=list)
    chars: int = 0


def pack_hits(hits: list[Hit], *, max_items: int, max_chars: int, item_chars: int) -> EvidenceSelection:
    """限制完整证据块的字符数；先为各代表分配空间，长片段不能吃掉第二轮或其他来源。"""
    selected = select_hits(hits, max_items)
    selected_ids = {hit.evidence_id for hit in selected}
    result = EvidenceSelection(
        excluded={
            hit.evidence_id: "item_limit" if (hit.full_text or hit.content or hit.snippet).strip() else "empty_content"
            for hit in hits if hit.evidence_id not in selected_ids
        }
    )
    for index, hit in enumerate(selected):
        header = evidence_header(hit.as_internal_item())
        # 预留后续条目的标题与换行，再平均分配剩余正文空间。
        rest_headers = sum(len(evidence_header(h.as_internal_item())) + 1 for h in selected[index:])
        available = max_chars - result.chars - rest_headers
        allowance = min(item_chars, max(0, available // (len(selected) - index)))
        if allowance <= 0:
            result.excluded[hit.evidence_id] = "char_limit"
            continue
        text = hit.context_text if hit.context_text is not None else hit.full_text or hit.content or hit.snippet
        body = context_window(text, hit.content or hit.snippet, allowance)
        if not body.strip():
            result.excluded[hit.evidence_id] = "empty_content"
            continue
        result.hits.append(replace(hit, context_text=body))
        result.chars += len(header) + len(body) + 1
        if len(body) < len(text):
            result.shortened_ids.append(hit.evidence_id)
    return result
