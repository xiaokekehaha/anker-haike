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
        ],
        "expect": ["step_card", "receipt_card", "escalation_summary", "done"],
    },
}
