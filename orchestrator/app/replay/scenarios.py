"""演示脚本（D6，2026-10-08 换成主办方真实工单）：录制与回放校验共用同一份步骤，保证键一致。

主线 T55（吸奶器：同名消歧 → 官方 Q&A 排障 → 保内 → 补证据 → 换货单），分支 T8（补发）、T2（送达不补发 →
承运商调查）、T29（过保委婉拒绝）、T45（经销商 + 烫伤 → 安全转人工）、T14（官方 Q&A 判硬件故障直进质保）、
T13（荷兰语，官方未收录错误码 → 转人工）。首封消息就是工单原文，附件是工单原图。

步骤类型：
- {"ticket": 工单号}：发送该工单原文与附件
- {"message": 文本, "purpose"?: fault|receipt, "image"?: 内置图片名}
- {"action": kind, "payload": {...}, "until"?: pending_kind, "while"?: pending_kind, "max"?: n, "optional"?: bool}
  action 从最近一次 awaiting_input 取 interrupt_id / card_id / version；带 until 时重复直到 pending 变为该种类，
  带 while 时只要 pending 仍是该种类就继续（最多 max 次）；optional 表示当前没有这个待办就跳过。
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
    "t55_main": {
        "title": "T55 主线：吸奶器 RMA → 官方 Q&A 排障未解决 → 订单保内 → 补照片与 SN → 换货单 → 转人工",
        "steps": [
            {"ticket": "T55"},
            {"action": "skip_retake", "payload": {}, "while": "upload_retake"},
            {"action": "step_feedback", "payload": {"feedback": "not_solved"}, "max": 12, "while": "step_feedback"},
            {"message": "SN: T8D04121ABCD0001"},
            {"action": "confirm_proposal", "payload": {"option_id": "replace"}},
        ],
        "expect": ["step_card", "proposal_card", "execution_card", "case_changed"],
        "tools": ["service_order.create"],
    },
    "t8_reship": {
        "title": "T8 物流：包裹退回发件人 → 补发单 → 转人工",
        "knowledge": False,
        "steps": [
            {"ticket": "T8"},
            {"action": "confirm_proposal", "payload": {"option_id": "reship"}},
        ],
        "expect": ["proposal_card", "execution_card", "case_changed"],
        "tools": ["logistics.query", "service_order.create"],
    },
    "t2_delivered": {
        "title": "T2 物流：两个包裹都显示送达 → 不补发，提交承运商调查单",
        "knowledge": False,
        "steps": [
            {"ticket": "T2"},
            {"action": "confirm_proposal", "payload": {"option_id": "carrier_investigation"}},
        ],
        "expect": ["proposal_card", "execution_card"],
        "tools": ["logistics.query", "service_order.create"],
    },
    "t29_out_of_warranty": {
        "title": "T29 过保：排障未解决 → 订单质保已过 → 委婉拒绝",
        "steps": [
            {"ticket": "T29"},
            {"action": "step_feedback", "payload": {"feedback": "not_solved"}, "max": 12, "while": "step_feedback"},
        ],
        "expect": ["step_card", "case_changed", "done"],
    },
    "t45_safety_dealer": {
        "title": "T45 安全：吸奶器加热烫伤 → 停用并转人工，摘要带经销商名录结论",
        "knowledge": False,
        "steps": [{"ticket": "T45"}],
        "expect": ["escalation_summary", "done"],
    },
    "t14_hardware_fault": {
        "title": "T14 硬件故障：错误码 4090 官方判硬件故障 → 不排障，直进质保（收订单 / 凭证）",
        "knowledge": False,
        "steps": [{"ticket": "T14"}],
        "expect": ["done"],
    },
    "t13_code_miss": {
        "title": "T13 荷兰语：错误码 5116 官方未收录 → 不套相近码，转人工",
        "knowledge": False,
        "steps": [{"ticket": "T13"}],
        "expect": ["escalation_summary", "done"],
    },
}
