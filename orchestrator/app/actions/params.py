import re

IDENTIFIER = re.compile(
    r"(?<![A-Z0-9-])(?:DEMO-[A-Z0-9-]{3,30}|SRV-[A-Z0-9]{6,32}|[A-Z]{2,8}-[0-9]{6,20})(?![A-Z0-9-])",
    re.IGNORECASE,
)


def extract_params(text: str, facts: dict | None = None) -> dict:
    result = {
        k: v
        for k, v in (facts or {}).items()
        if k in {"order_no", "tracking_no"} and isinstance(v, str) and IDENTIFIER.fullmatch(v)
    }
    for match in IDENTIFIER.finditer(text):
        value = match.group().upper()
        key = (
            "tracking_no"
            if "TRACK-" in value
            else "service_order_no"
            if value.startswith("SRV-")
            else "order_no"
        )
        result.setdefault(key, value)
    return result


def missing_params(kind, params):
    if kind == "logistics.query":
        return (
            []
            if any(params.get(k) for k in ("order_no", "tracking_no", "service_order_no"))
            else ["order_no"]
        )
    return [] if params.get("order_no") else ["order_no"]


def changes_order(text: str) -> bool:
    return bool(
        re.search(
            r"(?:另[一个笔张]*|其他|其它|新的?|别的)(?:.{0,4})(?:订单|运单|物流单|服务单)|换(?:个|一个|一笔)订单",
            text,
        )
    )
