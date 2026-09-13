"""S0 确定性查询扩展（design.md §3.2）：只用 retrieval.yaml 已审核的同义词表，不调模型。

规则：query 中出现某组同义词（规范词或任一口语词）时，生成把该词替换为规范词的变体；多组命中时每组一个单点
替换变体，再加一个全部替换的变体；去重、去掉与原 query 相同者；最多 max_variants 个。变体不引入 query 里没有的
型号 / 错误码 / 数字（同义词表本身不含这些，这里再断言一次）。
"""

from __future__ import annotations

import re

from app.diagnose.query import normalize_query

_MODEL_OR_NUMBER = re.compile(r"[A-Za-z]{1,6}\s?-?\d{1,4}[A-Za-z]{0,4}|\d+(?:\.\d+)?")

# 语音提示 / 灯态 / 部件名：命中即走精确路径（design.md §14：本期语料无数字错误码）
PRECISE_TOKENS = (
    "请检查尘盒",
    "请检查滚刷",
    "红灯常亮",
    "红灯闪烁",
    "电池鼓包",
)


def _hits(query: str, synonyms: dict[str, list[str]]) -> list[tuple[str, str]]:
    """返回 (原文中出现的词, 规范词)，只取需要替换的（原文词 ≠ 规范词）。长词优先，避免「扫地机」吃掉「扫地机器人」。"""
    out: list[tuple[str, str]] = []
    for base, alts in synonyms.items():
        # 单字同义词（如「扫」「跑」）会命中任意含该字的词（「扫地机器人」→「清扫地机器人」），只用于 rewrite 校验，不用于扩展
        found = [
            w
            for w in sorted(alts, key=len, reverse=True)
            if len(w) >= 2 and w in query and w != base
        ]
        if found and base not in query:
            out.append((found[0], base))
    return out


def expand_queries(query: str, synonyms: dict[str, list[str]], max_variants: int) -> list[str]:
    """返回变体列表（不含原 query），已去重、有上限。"""
    if not query or max_variants <= 0 or not synonyms:
        return []
    hits = _hits(query, synonyms)
    if not hits:
        return []
    candidates: list[str] = []
    for word, base in hits:
        candidates.append(query.replace(word, base))
    if len(hits) > 1:
        full = query
        for word, base in hits:
            full = full.replace(word, base)
        candidates.append(full)
    seen = {normalize_query(query)}
    out: list[str] = []
    src_tokens = set(_MODEL_OR_NUMBER.findall(query))
    for cand in candidates:
        cand = " ".join(cand.split())
        key = normalize_query(cand)
        if key in seen:
            continue
        if set(_MODEL_OR_NUMBER.findall(cand)) - src_tokens:  # 不该发生：同义词表引入了型号 / 数字
            continue
        seen.add(key)
        out.append(cand)
        if len(out) >= max_variants:
            break
    return out


def precise_tokens_in(text: str) -> list[str]:
    return [t for t in PRECISE_TOKENS if t in text]
