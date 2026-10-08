"""换货 / 退款 / 补发 / 承运商调查需要的 SOP 证据（主办方：订单/购买凭证、发货地址、视频/图片证明、产品 SN）。

证据只从可追溯来源取：已核实订单或凭证、本会话上传的图片、客户本人说过并带原话的事实（service_context）。
"""

from __future__ import annotations

import re
from typing import Any

# 机身 SN：工单里出现过 AK7RCN1E15600379、AMP3AC0F14201072、T8D02P20262058EB 这类 12–20 位大写字母数字。
SN_PATTERN = re.compile(
    r"(?:\bS/?N\b|serial(?:\s*number)?|seriennummer|serienummer|product[-\s]?sn|numéro de série|número de serie)"
    r"\s*[:：#]?\s*([A-Z0-9]{8,20})",
    re.IGNORECASE,
)


def serial_from_text(text: str) -> str | None:
    match = SN_PATTERN.search(text or "")
    return match.group(1).upper() if match else None


def collect(state: dict[str, Any]) -> dict[str, str]:
    """当前案件已具备的证据；值是可回溯的来源描述，不含推断。"""
    evidence: dict[str, str] = {}
    receipt = state.get("receipt") or {}
    facts = receipt.get("verified_facts") or {}
    stated = state.get("service_context") or {}
    if receipt.get("status") == "order_verified" and facts.get("order_no"):
        evidence["order_or_receipt"] = "order:" + facts["order_no"]
    elif receipt.get("status") in {"dealer_authorized", "needs_manual_check"} and receipt.get("image_ids"):
        evidence["order_or_receipt"] = "receipt:" + ",".join(receipt["image_ids"])
    if order_address := facts.get("address"):
        evidence["address"] = "order:" + order_address
    elif stated.get("address"):
        evidence["address"] = "customer:" + stated["address"]
    photos = [r["image_id"] for r in state.get("image_refs") or [] if r.get("purpose") != "receipt"]
    if photos:
        evidence["photo_or_video"] = "images:" + ",".join(photos)
    serial = stated.get("serial_number") or serial_from_text(state.get("text", "")) or next(
        (sn for sn in (serial_from_text(e.get("text", "")) for e in state.get("history") or []
                       if e.get("role") == "user" and e.get("issue_id") == state.get("active_issue_id")) if sn),
        None,
    )
    if serial:
        evidence["serial_number"] = "customer:" + serial
    return evidence
