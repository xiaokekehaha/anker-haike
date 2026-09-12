"""票 39：凭证收集 collect_receipt（09 §5.1；03 §1.7；05 §2）。

escalate 子流程入口按升级原因分流：
- 安全升级 R4、request_human R3，以及与凭证无关的 R5（无可用知识）/ R7（品类不明）/ R8（范围外）
  → 直接 summarize（receipt.status=not_collected）；
- 常规升级（排障失败 R1 / R1b / R1c / R2，退换 / 保修 R6）→ collect_receipt：awaiting_input(kind=upload_receipt)，
  用户在 Composer 以 purpose=receipt 上传凭证，或 skip_receipt{reason} 跳过。
- 跳过 → receipt.status=not_collected（skipped_reason 记录）→ summarize。
- 上传 → extract（票 40 OCR）→ confirm_fields → lookup；本票先以占位 receipt_extract 直达 summarize，
  status=needs_manual_check、next_step「凭证已收到，待人工核实」，票 40 / 41 替换。
- 在非 upload_receipt 位置上传的 purpose=receipt 图片不进入凭证流（走普通消息 / rediagnose，票 37）。

state.receipt = {status, image_ids, skipped_reason?, fields, confidence, edited, verified_facts, conflicts, next_step}
（02 §5）。摘要的 ReceiptOutcome 由 receipt_outcome() 从中派生。
"""

from __future__ import annotations

from typing import Any

from app.sessions.cards import derive_card_id

# 不收凭证直接摘要的升级原因：安全 / 人工请求 / 无可用知识（凭证无助于排障）/ 品类不明（无产品可核对）/ 范围外产品
DIRECT_SUMMARY_REASONS = frozenset({"R3", "R4", "R5", "R7", "R8"})
SKIP_REASONS = ("none", "unreadable", "later")

NEXT_STEP = {
    "not_collected": "请准备购买凭证，人工协助核实",
    "needs_manual_check": "凭证已收到，待人工核实",
    "insufficient": "请准备购买凭证，人工协助核实",
    "channel_unknown": "请准备购买凭证，人工协助核实",
    "order_verified": "资料已核实，转人工办理",
    "channel_in_directory": "经销商在名录内，人工确认购买凭证后办理",
    "order_product_mismatch": "凭证与当前设备信息不一致，需人工核实",
}


def receipt_card_id(session_id: str, reason: str) -> str:
    """凭证收集位置的卡片 / interrupt id：同一升级原因重跑得到同一 id。"""
    return derive_card_id(session_id, "collect_receipt", reason or "-")


def needs_collection(state: dict[str, Any]) -> bool:
    """常规升级且尚未收集 / 跳过凭证 → 进入 collect_receipt。"""
    reason = state.get("escalate_reason") or "R3"
    if reason in DIRECT_SUMMARY_REASONS:
        return False
    receipt = state.get("receipt") or {}
    return not receipt.get("status")


def has_uploaded(state: dict[str, Any]) -> bool:
    receipt = state.get("receipt") or {}
    return bool(receipt.get("image_ids")) and not receipt.get("status")


def empty_receipt() -> dict[str, Any]:
    return {
        "status": None,
        "image_ids": [],
        "fields": {},
        "confidence": {},
        "edited": [],
        "verified_facts": {},
        "conflicts": [],
        "next_step": None,
    }


def skipped_receipt(state: dict[str, Any], reason: str) -> dict[str, Any]:
    r = {**empty_receipt(), **(state.get("receipt") or {})}
    r.update(
        {
            "status": "not_collected",
            "skipped_reason": reason if reason in SKIP_REASONS else "none",
            "next_step": NEXT_STEP["not_collected"],
        }
    )
    return r


def uploaded_receipt(state: dict[str, Any], image_ids: list[str]) -> dict[str, Any]:
    """收到 purpose=receipt 的图片：记引用，status 留空交 extract。"""
    r = {**empty_receipt(), **(state.get("receipt") or {})}
    r["image_ids"] = [*r.get("image_ids", []), *image_ids]
    r["status"] = None
    return r


def extracted_placeholder(state: dict[str, Any]) -> dict[str, Any]:
    """票 40 之前的占位：已收到凭证但未做 OCR / 核对 → needs_manual_check。"""
    r = {**empty_receipt(), **(state.get("receipt") or {})}
    r.update({"status": "needs_manual_check", "next_step": NEXT_STEP["needs_manual_check"]})
    return r


def receipt_outcome(state: dict[str, Any], reason: str) -> dict[str, Any]:
    """摘要用 ReceiptOutcome 形状（09 §5.2：只有已核实事实与下一步，不含资格结论）。"""
    receipt = state.get("receipt") or {}
    status = receipt.get("status") or "not_collected"
    next_step = receipt.get("next_step") or (
        NEXT_STEP["not_collected"]
        if reason == "R6" or receipt.get("skipped_reason")
        else "已转人工，如需质保核实请补充购买凭证"
    )
    return {
        "status": status,
        "verified_facts": dict(receipt.get("verified_facts") or {}),
        "conflicts": list(receipt.get("conflicts") or []),
        "next_step": next_step,
    }


def receipt_refs_of_run(state: dict[str, Any]) -> list[str]:
    run_id = state.get("run_id", "")
    return [
        r["image_id"]
        for r in state.get("image_refs") or []
        if r.get("run_id") == run_id and r.get("purpose") == "receipt"
    ]
