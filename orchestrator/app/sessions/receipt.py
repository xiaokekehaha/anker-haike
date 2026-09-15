"""票 39：凭证收集 collect_receipt（09 §5.1；03 §1.7；05 §2）。

escalate 子流程入口按升级原因分流：
- 安全升级 R4、request_human R3，以及与凭证无关的 R5（无可用知识）/ R7（品类不明）/ R8（范围外）
  → 直接 summarize（receipt.status=not_collected）；
- 常规升级（排障失败 R1 / R1b / R1c / R2，退换 / 保修 R6）→ collect_receipt：awaiting_input(kind=upload_receipt)，
  用户在 Composer 以 purpose=receipt 上传凭证，或 skip_receipt{reason} 跳过。
- 跳过 → receipt.status=not_collected（skipped_reason 记录）→ summarize。
- 上传 → extract（票 40：warranty.receipt_ocr 视觉任务，internal，输出 fields / 逐字段 confidence / unreadable）
  → confirm_fields：receipt_card + awaiting_input(confirm_receipt)，用户确认 / 修改（edited[]）或 skip
  → lookup（票 41 L1–L6：订单与 SKU / 低置信 / 经销商名录核对）→ summarize。
  识别失败 / 无视觉模型：卡片字段为空、全部 unreadable，允许手输或跳过。
- 在非 upload_receipt 位置上传的 purpose=receipt 图片不进入凭证流（走普通消息 / rediagnose，票 37）。

state.receipt = {status, image_ids, skipped_reason?, fields, confidence, edited, verified_facts, conflicts, next_step}
（02 §5）。摘要的 ReceiptOutcome 由 receipt_outcome() 从中派生。
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from app.images.store import ImageStore
from app.models.queue import CapacityExceeded
from app.models.router import ModelInvokeError, ModelRouter
from app.prompts import compose_system_prompt, wrap_data
from app.sessions.cards import derive_card_id
from app.warranty.runtime import get_receipt_lookup

log = logging.getLogger("sessions.receipt")

OCR_TASK = "warranty.receipt_ocr"
OCR_BUDGET_MS = 12_000  # 凭证轮 run deadline 30 s（08 §8）
OCR_PROMPT_VERSION = "2026-09-12.1"
FIELDS = ("order_no", "channel", "purchase_date", "amount")
LOW_CONFIDENCE = 0.7  # 低于此值前端标黄（09 §5.3）

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


def confirm_card_id(session_id: str, image_ids: list[str]) -> str:
    """字段确认卡片 id：同一批凭证图重跑得到同一 id。"""
    return derive_card_id(session_id, "confirm_receipt", "|".join(image_ids) or "-")


# ---------------------------------------------------------------------------
# 票 40：OCR
# ---------------------------------------------------------------------------


class ReceiptOcr(BaseModel):
    """warranty.receipt_ocr 的模型输出 schema：只有字段与置信度，不含任何质保结论。"""

    model_config = ConfigDict(extra="forbid")

    order_no: str | None = Field(default=None, description="订单号 / 单号，原样抄录；看不清留空")
    channel: str | None = Field(default=None, description="购买渠道 / 店铺名，原样抄录")
    purchase_date: str | None = Field(
        default=None, description="购买或下单日期，YYYY-MM-DD；看不清留空"
    )
    amount: str | None = Field(default=None, description="实付金额，含货币符号原样抄录")
    confidence: dict[str, float] = Field(
        default_factory=dict,
        description="逐字段置信度 0-1，键为 order_no / channel / purchase_date / amount",
    )
    unreadable: list[str] = Field(default_factory=list, description="图片中看不清或不存在的字段名")


@dataclass
class OcrOutcome:
    status: str  # ok / failed / no_vision / skipped
    fields: dict[str, str | None] = field(default_factory=dict)
    confidence: dict[str, float] = field(default_factory=dict)
    unreadable: list[str] = field(default_factory=list)
    used_image_ids: list[str] = field(default_factory=list)
    model_used: str | None = None
    reason: str | None = None
    model_trace: dict[str, Any] | None = None


OCR_INSTRUCTION = (
    "你正在查看用户上传的购买凭证（订单截图 / 发票 / 收据）。只抄录图片中可见的订单号、购买渠道（店铺 / 平台）、"
    "购买日期、实付金额四个字段；看不清或不存在的字段留空并写入 unreadable；给每个字段 0-1 的置信度。"
    "不要判断是否在保、是否可退换，不要补全或猜测任何数字。只输出 JSON。"
)


def _image_limit(chain: list[Any]) -> int:
    """链上视觉模型的最小 max_images；都没配置时默认 4（与读图节点一致，独立实现避免跨模块耦合）。"""
    limits = [
        m.spec.max_images
        for m in chain
        if getattr(m.spec, "vision", False) and getattr(m.spec, "max_images", None)
    ]
    return min(limits) if limits else 4


def _select_latest(refs: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return list(refs) if limit <= 0 or len(refs) <= limit else list(refs[-limit:])


def _empty_ocr(status: str, reason: str | None, lane: str, attempts: int = 1) -> OcrOutcome:
    return OcrOutcome(
        status,
        fields=dict.fromkeys(FIELDS),
        confidence=dict.fromkeys(FIELDS, 0.0),
        unreadable=list(FIELDS),
        reason=reason,
        model_trace={"task": OCR_TASK, "model_used": "skipped", "lane": lane, "attempts": attempts},
    )


def build_ocr_messages(
    images: list[tuple[str, bytes]], *, summary: dict[str, Any] | None
) -> list[Any]:
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": f"{OCR_INSTRUCTION}\n{wrap_data('（购买凭证图片见附件）', kind='receipt_image')}",
        }
    ]
    for mime, data in images:
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
                },
            }
        )
    return [
        SystemMessage(content=compose_system_prompt("normal", summary)),
        HumanMessage(content=content),
    ]


async def extract_receipt(
    router: ModelRouter | None,
    store: ImageStore | None,
    *,
    session_id: str,
    image_ids: list[str],
    refs: list[dict[str, Any]],
    lane: str,
    summary: dict[str, Any] | None = None,
    budget_ms: int = OCR_BUDGET_MS,
) -> OcrOutcome:
    """凭证 OCR：失败 / 无视觉模型时返回空字段 + 全部 unreadable，卡片仍可手输（票 40）。"""
    if router is None or store is None:
        return _empty_ocr("skipped", "router or image store unavailable", lane)
    by_id = {r["image_id"]: r for r in refs}
    ordered = [by_id.get(i, {"image_id": i}) for i in image_ids]
    keep = _select_latest(ordered, _image_limit(router.registry.chain(OCR_TASK, lane)))
    images: list[tuple[str, bytes]] = []
    for r in keep:
        got = await store.get(session_id, r["image_id"])
        if got is not None:
            images.append((got[0].mime, got[1]))
    if not images:
        return _empty_ocr("failed", "receipt image bytes not found (expired?)", lane)
    try:
        res = await router.invoke(
            OCR_TASK,
            build_ocr_messages(images, summary=summary),
            ReceiptOcr,
            budget_ms=budget_ms,
            session_id=session_id,
            lane=lane,
        )
    except ModelInvokeError as exc:
        no_vision = bool(exc.attempts) and all(a.outcome == "skipped" for a in exc.attempts)
        log.warning(
            "receipt ocr degraded session=%s no_vision=%s reason=%s",
            session_id,
            no_vision,
            exc.reason,
        )
        return _empty_ocr(
            "no_vision" if no_vision else "failed",
            exc.reason[:200],
            lane,
            max(1, len(exc.attempts)),
        )
    except CapacityExceeded as exc:
        return _empty_ocr("failed", f"CapacityExceeded: {exc}"[:200], lane)
    parsed: ReceiptOcr = res.parsed
    fields = {k: (getattr(parsed, k) or None) for k in FIELDS}
    fields = {k: (v.strip() or None) if isinstance(v, str) else v for k, v in fields.items()}
    unreadable = sorted(
        {
            *(u for u in parsed.unreadable if u in FIELDS),
            *(k for k, v in fields.items() if v is None),
        }
    )
    confidence = {
        k: (0.0 if fields[k] is None else max(0.0, min(1.0, float(parsed.confidence.get(k, 0.5)))))
        for k in FIELDS
    }
    log.info(
        "receipt ocr session=%s fields=%s unreadable=%s model=%s prompt_ver=%s",
        session_id,
        {k: bool(v) for k, v in fields.items()},
        unreadable,
        res.model_used,
        OCR_PROMPT_VERSION,
    )
    return OcrOutcome(
        "ok",
        fields=fields,
        confidence=confidence,
        unreadable=unreadable,
        used_image_ids=[r["image_id"] for r in keep],
        model_used=res.model_used,
        model_trace={
            "task": OCR_TASK,
            "model_used": res.model_used,
            "lane": res.lane,
            "attempts": max(1, len(res.attempts)),
        },
    )


def extracted_receipt(state: dict[str, Any], ocr: OcrOutcome) -> dict[str, Any]:
    """OCR 结果写入 receipt（status 留空等待用户确认）。"""
    r = {**empty_receipt(), **(state.get("receipt") or {})}
    r.update(
        {
            "status": None,
            "fields": dict(ocr.fields),
            "confidence": dict(ocr.confidence),
            "unreadable": list(ocr.unreadable),
            "ocr_status": ocr.status,
        }
    )
    return r


def card_payload(receipt: dict[str, Any]) -> dict[str, Any]:
    """receipt_card 事件载荷（08 §5）：fields / confidence / unreadable，不含质保结论。"""
    return {
        "fields": {k: receipt.get("fields", {}).get(k) for k in FIELDS},
        "confidence": {
            k: float(v) for k, v in (receipt.get("confidence") or {}).items() if k in FIELDS
        },
        "unreadable": [u for u in receipt.get("unreadable") or [] if u in FIELDS],
    }


def confirmed_receipt(
    state: dict[str, Any], fields: dict[str, Any], edited: list[str]
) -> dict[str, Any]:
    """用户确认后按 L1–L6 核对。低置信字段只有实际修改才解除 L4 降级。"""
    r = {**empty_receipt(), **(state.get("receipt") or {})}
    clean = {
        k: ((fields.get(k) or None) if k in fields else r.get("fields", {}).get(k)) for k in FIELDS
    }
    clean = {k: (v.strip() or None) if isinstance(v, str) else v for k, v in clean.items()}
    previous = r.get("fields") or {}
    actual_edits = [
        e for e in dict.fromkeys(edited) if e in FIELDS and clean[e] != (previous.get(e) or None)
    ]
    r.update(
        {
            "fields": clean,
            "edited": actual_edits,
        }
    )
    outcome = get_receipt_lookup().lookup(r, state.get("product_confirmed"))
    r.update(outcome.model_dump(mode="json"))
    return r


def skipped_after_upload(state: dict[str, Any], reason: str) -> dict[str, Any]:
    """凭证已上传但用户在字段确认时跳过：图片仍可供人工核实。"""
    r = {**empty_receipt(), **(state.get("receipt") or {})}
    r.update(
        {
            "status": "needs_manual_check",
            "skipped_reason": reason if reason in SKIP_REASONS else "none",
            "next_step": NEXT_STEP["needs_manual_check"],
        }
    )
    return r


def diagnostic_only(state: dict[str, Any]) -> bool:
    """排障受阻本身不构成退换/保修申请，不以凭证收集阻塞摘要。"""
    return state.get("escalate_reason") in {"R1", "R1b", "R1c", "R2", "R5", "R7"} and not state.get("requested_remedy")


def needs_collection(state: dict[str, Any]) -> bool:
    """常规升级且尚未收集 / 跳过凭证 → 进入 collect_receipt。"""
    reason = state.get("escalate_reason") or "R3"
    if reason in DIRECT_SUMMARY_REASONS or diagnostic_only(state):
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
    r["image_ids"] = list(image_ids)
    r.update(fields={}, confidence={}, edited=[], verified_facts={}, conflicts=[], next_step=None)
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
        else "摘要已整理；如需质保核实，可向客服补充购买凭证"
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
