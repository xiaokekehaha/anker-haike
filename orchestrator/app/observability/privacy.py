"""日志与追踪共用的递归脱敏；图片字节和凭证标识不进入追踪。"""

from __future__ import annotations

import re
from dataclasses import asdict, is_dataclass
from typing import Any

MASK = "[REDACTED]"
SENSITIVE = {
    "address",
    "shipping_address",
    "order_no",
    "tracking_no",
    "service_order_no",
    "order_number",
    "phone",
    "mobile",
    "telephone",
    "password",
    "secret",
    "api_key",
    "authorization",
    "bytes",
    "image_url",
}
LABELLED = re.compile(
    r'((?:订单号|订单编号|单号|order[_ -]?(?:no|number))\s*["\']?\s*[：:=]?\s*["\']?)[A-Za-z0-9_-]+',
    re.IGNORECASE,
)
LONG_NUMBER = re.compile(
    r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d[- ]?\d{4}[- ]?\d{4}(?!\d)|(?<!\d)\d{8,}(?!\d)"
)
BUSINESS_NUMBER = re.compile(r"\b(?:Anker ?\d{3,7}(?:-\d{1,3})?|SRV-[A-Z0-9]+)\b", re.IGNORECASE)
DATA_URI = re.compile(r'data:image/[^\s"\']+')
# 票 48：地址脱敏——「地址 / 收货地址 / 住址 / 寄到」标签后的整段（到句读为止）
ADDRESS = re.compile(
    r"((?:收货地址|寄送地址|送货地址|住址|地址|寄到|送到)\s*[：:=]?\s*)[^，。；！？\n,;!?]{4,80}"
)


def sanitize(value: Any, *, key: str = "") -> Any:
    normalized = key.casefold()
    if normalized in SENSITIVE or any(
        part in normalized for part in ("password", "secret", "api_key")
    ):
        return MASK
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    elif is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if isinstance(value, dict):
        return {str(k): sanitize(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v) for v in value]
    if isinstance(value, bytes):
        return "[BINARY OMITTED]"
    if isinstance(value, str):
        value = BUSINESS_NUMBER.sub(MASK, value)
        value = DATA_URI.sub("[IMAGE OMITTED]", value)
        value = LABELLED.sub(lambda m: m[1] + MASK, value)
        value = ADDRESS.sub(lambda m: m[1] + MASK, value)
        # IDs originate in the runtime, retain them for trace joins; other text is masked conservatively.
        if normalized not in {"session_id", "run_id", "trace_id", "id", "card_id", "message_id"}:
            value = LONG_NUMBER.sub(MASK, value)
        return value[:16000]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return sanitize(str(value))
