"""换货 / 退款 / 补发 / 承运商调查需要的 SOP 证据（主办方：订单/购买凭证、发货地址、视频/图片证明、产品 SN）。

证据只从可追溯来源取：已核实订单或凭证、本会话上传的图片、客户本人说过并带原话的事实（service_context）。
"""

from __future__ import annotations

import re
from typing import Any

from app.official.message import parse_message

# 机身 SN：工单里出现过 AK7RCN1E15600379、AMP3AC0F14201072、T8D02P20262058EB 这类 8–20 位字母数字。
# 表单字段（Product SN: …）由首封解析取；这里补自由文本里的「serial number is …」。
# 只在同一行内找值：App 报告里 SN 留空时，下一行的「Probleemtype」不能被读成序列号（T13 / T18）。
SN_PATTERN = re.compile(
    r"(?:\bS/?N\b|serial(?:[ \t]*number)?|seriennummer|serienummer|product[-\s]?sn|numéro de série|número de serie)"
    r"[ \t]*(?:is[ \t]+)?[:：#]?[ \t]*([A-Z0-9]{8,20})\b",
    re.IGNORECASE,
)


def serial_from_text(text: str) -> str | None:
    if sn := parse_message(text or "").sn:
        return sn
    match = SN_PATTERN.search(text or "")
    if not match or not any(ch.isdigit() for ch in match.group(1)):
        return None
    return match.group(1).upper()


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
    # SOP 的「故障图片/视频」排除经读图确认为单据 / 界面截图的图（vision 的 content_kinds）。
    # 不能按 purpose 判定：purpose 记的是上传时机，客户在普通首问里传的订单截图同样是 fault，
    # 一张单据截图曾因此凑齐换货证据四件套。
    # 这里排除「确认不是」而不是只认「确认是」：读图没跑 / 失败时集合为空，退回按上传时机判定，
    # 视觉链故障不该把正常换货流程整个堵死。
    documents = set(state.get("document_image_ids") or [])
    photos = [
        r["image_id"]
        for r in state.get("image_refs") or []
        if r.get("purpose") != "receipt" and r["image_id"] not in documents
    ]
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
