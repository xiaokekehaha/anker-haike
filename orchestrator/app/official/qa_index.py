"""官方 Q&A 的确定性索引：错误码 + PN 精确查找、条目类型、步骤拆分、媒体链接。

全部由 data/official/qa.yaml 派生，不依赖 WeKnora 与模型；WeKnora 只在没有错误码时做语义召回。

错误码抽取必须带锚点：S1 Pro 有 E20 / E25 / E28 错误码，与机型名 Omni E25 / E28 同形，
全局正则会把机型名当成码（rv-0484）。码只认这几种位置：
    has 4090 Error: …        reports a warning 6025: …        reports an error: 6040/6041 …
    has E23: …               has EB01: …                       tips 7032: …
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

from app.official.models import OfficialData, QAEntry, pn_of

Kind = Literal["steps", "answer", "warranty"]

CODE = r"(?:\d{4}|E[0-9A-Z]{1,3}|EB[0-9A-Z]{1,2})"
CODE_LIST = rf"{CODE}(?:\s*(?:/|,|&|or)\s*{CODE})*"
# 锚点之后紧跟的码串；码串之后必须是 : - Error 或空格 + 描述（不是机型名后的 /）
TITLE_CODES = [
    re.compile(rf"\bhas\s+(?:a\s+|an\s+)?(?:warning\s+|error\s+|alert\s+)?({CODE_LIST})\s*(?:[:：\-]|Error|error|warning|\s)", re.IGNORECASE),
    re.compile(rf"\breports?\s+(?:a\s+|an\s+)?(?:warning|error|alert|toast|tips?)\s*[:：]?\s*({CODE_LIST})\s*(?:[:：\-]|Error|error|\s)", re.IGNORECASE),
    re.compile(rf"\btips\s+({CODE_LIST})\s*[:：]", re.IGNORECASE),
    re.compile(rf"\b(?:with|shows?|displays?|code)\s+({CODE_LIST})\s+(?:Error|error|warning)\b"),
    re.compile(rf"\b({CODE_LIST})\s+Error\s*[:：]"),
    # reports warning/error:2113 …、reports an error-1012 …、has Abnormal alert: E5G: …
    re.compile(rf"\b(?:warning/error|error|warning|alert)\s*[:：\-]\s*({CODE_LIST})\b(?!\s*/\s*Omni)", re.IGNORECASE),
    # displays 3222-The mop …、gives out E10: …、displays error E32: …
    re.compile(rf"\b(?:displays?|gives out|shows?)\s+(?:error\s+)?({CODE_LIST})\s*[:：\-]", re.IGNORECASE),
    # error message "5012-…"、(error 7031)、Trigger Error 6031 "…"
    re.compile(rf"(?:error message\s+[\"“']|\(error\s+|Trigger Error\s+)({CODE_LIST})\b", re.IGNORECASE),
    # code-6536 Insufficient …, code-6537 …
    re.compile(rf"\bcode-({CODE})\b", re.IGNORECASE),
    # … or 1022 Right wheel module error：多码用 or 连接时的后续码
    re.compile(rf"\bor\s+({CODE})\s+[A-Z][a-z]+.*?\berror\b"),
]
SPLIT_CODES = re.compile(r"\s*(?:/|,|&|\bor\b)\s*", re.IGNORECASE)

WARRANTY = re.compile(
    r"hardware malfunction|offer (?:you )?our warranty service|provide (?:you with )?warranty service"
    r"|ship (?:you )?a replacement|arrange (?:a )?replacement|replacement part",
    re.IGNORECASE,
)
FIRST_TRY = re.compile(
    r"\s*((?:please\s+)?(?:try|first)\s+[^.]*?(?:restart|reboot|reset)[^.]*\.)\s*(?=(?:if|when)\b)",
    re.IGNORECASE,
)
STEP_LINE = re.compile(r"^[\s*•\-]*(?:Step\s*)?(\d{1,2})\s*[.)、:：]\s*(.+)$", re.IGNORECASE)
TIPS_LINE = re.compile(r"^[\s*•\-]*(?:Additional\s+)?Tips?\b", re.IGNORECASE)
URL = re.compile(r"https?://[^\s)\]>\"']+")
ASKS_MEDIA = re.compile(r"\b(?:send|provide|upload|share|attach)\b[^.]{0,60}\b(?:photo|picture|image|video)s?\b", re.IGNORECASE)


@dataclass(frozen=True)
class Media:
    url: str
    kind: Literal["image", "video", "link"]


@dataclass(frozen=True)
class Step:
    no: int
    text: str
    media: tuple[Media, ...] = ()
    warranty: bool = False


@dataclass(frozen=True)
class Guide:
    qa_id: str
    title: str
    pns: tuple[str, ...]
    codes: tuple[str, ...]
    kind: Kind
    steps: tuple[Step, ...]
    answer: str
    tips: str = ""
    media: tuple[Media, ...] = ()
    asks_media: bool = False
    visible: bool = True
    category: str = ""

    @property
    def plan_id(self) -> str:
        return "qa_" + self.qa_id.replace("-", "_")


def media_of(text: str) -> tuple[Media, ...]:
    out = []
    for url in URL.findall(text):
        url = url.rstrip(".,;")
        low = url.lower()
        kind = "video" if any(x in low for x in (".mp4", ".mov", "youtube.com", "youtu.be")) else (
            "image" if any(x in low for x in (".png", ".jpg", ".jpeg", ".gif", ".webp")) else "link"
        )
        out.append(Media(url, kind))
    return tuple(dict.fromkeys(out))


def strip_urls(text: str) -> str:
    return re.sub(r"\s{2,}", " ", URL.sub("", text)).strip()


def title_codes(title: str) -> tuple[str, ...]:
    codes: list[str] = []
    for pattern in TITLE_CODES:
        for match in pattern.finditer(title):
            codes.extend(c.upper() for c in SPLIT_CODES.split(match.group(1)) if c)
    return tuple(dict.fromkeys(codes))


LEAD_IN = re.compile(
    r"^\s*(?:please\s+)?(?:follow|try)\s+(?:these|the following|the steps below)[^:：\n]{0,40}[:：]\s*"
    r"|^\s*troubleshoot(?:ing)?\s+as\s+follows\s*[:：]\s*",
    re.IGNORECASE,
)


def strip_lead_in(text: str) -> str:
    """去掉「Please follow these troubleshooting steps:」这类引导语与单步条目开头的「1.」，卡片标题才是动作本身。"""
    return re.sub(r"^[*•\s]*1\s*[.)、]\s*", "", LEAD_IN.sub("", text, count=1).lstrip(), count=1)


def split_steps(content: str) -> tuple[list[tuple[int, str]], str]:
    """编号行开启一步，其后非编号行（含图片 / 视频链接）归入该步；Tips 段落之后不再是步骤。"""
    steps: list[list] = []
    tips: list[str] = []
    in_tips = False
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        if TIPS_LINE.match(line):
            in_tips = True
        if in_tips:
            tips.append(line)
            continue
        match = STEP_LINE.match(line)
        if match:
            steps.append([int(match.group(1)), match.group(2)])
        elif steps:
            steps[-1][1] += "\n" + line
    if len(steps) < 2:
        inline = inline_steps(content)
        if len(inline) >= 2:
            return inline, "\n".join(tips)
    return [(n, t) for n, t in steps], "\n".join(tips)


INLINE_NO = re.compile(r"(?:^|(?<=[.:;!?。：；*])\s*|\n\s*)[*•\s]*(\d{1,2})[.)]\s+")
INLINE_TIPS = re.compile(r"[*•\s]*(?:Additional\s+)?Tips?\s*[:：]", re.IGNORECASE)


def inline_steps(content: str) -> list[tuple[int, str]]:
    """同一行内的「1. … 2. …」：只认句首、且从 1 开始逐个递增的编号，避免把版本号 7.0.143 当步骤。"""
    marks, expected = [], 1
    for match in INLINE_NO.finditer(content):
        if int(match.group(1)) == expected:
            marks.append(match)
            expected += 1
    steps = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(content)
        text = content[m.end(): end]
        if tips := INLINE_TIPS.search(text):
            text = text[: tips.start()]
        steps.append((int(m.group(1)), text.strip(" *•\n")))
    return steps


CATEGORY = {"Breast Pump": "breast_pump", "SoloCam": "security_cam"}


def answer_body(content: str, tips: str) -> str:
    """答案正文去掉 Tips 段：Tips 单独作为步骤卡的注意事项，正文再带一遍就重复了。"""
    if not tips:
        return content
    match = INLINE_TIPS.search(content)
    return content[: match.start()].rstrip() if match else content


def build_guide(entry: QAEntry) -> Guide:
    raw_steps, tips = split_steps(entry.content)
    steps = tuple(
        Step(no=n, text=strip_urls(text), media=media_of(text), warranty=bool(WARRANTY.search(text)))
        for n, text in raw_steps
    )
    warranty = bool(WARRANTY.search(entry.content))
    if len(steps) < 2 and warranty and (pre := FIRST_TRY.match(strip_urls(entry.content))):
        # 「Please try restarting… If the restarting could not fix the issue, … hardware malfunction」：
        # 先给一步「重启」，仍未解决再走质保（25 条），不能一上来就判硬件故障。
        steps = (
            Step(no=1, text=pre.group(1).strip()),
            Step(no=2, text=strip_lead_in(strip_urls(entry.content[pre.end():])).strip(), warranty=True),
        )
    if len(steps) >= 2:
        kind: Kind = "steps"
    elif warranty:
        kind = "warranty"
    else:
        kind = "answer"
    return Guide(
        qa_id=entry.id,
        title=entry.title,
        pns=tuple(entry.pn),
        codes=title_codes(entry.title),
        kind=kind,
        steps=steps if kind == "steps" else (),
        answer=strip_lead_in(strip_urls(answer_body(entry.content, tips))),
        tips=strip_urls(tips),
        media=media_of(entry.content),
        asks_media=bool(ASKS_MEDIA.search(entry.content)),
        visible=entry.visible,
        category=CATEGORY.get(entry.directory[1], "robot_vacuum"),
    )


# ---- 工单 / 客户消息里的错误码 ----

# App 结构化反馈的字段名（英 / 荷 / 德 / 法 / 西）
FIELD_CODE = re.compile(
    r"(?:Problem\s*Code|Probleemcode|Fehlercode|Code\s+du\s+probl[eè]me|C[oó]digo(?:\s+del\s+problema)?)\s*[:：]\s*([^\n]*)",
    re.IGNORECASE,
)
FIELD_PUSH = re.compile(
    r"(?:Problem\s*Push|Probleempush|Push-Benachrichtigung|Problem\s*Description|Probleembeschrijving|Problembeschreibung)\s*[:：]\s*([^\n]*)",
    re.IGNORECASE,
)
LEADING_LETTER_CODE = re.compile(r"^\s*(E[0-9A-Z]{1,3}|EB[0-9A-Z]{1,2})\s*[:：]")
LEADING_DIGIT_CODE = re.compile(r"^\s*(\d{4})(?!\d)")
INLINE_CODE = re.compile(
    r"(?:\b(?:error|code|fout|fehler|erreur)|报错|错误码?|故障码|提示码?|代码)\s*(?:code\s*)?[:：#]?\s*(\d{4}|E[0-9A-Z]{1,3}|EB[0-9A-Z]{1,2})(?![0-9A-Za-z])",
    re.IGNORECASE,
)


def message_codes(text: str) -> tuple[str, ...]:
    """客户消息里的错误码。S1 Pro 的 Problem Code 是 8 位内部号（21037332-），忽略，改从 Push 取 EB1L / E41。"""
    codes: list[str] = []
    for value in FIELD_CODE.findall(text):
        if match := LEADING_DIGIT_CODE.match(value):
            codes.append(match.group(1))
        elif match := LEADING_LETTER_CODE.match(value):
            codes.append(match.group(1).upper())
        else:
            # 21037332-E5A: Gyroscope abnormal … 形式：内部号后面跟字母码
            if found := re.search(r"-\s*(E[0-9A-Z]{1,3}|EB[0-9A-Z]{1,2})\s*[:：]", value):
                codes.append(found.group(1).upper())
    for value in FIELD_PUSH.findall(text):
        if match := LEADING_LETTER_CODE.match(value):
            codes.append(match.group(1).upper())
    if not codes:
        codes.extend(c.upper() for c in INLINE_CODE.findall(text))
    return tuple(dict.fromkeys(codes))


@dataclass
class QAIndex:
    guides: dict[str, Guide] = field(default_factory=dict)
    by_code: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    by_pn: dict[str, list[str]] = field(default_factory=dict)
    version: str = ""

    @classmethod
    def build(cls, data: OfficialData | None = None) -> QAIndex:
        data = data or OfficialData()
        index = cls(version=data.version("qa.yaml"))
        for entry in data.qa:
            guide = build_guide(entry)
            index.guides[guide.qa_id] = guide
            for pn in guide.pns:
                index.by_pn.setdefault(pn, []).append(guide.qa_id)
                for code in guide.codes:
                    index.by_code.setdefault((pn, code), []).append(guide.qa_id)
        return index

    def lookup(self, sku: str | None, code: str) -> list[Guide]:
        """错误码精确命中；型号未知时在全部 PN 中查，仅当结果唯一属于一个型号家族才算命中。"""
        code = code.upper()
        pn = pn_of(sku) if sku else None
        if pn:
            return [self.guides[i] for i in self.by_code.get((pn, code), [])]
        hits = {i for (p, c), ids in self.by_code.items() if c == code for i in ids}
        return [self.guides[i] for i in sorted(hits)]

    def pns_for_code(self, code: str) -> set[str]:
        return {p for (p, c) in self.by_code if c == code.upper()}

    def for_pn(self, sku: str | None) -> list[Guide]:
        pn = pn_of(sku)
        return [self.guides[i] for i in self.by_pn.get(pn or "", [])]


@lru_cache(maxsize=1)
def get_qa_index() -> QAIndex:
    return QAIndex.build()
