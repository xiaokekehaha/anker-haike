"""票 24：product_state 三分、澄清（clarification）与追问上限 R7（09 §1.1、§2.1；03 §1.2、§1.3；01 F5c）。

路由只有三种处理结果：继续 / 澄清 / 升级，由后端根据状态与目录规则决定，不用模型自报置信度。

- product_state：confirmed_sku（目录唯一命中或卡片选中）/ category_only（零命中但品类词明确，且有适用的
  category_generic 预写计划）/ unknown（品类未定，只允许追问或升级）。
- clarification = {reason: product | symptom | conflict, attempts, asked_run_id}：checkpoint 内部状态。
  每次实际发出澄清问题（文字追问或产品卡片）attempts + 1；收到回答后仍不明且 attempts ≥ 2 → R7。
  信息补齐并可进入合法流程后清零；同一未决问题换措辞、换 run 不重置。与排障 counters 分开计数。
- 追问文案由 ModelRouter task=disambiguate.clarify 生成（tag=internal，结构化 {question}），失败用固定文案。
- 澄清阶段不生成新步骤、不检索、不改写查询；run 以 done(completed) 结束但会话不算 solved。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.queue import CapacityExceeded
from app.models.router import ModelInvokeError, ModelRouter
from app.prompts import compose_system_prompt, wrap_data
from app.sessions.cards import get_catalog, get_plans

log = logging.getLogger("sessions.clarify")

Reason = Literal["product", "symptom", "conflict"]
MAX_CLARIFICATIONS = 2  # R7：连续澄清 2 次并收到回答后仍不明 → 升级
CLARIFY_BUDGET_MS = 4000
CLARIFY_PROMPT_VERSION = "2026-09-12.1"

# 指代 / 空泛表达：文本去掉产品与品类词后若只剩这些，视为「没有具体故障描述」
_DEICTIC = re.compile(
    r"^(这个|那个|它|机器|设备|这台|那台|我的|又|还是|还|就是|不行|坏了|不好用|有问题|出问题|了|啊|呀|吧|呢|的|。|，|,|\.|!|！|\?|？|\s)*$"
)
_SYMPTOM_WORDS = (
    "不吸",
    "吸力",
    "不开机",
    "无法启动",
    "开不了",
    "不充电",
    "充不",
    "异响",
    "噪音",
    "漏水",
    "不拖",
    "不回充",
    "回不去",
    "报错",
    "错误",
    "断连",
    "连不上",
    "app",
    "APP",
    "wifi",
    "WiFi",
    "地图",
    "撞",
    "卡住",
    "掉线",
    "关机",
    "灯",
    "响",
    "不动",
    "不走",
    "转",
    "停",
    "臭",
    "味",
    "热",
    "冒烟",
    "电池",
    "续航",
    "掉电",
)

FIXED_QUESTIONS: dict[str, str] = {
    "product": "为了准确排查，请告诉我设备的品类或型号，例如「扫地机 X10 Pro」或「S1 Pro 吸奶器」。",
    "symptom": "请具体描述一下故障现象：是吸力变弱、无法启动、有异响，还是其他情况？",
    "conflict": "您之前确认的是 {confirmed}，这次提到的是 {mentioned}，请问需要排查的是哪一台？",
}


class ClarifyQuestion(BaseModel):
    """disambiguate.clarify 任务的模型输出 schema。"""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=2, max_length=80, description="一句具体的中文追问，不含步骤")


@dataclass
class Decision:
    """disambiguate 的三种处理结果之一。"""

    outcome: Literal["continue", "clarify", "escalate"]
    update: dict[str, Any] = field(default_factory=dict)
    reason: Reason | None = None
    detail: dict[str, Any] = field(default_factory=dict)  # 追问文案所需的上下文（conflict 双方等）


# ---------------------------------------------------------------------------
# 判定
# ---------------------------------------------------------------------------


def decide(state: dict[str, Any], *, abandoned_card: dict[str, Any] | None) -> Decision:
    """按 09 §1.1 的三种结果判定本轮：

    1. 产品：目录匹配 → 多命中出卡（continue，由 disambiguate 路由到 prepare_card）/ 单命中确认 /
       零命中：品类词明确且有通用计划 → category_only；否则 product 澄清或 R7。
    2. 冲突：已确认产品与本轮提到的品类不一致且无法唯一定位 → conflict 澄清。
    3. 症状：产品已定但没有任何故障描述（抽取为空且原文只剩指代）→ symptom 澄清。
    """
    catalog = get_catalog()
    text = state.get("text", "") or ""
    hints = [h for h in (state.get("product_hints") or []) if h]
    clar = dict(state.get("clarification") or {})
    confirmed = state.get("product_confirmed") or None

    # ---- 1) 产品 ----
    cands = _lookup(catalog, text, hints)
    category = catalog.category_hint(text) or next(
        (catalog.category_hint(h) for h in hints if catalog.category_hint(h)), None
    )
    update: dict[str, Any] = {}
    if abandoned_card:
        # 用户对产品卡片未选而改发文本：卡片已由 intake 作废；这里只留观察记录（次数已在出卡时计入）
        update["observations"] = [
            *(state.get("observations") or []),
            "用户未在产品确认卡片中选择，改为文字补充",
        ]

    if confirmed:
        confirmed_skus = {confirmed.get("sku")}
        if cands and {c["sku"] for c in cands} != confirmed_skus:
            if len(cands) == 1:
                # 型号纠正：重新确认新产品，旧证据与检索状态失效（09 §1.1、记忆设计 §3.2 第 5 条）
                update.update(_confirm(cands[0]))
                update.update({"evidence": {}, "knowledge_status": None})
                confirmed = cands[0]
            else:
                # 提到多个候选 → 再次确认（卡片），不算文字澄清
                update.update({"product_candidates": cands, "product_confirmed": None})
                update["product_state"] = "unknown"
                return Decision("continue", update)
        elif not cands and category and category != confirmed.get("category"):
            mentioned = (
                catalog.categories[category].name if category in catalog.categories else category
            )
            return _clarify(
                clar,
                "conflict",
                update,
                confirmed=confirmed.get("name") or confirmed.get("sku"),
                mentioned=mentioned,
            )
    else:
        if len(cands) > 1:
            update.update({"product_candidates": cands, "product_state": "unknown"})
            return Decision(
                "continue", update
            )  # → prepare_card（卡片本身计一次澄清，见 disambiguate）
        if len(cands) == 1:
            update.update(_confirm(cands[0]))
            confirmed = cands[0]
        else:
            update["product_candidates"] = []
            # 用户放弃卡片、原文含品类词、或历史线索含品类词 → category_only（前提：该品类有通用计划）
            if category and get_plans().allowed_for(category=category):
                spec = catalog.categories.get(category)
                update.update(
                    {
                        "product_state": "category_only",
                        "product_confirmed": None,
                        "category": category,
                        "out_of_scope": bool(spec is not None and not spec.in_scope),
                    }
                )
            elif (
                category
                and category in catalog.categories
                and not catalog.categories[category].in_scope
            ):
                # 品类明确但本期不支持（吸奶器 / 充电宝……）→ 范围外子流程；摘要文案在票 25（R8）
                update.update(
                    {
                        "product_state": "category_only",
                        "category": category,
                        "out_of_scope": True,
                        "escalate_reason": "R8",
                    }
                )
            else:
                update["product_state"] = "unknown"
                return _clarify(clar, "product", update)

    if update.get("out_of_scope"):
        return Decision("continue", update)

    # ---- 3) 症状 ----
    # 抽取结果为空时回退到原文；产品已确认（明确上文）时承接更早轮次的故障描述，不把「这个又不行了」
    # 当成新故障，也不盲目归入某一现象（09 §1.1）
    symptoms = state.get("symptoms") or []
    if not symptoms and not _has_symptom_text(catalog, text):
        earlier = [
            m.get("text", "") for m in (state.get("messages") or [])[:-1] if m.get("role") == "user"
        ]
        product_resolved = confirmed is not None or update.get("product_state") == "category_only"
        if not (product_resolved and any(_has_symptom_text(catalog, t) for t in earlier)):
            return _clarify(clar, "symptom", update)

    # 信息齐全且可进入合法流程：澄清计数清零
    update["clarification"] = None
    return Decision("continue", update)


def _clarify(
    clar: dict[str, Any], reason: Reason, update: dict[str, Any], **detail: Any
) -> Decision:
    """attempts ≥ MAX 且这是对上一问的回答 → R7；否则再问一次（attempts 在真正发问时 +1）。"""
    attempts = int(clar.get("attempts") or 0)
    if attempts >= MAX_CLARIFICATIONS:
        update.update(
            {
                "escalate_reason": "R7",
                "clarification": {**clar, "reason": reason, "resolved": False},
                "observations": [
                    *(update.get("observations") or []),
                    f"R7：连续 {attempts} 次澄清（{clar.get('reason') or reason}）并收到回答后仍无法确认",
                ],
            }
        )
        return Decision("escalate", update, reason)
    update["clarification"] = {"reason": reason, "attempts": attempts}
    return Decision("clarify", update, reason, detail)


def count_attempt(state_clar: dict[str, Any] | None, reason: Reason, run_id: str) -> dict[str, Any]:
    """真正发出一次澄清（文字追问或产品卡片）时调用：attempts + 1，记录发问的 run。"""
    clar = dict(state_clar or {})
    return {
        "reason": reason,
        "attempts": int(clar.get("attempts") or 0) + 1,
        "asked_run_id": run_id,
    }


def _confirm(cand: dict[str, Any]) -> dict[str, Any]:
    return {
        "product_confirmed": cand,
        "product_state": "confirmed_sku",
        "product_candidates": [],
        "category": cand.get("category"),
        "out_of_scope": not cand.get("in_scope", True),
    }


def _lookup(catalog, text: str, hints: list[str]) -> list[dict[str, Any]]:
    cands = [c.model_dump() for c in catalog.lookup_product(text)]
    if not cands:
        seen: set[str] = set()
        for h in hints:
            for c in catalog.lookup_product(h):
                if c.sku not in seen:
                    seen.add(c.sku)
                    cands.append(c.model_dump())
    return cands


def _has_symptom_text(catalog, text: str) -> bool:
    """抽取为空时的回退（03 §1.4.1 规则 3）：去掉产品 / 品类词后仍有具体故障描述才算有症状。"""
    rest = catalog.strip_category_words(text)
    for p in catalog.products:
        for alias in (p.name, *p.aliases, p.sku):
            rest = re.sub(re.escape(alias), " ", rest, flags=re.IGNORECASE)
    rest = rest.strip()
    if not rest or _DEICTIC.match(rest):
        return False
    return any(w.lower() in rest.lower() for w in _SYMPTOM_WORDS) or len(rest) >= 6


# ---------------------------------------------------------------------------
# 追问文案
# ---------------------------------------------------------------------------


def fixed_question(reason: str, detail: dict[str, Any]) -> str:
    tpl = FIXED_QUESTIONS.get(reason, FIXED_QUESTIONS["product"])
    try:
        return tpl.format(**detail)
    except (KeyError, IndexError):
        return FIXED_QUESTIONS["product"]


CLARIFY_INSTRUCTION = {
    "product": "用户没有说明设备的品类或型号。请只输出一句具体的中文追问，请用户提供品类或型号；不要给排查步骤，不要猜测型号。",
    "symptom": "设备已确认，但用户没有描述具体故障现象。请只输出一句具体的中文追问，给出两三个常见现象让用户选择（如吸力变弱 / 无法启动 / 异响）；不要给排查步骤。",
    "conflict": "用户之前确认的产品与这次提到的产品不一致。请只输出一句具体的中文追问，请用户确认要排查的是哪一台；不要给排查步骤。",
}


def build_messages(
    reason: str, text: str, *, strategy: str, summary: dict[str, Any] | None, detail: dict[str, Any]
) -> list[tuple[str, str]]:
    ctx = ""
    if reason == "conflict":
        ctx = f"之前确认：{detail.get('confirmed')}；这次提到：{detail.get('mentioned')}。"
    return [
        ("system", compose_system_prompt(strategy, summary)),
        (
            "human",
            f'{CLARIFY_INSTRUCTION[reason]}{ctx}\n只输出 JSON：{{"question": "..."}}\n{wrap_data(text)}',
        ),
    ]


@dataclass
class QuestionOutcome:
    text: str
    model_used: str  # skipped / fixed / 模型名
    model_trace: dict[str, Any] | None = None


async def make_question(
    router: ModelRouter | None,
    reason: str,
    text: str,
    *,
    strategy: str,
    summary: dict[str, Any] | None,
    detail: dict[str, Any],
    session_id: str | None,
    lane: str,
    budget_ms: int = CLARIFY_BUDGET_MS,
) -> QuestionOutcome:
    fallback = fixed_question(reason, detail)
    if router is None:
        return QuestionOutcome(fallback, "skipped")
    try:
        res = await router.invoke(
            "disambiguate.clarify",
            build_messages(reason, text, strategy=strategy, summary=summary, detail=detail),
            ClarifyQuestion,
            budget_ms=budget_ms,
            session_id=session_id,
            lane=lane,
        )
    except (ModelInvokeError, CapacityExceeded) as exc:
        log.warning("clarify question degraded session=%s reason=%s", session_id, str(exc)[:200])
        return QuestionOutcome(
            fallback,
            "fixed",
            {"task": "disambiguate.clarify", "model_used": "skipped", "lane": lane, "attempts": 1},
        )
    q = res.parsed.question.strip()
    return QuestionOutcome(
        q or fallback,
        res.model_used,
        {
            "task": "disambiguate.clarify",
            "model_used": res.model_used,
            "lane": res.lane,
            "attempts": max(1, len(res.attempts)),
        },
    )
