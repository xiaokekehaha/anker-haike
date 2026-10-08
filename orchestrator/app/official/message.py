"""首封消息的确定性解析：App 结构化报错 / anker.com RMA 表单 / 自由邮件（英、荷、德、法、西）。

只抽可核对的字段（PN、SN、错误码、订单号、国家、购买商家、问题描述），不判断意图与故障；
意图仍由语义模型给出，这里给它和下游一个不依赖模型的事实底座：
- PN 直接锁产品（「S1 Pro」同名时不必再出产品卡）；
- 错误码走 QAIndex 精确命中；
- SN、订单号、国家 / 商家进入 SOP 证据与经销商判定；
- 语言决定回复语言（D2：客户语言 + 中文译文）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.actions.params import extract_params
from app.official.models import pn_of
from app.official.qa_index import message_codes

FIELD = r"[ \t]*[:：][ \t]*"
LABELS: dict[str, tuple[str, ...]] = {
    "product_name": ("Product Name", "Productnaam", "Produktname", "Nom du produit", "Nombre del producto"),
    "pn": ("Product PN", "Product-PN", "Produktnummer \\(PN\\)", "Produktnummer", "Référence produit",
           "Número de parte del producto", "SKU"),
    "sn": ("Product SN", "Product-SN", "Prodcut SN", "Seriennummer \\(SN\\)", "Seriennummer", "SN"),
    "description": ("Problem Description", "Probleembeschrijving", "Probleemomschrijving", "Problembeschreibung",
                    "Description du problème", "Descripción del problema"),
    "push": ("Problem Push", "Probleempush", "Push-Benachrichtigung"),
    "order_no": ("Order No", "Order Number", "Order", "Ordernummer", "Bestellnummer", "Numéro de commande", "Número de pedido"),
    "country": ("Country", "Land", "Pays", "País", "Inlogland", "Land van accountregistratie"),
    "source": ("Source", "Bron"),
}
APP_MARKERS = re.compile(r"Product\s*PN|Product-PN|Produktnummer|Référence produit|Número de parte|Problem Type|Probleemtype|Problemtyp", re.IGNORECASE)
RMA_MARKERS = re.compile(r"----RMA----|Submit Date|Prodcut SN|Purchase proof", re.IGNORECASE)
URLS = re.compile(r"\[?\s*\"?https?://\S+|\[\s*\]")
SELLER = re.compile(r"(?:ordered|bought|purchased)[ \t]+(?:it[ \t]+)?(?:from|at|on)[ \t]+(?:the[ \t]+)?(?:reseller[ \t]+)?([A-Z][\w&'.-]*(?:[ \t]+[A-Z][\w&'.-]*){0,3})", re.IGNORECASE)

# 只用各语言独有的词：英文工单里也会出现 the / die / la 这类拼写，功能词会误判。
LANG_HINTS = {
    "nl": ("productnaam", "probleem", "gelieve", " niet ", " het ", "bestelling", "stofzuiger", "dweil", " taak", "wordt", " nog ", " heb ", " deze "),
    "de": ("produktname", "fehler", "bitte", " nicht ", " und ", "staubsauger", "wenden sie", "bürste"),
    "fr": ("nom du produit", "problème", "bonjour", "aspirateur", " je ", " est ", " avec ", " pas "),
    "es": ("nombre del producto", "problema", " está", "desconectado", "aspiradora", " el robot", " del "),
}


@dataclass
class ParsedMessage:
    format: str  # app_report | rma | email
    language: str
    pn: str | None = None
    sn: str | None = None
    codes: tuple[str, ...] = ()
    order_no: str | None = None
    tracking_no: str | None = None
    country: str | None = None
    seller: str | None = None
    product_name: str | None = None
    description: str | None = None
    fields: dict[str, str] = field(default_factory=dict)

    @property
    def problem_text(self) -> str | None:
        """检索用的问题原话：表单的问题描述 / 推送提示，不含表头、订单字段与图片链接。自由邮件返回 None（用全文）。"""
        parts = list(dict.fromkeys(v for k in ("push", "description") if (v := self.fields.get(k))))
        text = URLS.sub(" ", " ".join(parts)).strip()
        return text or None

    @property
    def has_facts(self) -> bool:
        return bool(self.pn or self.sn or self.codes or self.order_no or self.tracking_no)


def _field(text: str, key: str) -> str | None:
    for label in LABELS[key]:
        if match := re.search(rf"(?im)^[ \t]*{label}{FIELD}([^\n]*)$", text):
            value = match.group(1).strip()
            if value and value.lower() not in {"null", "[]", "-", "/"}:
                return value
    return None


def detect_language(text: str) -> str:
    """中文 / 英 / 荷 / 德 / 法 / 西的粗判；结构化字段名本身就是很强的语言信号。"""
    if re.search(r"[一-鿿]", text):
        return "zh"
    low = f" {text.casefold()} "
    scores = {lang: sum(low.count(h) for h in hints) for lang, hints in LANG_HINTS.items()}
    lang, score = max(scores.items(), key=lambda kv: kv[1])
    return lang if score >= 2 else "en"


def parse_message(text: str) -> ParsedMessage:
    fmt = "app_report" if APP_MARKERS.search(text) else "rma" if RMA_MARKERS.search(text) else "email"
    fields = {k: v for k in LABELS if (v := _field(text, k))}
    params = extract_params(text)
    sn_field = fields.get("sn") or ""
    if params.get("tracking_no") and params["tracking_no"].casefold() in sn_field.casefold():
        params.pop("tracking_no")  # Anker1234567E 是写在 SN 字段里的序列号，不是运单号
    pn_raw = fields.get("pn")
    pn = pn_of(pn_raw.split()[0]) if pn_raw else None
    sn = fields.get("sn")
    if sn and len(sn) < 6:
        sn = None  # 空格占位或截断的值不是 SN
    seller = None
    if match := SELLER.search(text):
        seller = match.group(1).strip(" .,")
    country = fields.get("country")
    return ParsedMessage(
        format=fmt,
        language=detect_language(text),
        pn=pn,
        sn=sn.upper() if sn else None,
        codes=message_codes(text),
        order_no=params.get("order_no"),
        tracking_no=params.get("tracking_no"),
        country=country.upper() if country and len(country) <= 3 else country,
        seller=seller,
        product_name=fields.get("product_name"),
        description=fields.get("description"),
        fields=fields,
    )
