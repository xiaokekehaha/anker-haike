"""证据锚点：plans.yaml 的 instruction_src 与知识库实际分块 / 检索命中的对应关系。

锚点（`manual_rv_v1#c12`）是人工写进语料的语义单元标记，比任何字符切分都准。所以这里
不再为「引用」切第三套块（对比外部方案的 512 字符 citation chunk，见
docs/claude/spec_grounded_citation_20260916.md §4），而是直接用锚点认出「真正支撑这一步
的那一条」证据。

三类锚点的认法不同，按可靠性排序：
- `faq_rv#q7`            FAQ 索引本来就按条目发命中，chunk_id 就是锚点，相等即可；
- `manual_rv_v1#c12`     标记「（c12）」由人写在小节标题里，落在命中正文中；
- `troubleshooting_rv#e1` 正文里没有任何标记，只能按 plans.yaml 那句已审核原文去认。

第三类说明锚点不是万能的：认不出时调用方必须退回本地发布，而不是硬挂一条。
"""

from __future__ import annotations

import re
from typing import Any, Literal

# 已审核原文取前若干字做包含匹配：太短会误命中相邻小节，太长会被 snippet 截断截掉
TEXT_PROBE_CHARS = 14

MatchKind = Literal["exact_chunk", "marker", "text", "none"]

_MANUAL_ANCHOR = re.compile(r"^c\d+$")


def anchor_marker(chunk_id: str) -> str | None:
    """锚点 → 正文里应当出现的标记。只有手册的 cNN 有人工标记，其余返回 None。"""
    return f"（{chunk_id}）" if _MANUAL_ANCHOR.match(chunk_id) else None


def _texts(item: dict[str, Any]) -> str:
    """一条证据可供匹配的全部文本。运行时只有 snippet，离线评测还带父块 full_text。"""
    return f"{item.get('snippet') or ''}\n{item.get('full_text') or ''}"


def match_anchor(
    evidence_key: str,
    source_text: str,
    evidence: dict[str, dict[str, Any]],
) -> tuple[str | None, MatchKind]:
    """在允许证据集合里找出锚点对应的那一条检索命中。

    evidence_key 形如 `manual_rv_v1#c12`（不带 `evidence:` 前缀），source_text 是
    plans.yaml 证据段里的已审核原文。返回 (evidence_id, 命中方式)；认不出返回 (None, "none")，
    调用方据此判断这段内容是否真的被检索到了。
    """
    doc_id, _, chunk_id = evidence_key.partition("#")
    same_doc = {eid: it for eid, it in evidence.items() if it.get("doc_id") == doc_id}
    if not same_doc:
        return None, "none"
    # 1. FAQ：命中的 chunk_id 就是完整锚点
    for eid, it in same_doc.items():
        if it.get("chunk_id") in (evidence_key, chunk_id):
            return eid, "exact_chunk"
    # 2. 手册：人工标记
    marker = anchor_marker(chunk_id)
    if marker:
        for eid, it in same_doc.items():
            if marker in _texts(it):
                return eid, "marker"
    # 3. 已审核原文（无标记的语料，或标记与正文被切到了不同块）
    probe = (source_text or "").strip()[:TEXT_PROBE_CHARS]
    if len(probe) >= 6:
        for eid, it in same_doc.items():
            if probe in _texts(it):
                return eid, "text"
    return None, "none"
