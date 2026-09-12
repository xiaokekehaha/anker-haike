"""SSE 编码：id = seq，event = type，data = 事件 JSON（05 §4 前端按 data 行解析）。"""

from __future__ import annotations

import json
from typing import Any

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


def encode(event: dict[str, Any]) -> bytes:
    data = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event['seq']}\nevent: {event['type']}\ndata: {data}\n\n".encode()


def parse(raw: str) -> list[dict[str, Any]]:
    """测试辅助：把整段 SSE 文本解析回事件列表。"""
    out: list[dict[str, Any]] = []
    for block in raw.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                out.append(json.loads(line[6:]))
    return out
