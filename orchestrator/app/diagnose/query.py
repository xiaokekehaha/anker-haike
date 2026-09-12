"""查询规范化（03 §1.4.1）：纯函数，无模型调用。

1. confirmed_sku 只取已确认产品名 / 型号；category_only 只取品类名，不拼候选型号；unknown 不构造（返回空）。
2. 产品 + 有效症状固定顺序拼接，去重、清理空白；保留否定、部件、错误码，不猜型号 / 原因。
3. 症状为空（抽取失败）→ 产品 + 当前原文回退；原文也为空 → 空串（调用方按「无可查内容」处理）。
"""

from __future__ import annotations

import re
from typing import Any

_WS = re.compile(r"[\s　]+")
_PUNCT_EDGE = re.compile(r"^[，。！？、,.!?;；:：\-—]+|[，。！？、,.!?;；:：\-—]+$")
CATEGORY_LABELS = {
    "robot_vacuum": "扫地机器人",
    "breast_pump": "吸奶器",
    "power_bank": "移动电源",
    "charger": "充电器",
    "earbuds": "耳机",
    "security_cam": "摄像头",
}


def normalize_query(text: str) -> str:
    """比较 / 去重用的规范化：折叠空白、去首尾标点、小写。"""
    return _WS.sub(" ", text).strip().casefold()


def _clean_part(s: str) -> str:
    s = _WS.sub(" ", s).strip()
    return _PUNCT_EDGE.sub("", s).strip()


def dedupe(parts: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for p in parts:
        c = _clean_part(p)
        if not c:
            continue
        key = normalize_query(c).replace(" ", "")
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def product_term(state: dict[str, Any]) -> str:
    ps = state.get("product_state")
    if ps == "confirmed_sku":
        product = state.get("product_confirmed") or {}
        return _clean_part(product.get("name") or product.get("sku") or "")
    if ps == "category_only":
        cat = (
            state.get("category")
            or (state.get("product_confirmed") or {}).get("category")
            or "robot_vacuum"
        )
        return CATEGORY_LABELS.get(cat, cat)
    return ""


def build_query(state: dict[str, Any]) -> str:
    """一个 query，同时用于说明书库与工单库；unknown 或无内容时返回空串。"""
    ps = state.get("product_state")
    if ps not in ("confirmed_sku", "category_only"):
        return ""
    product = product_term(state)
    symptoms = dedupe([str(s) for s in (state.get("symptoms") or [])])
    if not symptoms:
        raw = _clean_part(str(state.get("text") or ""))
        symptoms = [raw] if raw else []
    if not symptoms:
        return ""
    return " ".join(dedupe([product, *symptoms]))
