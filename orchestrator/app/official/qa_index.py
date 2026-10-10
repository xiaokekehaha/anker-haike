"""官方 Q&A 的确定性索引：错误码 + PN 精确查找、条目类型、步骤拆分、媒体链接。

全部由 data/official/qa.yaml 派生，不依赖 WeKnora 与模型；WeKnora 只在没有错误码时做语义召回。

错误码抽取必须带锚点：S1 Pro 有 E20 / E25 / E28 错误码，与机型名 Omni E25 / E28 同形，
全局正则会把机型名当成码（rv-0484）。码只认这几种位置：
    has 4090 Error: …        reports a warning 6025: …        reports an error: 6040/6041 …
    has E23: …               has EB01: …                       tips 7032: …
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Literal

from app.official.models import OfficialData, QAEntry, pn_of

Kind = Literal["steps", "answer", "warranty"]
# 一个编号段落对用户意味着什么（2026-10-09 第二批 I4）：要回答、要操作、只需知道、要提供材料、还是要交人工。
StepKind = Literal["action", "question", "statement", "material_request", "handoff"]

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
DANGLING_REFERENCE = re.compile(
    r"\b(?:steps?|instructions?|guides?|articles?|videos?|links?)\b[^\n]{0,100}"
    r"\b(?:found at|available at|provided at|(?:shown|listed|provided) below)\s*:\s*$",
    re.IGNORECASE,
)


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
    kind: StepKind = "action"
    options: tuple[str, ...] = ()
    # 选项 → 目标（question 用）：int 是段落位置 pos；str 是本条计划的 step_id（s3b）或 "EXHAUSTED"
    branches: dict[str, int | str] = field(default_factory=dict)
    default: int | str | None = None  # 回答不在选项里时去哪儿；None 沿原文顺序走下一步
    title: str = ""  # 人工审核给的卡片标题（question 卡只显示标题与选项，原文段落不是问句时必须给）
    parts: tuple[Step, ...] = ()  # 人工审核把一段拆成多步（段内问句、诊断树）；为空即整段一步
    disabled: bool = False
    disabled_reason: str = ""
    source_gap: bool = False


@dataclass(frozen=True)
class FaultSection:
    title: str
    start: int
    end: int


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
    sections: tuple[FaultSection, ...] = ()

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


# ---- 步骤类型 ----
# 875 条 Q&A 共 1364 段，非 action 段不到 11%，question 只有 3 段：规则分类够用，少数条目用 qa_overrides.yaml 修正。
ACTION_VERB = re.compile(
    r"\b(?:check|clean|remove|press|turn|restart|reboot|reset|replace|place|ensure|make sure|fill|wipe|install|update|"
    r"open|close|try|use|disconnect|connect|charge|empty|re-?install|tighten|hold|move|put|take out|pull|push|unplug|"
    r"plug|power(?=\s+(?:on|off|up|down|cycle)\b)|switch|run|start|confirm|verify|adjust|set|enable|disable|delete|re-?add|log in|test|compare|inspect|"
    r"look|shake|dry|rinse|align|separate|flip|rotate|lift|lower|change|disassemble|reassemble|attach|detach|wash|"
    r"calibrate|pair|re-?pair|add|download|upgrade|contact|apply|attempt|observe)\b",
    re.IGNORECASE,
)
MATERIAL = re.compile(
    r"\b(?:please\s+)?(?:record|send(?: us)?|provide(?: us with)?|upload|share|attach|take)\b[^.]{0,60}"
    r"\b(?:photo|picture|image|video|audio|clip|screenshot|screen recording)s?\b",
    re.IGNORECASE,
)
HANDOFF = re.compile(
    r"^(?:if .{0,100}(?:persists?|still|cannot|unable|not resolved|ineffective)[^.]*[,.]?\s*)?(?:please\s+)?"
    r"contact (?:us|customer service|support|eufy)\b",
    re.IGNORECASE,
)
HEADING = re.compile(r"^(?:step\s*\w+\s*[:：]\s*)?[A-Z][\w &/,()'-]{2,60}:?$")
STATEMENT_LEAD = re.compile(r"^(?:when|if|this|it is normal|the (?:robot|device|app|noise|base station)|note|during|after|under)\b", re.IGNORECASE)
DESCRIPTIVE = re.compile(
    r"\b(?:will|may|can)\b|^(?:the\s+.+?\s+(?:is|are|has|uses?)\b)",
    re.IGNORECASE,
)
REQUEST = re.compile(
    r"(?:^|[.!?:;,]\s+|\n)\s*[-*•]*\s*(?:please\s+)?"
    r"(?:(?:you\s+(?:can|may|should|must|need to)|it is (?:recommended|advised) to)\s+)?"
    r"(?:(?:\w+ly|first|then|also|further)\s+)*" + ACTION_VERB.pattern,
    re.IGNORECASE,
)
QUESTION_PAREN = re.compile(r"\(([^()]*?/[^()]*?)\)\s*$")
QUESTION_OR = re.compile(r"\b(?:is|are|does|do)\s+(?:it|the \w+(?: \w+)?)\s+(\w[\w-]*)\s+or\s+(\w[\w-]*)\s*\?$", re.IGNORECASE)


def _head_body(text: str) -> tuple[str, list[str]]:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    return (lines[0] if lines else ""), lines[1:]


def classify_step(text: str) -> StepKind:
    """按段落首行判定类型。顺序：问句 → 材料请求 → 交人工 → 纯标题（正文有动作则 action）→ 说明句 → 操作。"""
    head, body = _head_body(text)
    # 首句：句号后面不一定有空格（「…as shown in the picture.If it's loose, please provide a picture」）
    first_sentence = re.split(r"(?<=[.!?])\s*(?=[A-Z])", head, maxsplit=1)[0]
    # 问句：以 ? 结尾，或 ? 后只跟一段括号里的选项（「When does it occur? (… / … / …)」）
    if (head.rstrip().endswith("?") or re.search(r"\?\s*\([^()]*\)\s*$", head)) and len(head) < 200:
        return "question"
    # 材料请求是这一段的主要内容才算；操作之后附带的「若松动请拍照」仍是操作步骤（rv-0272）
    if MATERIAL.search(first_sentence) and not ACTION_VERB.match(first_sentence.lstrip("- ")):
        return "material_request"
    if HANDOFF.match(head) and not ACTION_VERB.search(" ".join(body)):
        return "handoff"
    # A condition describing the warranty outcome is not a customer operation.
    if WARRANTY.search(text) and not REQUEST.search(text):
        return "handoff"
    if DESCRIPTIVE.search(head) and not REQUEST.search(text):
        return "statement"
    if HEADING.match(head) and not ACTION_VERB.search(head):
        return "action" if ACTION_VERB.search(" ".join(body)) else "statement"
    if STATEMENT_LEAD.match(head) and not REQUEST.search(text):
        return "statement"
    return "action"


def question_options(text: str) -> tuple[str, ...]:
    """问句里列出的选项：括号内以 / 分隔（「(upon startup / During pumping / Only at high speed)」），或 A or B。"""
    head, _ = _head_body(text)
    if match := QUESTION_PAREN.search(head):
        parts = [p.strip(" ?.") for p in match.group(1).split("/")]
        return tuple(p for p in parts if p)
    if match := QUESTION_OR.search(head):
        return (match.group(1), match.group(2))
    return ()


def overrides_path() -> Path:
    """与 qa.yaml 同目录（本机 data/official，容器内 OFFICIAL_DATA_DIR）。"""
    from app.official.models import OFFICIAL_DIR

    return OFFICIAL_DIR / "qa_overrides.yaml"


@lru_cache(maxsize=1)
def load_overrides(path: Path | None = None) -> dict[str, dict[int, dict]]:
    """人工审核结果：{qa_id: {pos: spec}}。pos 是段落在原文中的位置（从 1 起），
    不是原文编号 —— bp-0123 的「Step 1:」与「1.」编号都是 1。文件不存在视为空。字段见 qa_overrides.yaml 文件头。"""
    import yaml

    target = path or overrides_path()
    if not target.is_file():
        return {}
    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    return {str(qa_id): {int(no): dict(spec or {}) for no, spec in (entries or {}).items()} for qa_id, entries in raw.items()}


SPEC_KEYS = {"kind", "title", "options", "branches", "default", "disabled", "reason"}


def _target(value: int | str) -> int | str:
    return value if isinstance(value, int) else str(value)


def _spec_step(no: int, pos: int, text: str, spec: dict, *, warranty: bool) -> Step:
    if unknown := set(spec) - SPEC_KEYS:
        raise ValueError(f"unknown override keys in paragraph {pos}: {sorted(unknown)}")
    kind: StepKind = spec.get("kind") or classify_step(text)
    options = tuple(spec.get("options") or (question_options(text) if kind == "question" else ()))
    return Step(
        no=no, text=strip_urls(text), media=media_of(text), warranty=warranty or kind == "handoff",
        kind=kind, options=options, branches={str(k): _target(v) for k, v in (spec.get("branches") or {}).items()},
        default=_target(spec["default"]) if spec.get("default") is not None else None,
        title=str(spec.get("title") or ""),
        disabled=bool(spec.get("disabled")), disabled_reason=str(spec.get("reason") or ""),
        source_gap=bool(DANGLING_REFERENCE.search(text)),
    )


def _split_parts(no: int, pos: int, text: str, specs: list[dict]) -> tuple[Step, ...]:
    """按审核锚点切段：第一部分从段首开始（不写 at），之后每部分从它的 at 开始；at 在段内必须唯一且依次后移。
    切出来的文字拼回去就是原段落，不增删原文。"""
    text = strip_urls(text)
    starts = [0]
    for spec in specs[1:]:
        anchor = str(spec.get("at") or "")
        if not anchor or text.count(anchor) != 1:
            raise ValueError(f"parts anchor must occur exactly once in paragraph {pos}: {anchor!r}")
        starts.append(text.index(anchor))
    if specs[0].get("at") or starts != sorted(starts) or len(set(starts)) != len(starts):
        raise ValueError(f"parts anchors must follow the paragraph order in paragraph {pos}")
    bounds = [*starts, len(text)]
    # 段内的「- 」列表符号归给哪一块都不对，去掉；其余原文一字不改
    pieces = [text[bounds[i]:bounds[i + 1]].strip(" -\n") for i in range(len(specs))]
    return tuple(_spec_step(no, pos, piece, {k: v for k, v in spec.items() if k != "at"}, warranty=bool(WARRANTY.search(piece)))
                 for piece, spec in zip(pieces, specs, strict=True))


def _typed_step(no: int, pos: int, text: str, *, warranty: bool, overrides: dict[int, dict]) -> Step:
    spec = overrides.get(pos, {})
    step = _spec_step(no, pos, text, {k: v for k, v in spec.items() if k != "parts"}, warranty=warranty)
    if spec.get("parts"):
        step = replace(step, parts=_split_parts(no, pos, text, list(spec["parts"])))
    return step


def answer_body(content: str, tips: str) -> str:
    """答案正文去掉 Tips 段：Tips 单独作为步骤卡的注意事项，正文再带一遍就重复了。"""
    if not tips:
        return content
    match = INLINE_TIPS.search(content)
    return content[: match.start()].rstrip() if match else content


INDEX_FIELD = re.compile(r"^\s*(?:Applicable Models|Applicable Error Codes(?: or problem codes)?|Core Symptoms)\s*:", re.IGNORECASE)
FAULT_HEADING = re.compile(r"\b(?:cannot|unable|malfunction|error|failure|not working|stops? working)\b", re.IGNORECASE)


def fault_sections(content: str) -> tuple[FaultSection, ...]:
    """仅识别明确故障标题下的嵌套编号检查；阶段性操作标题不能推断为互斥故障。"""
    roots: list[tuple[int, str, bool]] = []
    pos = 0
    for raw in content.splitlines():
        line = raw.strip()
        if TIPS_LINE.match(line):
            break
        match = STEP_LINE.match(line)
        if not match:
            continue
        pos += 1
        nested = line.startswith(("-", "*", "•")) or raw.startswith(("  ", "\t"))
        if nested and roots:
            start, title, _ = roots[-1]
            roots[-1] = (start, title, True)
        elif not nested:
            roots.append((pos, match.group(2).strip(), False))
    if len(roots) < 2 or not all(nested and FAULT_HEADING.search(title) and not REQUEST.search(title)
                                  for _, title, nested in roots):
        return ()
    return tuple(FaultSection(title, start, roots[i + 1][0] - 1 if i + 1 < len(roots) else pos)
                 for i, (start, title, _) in enumerate(roots))


def build_guide(entry: QAEntry, overrides: dict[int, dict] | None = None) -> Guide:
    content = "\n".join(line for line in entry.content.splitlines() if not INDEX_FIELD.match(line))
    raw_steps, tips = split_steps(content)
    overrides = overrides if overrides is not None else load_overrides().get(entry.id, {})
    sections = fault_sections(content) if not any(s.get("branches") for s in overrides.values()) else ()
    steps = tuple(
        _typed_step(n, pos, text, warranty=bool(WARRANTY.search(text)), overrides=overrides)
        for pos, (n, text) in enumerate(raw_steps, 1)
    )
    starts = {s.start for s in sections}
    steps = tuple(replace(step, kind="statement") if pos in starts and not overrides.get(pos, {}).get("kind") else step
                  for pos, step in enumerate(steps, 1))
    warranty = bool(WARRANTY.search(entry.content))
    if len(steps) < 2 and warranty and (pre := FIRST_TRY.match(entry.content)):
        # 「Please try restarting… If the restarting could not fix the issue, … hardware malfunction」：
        # 先给一步「重启」，仍未解决再走质保（25 条），不能一上来就判硬件故障。
        steps = (
            _typed_step(1, 1, pre.group(1).strip(), warranty=False, overrides=overrides),
            _typed_step(2, 2, entry.content[pre.end():].strip(), warranty=True, overrides=overrides),
        )
    if len(steps) >= 2:
        kind: Kind = "steps"
    elif warranty:
        kind = "warranty"
    else:
        kind = "answer"
    if not steps:
        steps = (_typed_step(1, 1, strip_lead_in(answer_body(content, tips)), warranty=warranty, overrides=overrides),)
    return Guide(
        qa_id=entry.id,
        title=entry.title,
        pns=tuple(entry.pn),
        codes=title_codes(entry.title),
        kind=kind,
        steps=steps,
        answer=strip_lead_in(strip_urls(answer_body(entry.content, tips))),
        tips=strip_urls(tips),
        media=media_of(entry.content),
        asks_media=bool(ASKS_MEDIA.search(entry.content)),
        visible=entry.visible,
        category=CATEGORY.get(entry.directory[1], "robot_vacuum"),
        sections=sections,
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
