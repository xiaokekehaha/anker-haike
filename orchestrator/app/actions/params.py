import re

# 主办方编号格式：订单 Anker016；运单 Anker1234567 / Anker1234567-3（工单里也出现 "Anker 1234567-4"）；
# 服务单 SRV-XXXXXXXXXXXX（本系统生成）。
ORDER_NO = re.compile(r"(?<![A-Za-z0-9])Anker\d{3}(?![\d-])", re.IGNORECASE)
TRACKING_NO = re.compile(r"(?<![A-Za-z0-9])Anker ?\d{7}(?:-\d{1,3})?(?![\w-])", re.IGNORECASE)
SERVICE_ORDER_NO = re.compile(r"(?<![A-Z0-9-])SRV-[A-Z0-9]{6,32}(?![A-Z0-9-])", re.IGNORECASE)
IDENTIFIER = re.compile(f"{SERVICE_ORDER_NO.pattern}|{TRACKING_NO.pattern}|{ORDER_NO.pattern}", re.IGNORECASE)


def classify(value: str) -> tuple[str, str]:
    """(key, canonical value)；canonical 与 data/official 的写法一致。"""
    if SERVICE_ORDER_NO.fullmatch(value):
        return "service_order_no", value.upper()
    if TRACKING_NO.fullmatch(value):
        return "tracking_no", "Anker" + value[5:].replace(" ", "")
    return "order_no", "Anker" + value[5:]


def extract_params(text: str, facts: dict | None = None) -> dict:
    result = {
        k: v
        for k, v in (facts or {}).items()
        if k in {"order_no", "tracking_no"} and isinstance(v, str) and IDENTIFIER.fullmatch(v)
    }
    for match in IDENTIFIER.finditer(text):
        key, value = classify(match.group())
        result.setdefault(key, value)
    return result


def missing_params(kind, params):
    if kind == "logistics.query":
        return (
            []
            if any(params.get(k) for k in ("order_no", "tracking_no", "service_order_no"))
            else ["order_no"]
        )
    if kind == "service_order.create":
        return []
    return [] if params.get("order_no") else ["order_no"]


def changes_order(text: str) -> bool:
    return bool(
        re.search(
            r"(?:另[一个笔张]*|其他|其它|新的?|别的)(?:.{0,4})(?:订单|运单|物流单|服务单)|换(?:个|一个|一笔)订单"
            r"|another order|different order|other order",
            text,
            re.IGNORECASE,
        )
    )
