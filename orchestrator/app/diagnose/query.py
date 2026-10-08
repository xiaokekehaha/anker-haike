"""查询规范化（03 §1.4.1）：纯函数，无模型调用。

1. confirmed_sku 不拼产品名（检索范围已按 PN 锁定）；category_only 拼品类名，不拼候选型号；unknown 不构造（返回空）。
2. 有效症状去重、清理空白；保留否定、部件、错误码，不猜型号 / 原因。
3. 症状为空（抽取失败）→ 产品 + 当前原文回退（表单只取问题描述 / 推送，去链接）；原文也为空 → 空串。
"""

from __future__ import annotations

import re
from typing import Any

from app.conversation.taxonomy import families
from app.official.message import URLS, parse_message
from app.sessions.cards import get_catalog

_WS = re.compile(r"[\s　]+")
_PUNCT_EDGE = re.compile(r"^[，。！？、,.!?;；:：\-—]+|[，。！？、,.!?;；:：\-—]+$")


def category_label(category: str | None) -> str:
    """品类中文名只有一处真源：products.yaml 的 categories[].name。未登记的品类原样返回。"""
    spec = get_catalog().categories.get(category or "")
    return spec.name if spec else (category or "")


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
        return category_label(state.get("category") or (state.get("product_confirmed") or {}).get("category"))
    return ""


def build_query(state: dict[str, Any]) -> str:
    """一个 query，同时用于说明书库与工单库；unknown 或无内容时返回空串。"""
    ps = state.get("product_state")
    if ps not in ("confirmed_sku", "category_only"):
        return ""
    product = product_term(state)
    symptoms = dedupe([str(s) for s in (state.get("symptoms") or [])])
    if state.get("symptom_codes"):
        category = state.get("category") or (state.get("product_confirmed") or {}).get("category")
        labels = [f["fault_family"] for f in families(category) if f["symptom_code"] in state["symptom_codes"]]
        symptoms = dedupe([*labels, *symptoms])
    if not symptoms:
        # App 报错 / RMA 表单只取问题描述与推送提示：表头、订单字段和图片链接会冲淡检索（63 单评测 recall 4/13 → 7/13）
        text = str(state.get("text") or "")
        raw = _clean_part(parse_message(text).problem_text or URLS.sub(" ", text))
        symptoms = [raw] if raw else []
    if not symptoms:
        return ""
    if ps == "confirmed_sku":
        # 检索范围已按 PN 锁定，范围内每条 Q&A 标题都带型号名：再拼产品名只会给所有候选同样加分，冲淡现象词
        return " ".join(dedupe(symptoms))
    return " ".join(dedupe([product, *symptoms]))
