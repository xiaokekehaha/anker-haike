"""A1–A3 演示脚本（票 43）：录制与回放校验共用同一份步骤，保证键一致。

步骤类型：
- {"message": 文本, "purpose"?: fault|receipt, "image"?: 内置图片名}
- {"action": kind, "payload": {...}, "until"?: pending_kind, "max"?: n}
  action 从最近一次 awaiting_input 取 interrupt_id / card_id / version；带 until 时重复直到 pending 变为该种类（或耗尽 max）。
expect：回放校验时事件流必须出现的事件类型。
"""

from __future__ import annotations

import struct
import zlib
from typing import Any

# 1×1 白色 PNG，字节固定：凭证 OCR 键按图片 sha256 计算，录制与回放必须是同一张图
_RAW = b"\x00\xff\xff\xff"


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def demo_receipt_png() -> bytes:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(_RAW))
        + _chunk(b"IEND", b"")
    )


IMAGES: dict[str, bytes] = {"receipt_demo": demo_receipt_png()}

SCENARIOS: dict[str, dict[str, Any]] = {
    "a1_hair_wrap": {
        "title": "A1 排障成功：X9 Pro 不吸 → 滚刷缠发步骤 → 已解决",
        "steps": [
            {"message": "eufy X9 Pro 扫地机不吸了，滚刷缠了很多头发"},
            {"action": "step_feedback", "payload": {"feedback": "solved"}},
        ],
        "expect": ["tool_call", "step_card", "done"],
    },
    "a2_disambiguate": {
        "title": "A2 消歧：S1 Pro 同名 → 产品卡选择扫地机 → 步骤卡",
        "steps": [
            {"message": "我的 S1 Pro 不吸了"},
            {"action": "select_product", "payload": {"sku": "EUFY-S1-PRO"}},
            {"action": "step_feedback", "payload": {"feedback": "solved"}},
        ],
        "expect": ["product_card", "step_card", "done"],
    },
    "a3_receipt_channel": {
        "title": "A3 升级：多步未解决 → 凭证收集 → 字段确认 → 渠道在名录 → 转人工摘要",
        "steps": [
            {"message": "eufy X10 Pro 扫地机不吸了，滚刷缠了很多头发"},
            {
                "action": "step_feedback",
                "payload": {"feedback": "not_solved"},
                "until": "upload_receipt",
                "max": 8,
            },
            {"message": "订单截图", "purpose": "receipt", "image": "receipt_demo"},
            {
                "action": "confirm_receipt",
                "payload": {
                    "fields": {
                        "order_no": "20260315-DEMO-9999",
                        "channel": "海科演示授权经销商",
                        "purchase_date": "2026-03-15",
                        "amount": None,
                    },
                    "edited": ["order_no", "channel", "purchase_date"],
                },
            },
            {"action": "request_human", "payload": {}},
        ],
        "expect": ["step_card", "receipt_card", "escalation_summary", "done"],
    },
    "a4_logistics": {
        "title": "A4 物流查询：一轮完成并展示来源",
        "knowledge": False,
        "steps": [{"message": "我的换货单 DEMO-X10-001 到哪了"}],
        "expect": ["tool_call", "message", "done"],
        "tools": ["logistics.query"],
    },
    "a5_replacement": {
        "title": "A5 自主换货：排障未解决 → 政策方案 → 执行回执 → 收货结案",
        "steps": [
            {"message": "eufy X10 Pro 扫地机不吸了，滚刷缠了很多头发，订单 DEMO-CN-003"},
            {
                "action": "step_feedback",
                "payload": {"feedback": "not_solved"},
                "until": "confirm_context",
                "max": 8,
            },
            {"action": "confirm_context", "payload": {"region_use": "CN"}},
            {"action": "confirm_proposal", "payload": {"option_id": "replace"}},
            {"backend_status": "shipped"},
            {"message": "收到换货了，确认已收到"},
            {"action": "rate_satisfaction", "payload": {"score": 5}},
        ],
        "expect": ["step_card", "proposal_card", "execution_card", "case_changed", "rating_card"],
        "tools": ["replacement.create"],
        "final_case_status": "closed",
    },
    "a6_human_approval": {
        "title": "A6 跨境审核：UK 购买 DE 使用 → 人工审批 → 服务单回执",
        "steps": [
            {"message": "eufy X10 Pro 扫地机不吸了，滚刷缠了很多头发，订单 DEMO-UK-005"},
            {
                "action": "step_feedback",
                "payload": {"feedback": "not_solved"},
                "until": "confirm_context",
                "max": 8,
            },
            {"message": "修不好了，我要换货"},
            {"action": "confirm_context", "payload": {"region_use": "DE"}},
            {
                "admin_decision": {
                    "decision": "approve",
                    "option_id": "replace",
                    "override_reason": "跨区域演示审核，同意为此订单换货",
                    "note": "已核实订单、故障及用户换货诉求",
                }
            },
        ],
        "expect": ["case_changed", "execution_card"],
        "tools": ["replacement.create"],
        "final_case_status": "tracking",
    },
    "a7_multi_intent": {
        "title": "A7 多诉求：先排障，再自动查询物流",
        "steps": [
            {
                "message": "eufy X10 Pro 扫地机不吸了，滚刷缠了头发。另外查一下订单 DEMO-X10-001 的物流"
            },
            {"action": "step_feedback", "payload": {"feedback": "solved"}},
        ],
        "expect": ["step_card", "tool_call", "message", "done"],
        "tools": ["logistics.query"],
    },
    "a8_emotion": {
        "title": "A8 情绪接续：不满 → 愤怒 → 投诉风险与人工审核",
        "steps": [
            {
                "message": "eufy X10 Pro 不吸了，滚刷缠了头发，订单 DEMO-CN-003。我对这个体验很不满意"
            },
            {"message": "一直没解决，真是气死我了"},
            {"message": "再不解决我就去平台投诉"},
            {"action": "confirm_context", "payload": {"region_use": "CN"}},
            {"action": "decline_proposal", "payload": {"reason": "request_human"}},
        ],
        "expect": ["context_card", "case_changed", "proposal_card"],
        "final_case_status": "awaiting_approval",
    },
    "a9_vision": {
        "title": "A9 看图定位与模糊图补拍",
        "steps": [
            {"message": "eufy X10 Pro 扫地机不吸了，请看滚刷底部照片", "image": "roller_clear.jpg"},
            {"message": "再看一下这张照片", "image": "roller_blur.jpg"},
            {"action": "skip_retake", "payload": {}},
        ],
        "expect": ["step_card", "retake_card", "done"],
    },
}
