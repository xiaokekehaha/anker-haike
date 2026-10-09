"""票 24：product_state 三分、澄清（clarification）与追问上限 R7（09 §1.1、§2.1；03 §1.2、§1.3；01 F5c）。

路由只有三种处理结果：继续 / 澄清 / 升级，由后端根据状态与目录规则决定，不用模型自报置信度。

- product_state：confirmed_sku（目录唯一命中或卡片选中）/ category_only（品类已知，方案覆盖另行判断）/ unknown（品类未定，只允许追问或升级）。
- clarification = {reason: product | symptom | conflict, attempts, asked_run_id}：checkpoint 内部状态。
  每次实际发出问题记录 attempts；产品确认保留次数兜底，症状按有效答案和可区分问题决策。
  信息补齐并可进入合法流程后清零；同一未决问题换措辞、换 run 不重置。与排障 counters 分开计数。
- 追问采用确定性文案，记录实际问题与已有证据，新增有效信息会重算未进展次数。
- 澄清阶段不生成新步骤、不检索、不改写查询；run 以 done(completed) 结束但会话不算 solved。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.router import ModelRouter
from app.prompts import compose_system_prompt, wrap_data
from app.prompts.system import state_layer
from app.sessions.cards import get_catalog, get_plans

Reason = Literal["product", "symptom", "conflict"]
MAX_CLARIFICATIONS = 2  # R7：连续澄清 2 次并收到回答后仍不明 → 升级
CLARIFY_BUDGET_MS = 4000
CLARIFY_PROMPT_VERSION = "2026-09-15.1"

FIXED_QUESTIONS: dict[str, str] = {
    "product": (
        "Which product is this? For example: robot vacuum X10 Pro Omni, Omni E25 / E28, S1 Pro or Omni C20; "
        "S1 Pro wearable breast pump; or SoloCam S340 camera. The model number (e.g. T2351) also works."
    ),
    "symptom": "Could you describe what the device is doing, or tell me the error code shown in the app (e.g. 3212 or E41)?",
    "conflict": "Earlier we confirmed {confirmed}, and now you mentioned {mentioned}. Which one should we look at?",
}


class ClarifyQuestion(BaseModel):
    """disambiguate.clarify 任务的模型输出 schema。"""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=2, max_length=200, description="一句具体的英文追问，不含步骤")


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
    # App 报错 / RMA 表单里的 PN（T2080A、T8D04121…）是设备自报的型号：直接按 PN 锁定，「S1 Pro」同名也不再出卡
    from app.official.message import parse_message

    parsed_pn = parse_message(text).pn
    pinned = catalog.get(parsed_pn) if parsed_pn else None
    if pinned is None and parsed_pn:
        pinned = next(iter(catalog.lookup_product(parsed_pn)), None)
        pinned = catalog.get(pinned.sku) if pinned else None
    cands = [pinned.to_candidate().model_dump()] if pinned and pinned.in_scope else _lookup(
        catalog, text, [] if confirmed else hints
    )
    category = catalog.category_hint(text) or next(
        (catalog.category_hint(h) for h in hints if catalog.category_hint(h)), None
    )
    # 同名型号跨品类（「S1 Pro」= 扫地机 T2080 + 吸奶器 T8D04）时，品类词已经说明是哪一台。
    # 这一步对「已确认」与「未确认」两条分支同样适用：一句话能定位哪台设备，不该因为之前已经
    # 确认过就反而失去定位能力（T55 / T45）。
    if len(cands) > 1 and category:
        same = [c for c in cands if c.get("category") == category]
        cands = same if len(same) == 1 else cands
    if not category:
        # A short answer such as an unknown model must retain this issue's device.
        # Do not scan the whole transcript: it can contain other devices/issues.
        issue = (state.get("issues") or {}).get(state.get("active_issue_id")) or {}
        device_category = (issue.get("device_ref") or {}).get("category")
        for saved in (state.get("category"), device_category):
            if saved:
                category = saved if saved in catalog.categories else catalog.category_hint(saved)
                if category:
                    break
    update: dict[str, Any] = {}
    visual = state.get("visual_product") or {}
    expected = clar.get("expected_category")
    response = text.strip("。！! ")
    if not category and expected and clar.get("question"):
        if response in {"是", "是的", "对"}:
            category = expected
            update["visual_product"] = None
        elif response in {"不是", "不是的", "不对"}:
            visual = {}
            update["visual_product"] = None
            clar = {}
    if abandoned_card:
        # 用户对产品卡片未选而改发文本：卡片已由 intake 作废；这里只留观察记录（次数已在出卡时计入）
        update["observations"] = [
            *(state.get("observations") or []),
            "用户未在产品确认卡片中选择，改为文字补充",
        ]

    if confirmed and not confirmed.get("in_scope", True):
        # 范围外产品（out_of_scope 节点写的「移动电源（型号未确认）」占位，或卡片里选中的范围外 SKU）
        # 不是排障对象：本轮提到范围内的型号或品类就切换过去；否则仍是范围外，再走一次 R8 说明，
        # 不能掉进下面的症状问诊去问一台移动电源「按电源后能正常启动吗」（2026-09-17 会话 cd45df）。
        spec = catalog.categories.get(category or "")
        if cands or (spec is not None and spec.in_scope):
            confirmed = None
            update["product_confirmed"] = None
        else:
            update["out_of_scope"] = True
            return Decision("continue", update)

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
            # 用户放弃卡片、原文含品类词、或历史线索含品类词 → category_only；方案覆盖不影响品类事实
            only = [p for p in catalog.products if p.category == category and p.in_scope] if category else []
            if len(only) == 1:
                # 品类下只有一款产品（吸奶器 T8D04、SoloCam S340）：品类即型号，直接确认，不出型号卡
                update.update(_confirm(only[0].to_candidate().model_dump()))
                confirmed = update["product_confirmed"]
            elif category and category in catalog.categories:
                spec = catalog.categories.get(category)
                update.update(
                    {
                        "product_state": "category_only",
                        "product_confirmed": None,
                        "category": category,
                        "out_of_scope": bool(spec is not None and not spec.in_scope),
                    }
                )
                if not update["out_of_scope"]:
                    # spec 2026-09-19-0810 A：知识按型号分化时问一次型号（点选卡），不分化就不问
                    cands = differentiated_candidates(catalog, category, {**state, **update})
                    if cands:
                        update["product_candidates"] = cands
                        return Decision("continue", update)
            else:
                update["product_state"] = "unknown"
                visual_category = visual.get("category")
                spec = catalog.categories.get(visual_category)
                return _clarify(clar, "product", update, unmatched_hints=hints,
                                known_symptoms=sorted(set(state.get("symptoms") or [])),
                                expected_category=visual_category if spec else None,
                                category_name=(spec.name_en or spec.name) if spec else None)

    if update.get("out_of_scope"):
        return Decision("continue", update)
    return symptom_decision(state, update, clar, confirmed, category)


def symptom_decision(
    state: dict[str, Any], update: dict[str, Any], clar: dict[str, Any],
    confirmed: dict[str, Any] | None, category: str | None,
) -> Decision:
    """产品已定之后的症状判定：继续 / 问一句 / 升级。disambiguate 与产品卡片选中后（apply_action）共用，
    否则「我的 S1 Pro 出问题了」选完型号会在没有任何现象的情况下直接下发第一条计划的步骤。"""
    from app.diagnose.decision import decide_symptoms, fact_codes
    product = confirmed or {}
    category = product.get("category") or update.get("category") or category
    decision = decide_symptoms({**state, **update})
    update["diagnostic_decision"] = decision.snapshot(state)
    if decision.outcome == "continue":
        update["clarification"] = None
        codes = set(fact_codes({**state, **update}))
        available = get_plans().allowed_for(category=category, sku=product.get("sku"))
        if (
            not confirmed and codes and category
            and not any(codes.intersection(p.symptom_codes) for p in available)
        ):
            # 照片签名已定位到带错误码的官方 Q&A，但当前产品状态下一条都不可用（型号未知）：补问一次型号，
            # 而不是直接 R5（会话 e84456）
            update["product_candidates"] = model_candidates_for_codes(
                get_catalog(), category, {**state, **update}, sorted(codes)
            )
        return Decision("continue", update)
    if decision.outcome == "escalate":
        # 只剩安全限制一种升级：R4，不再继续排查。
        update.update(escalate_reason="R4",
                      clarification={**clar, "reason": "symptom", "resolved": False},
                      observations=[*state.get("observations", []), "当前无法继续排查"])
        return Decision("escalate", update, "symptom")
    return _clarify(clar, "symptom", update, category=category)


def _clarify(
    clar: dict[str, Any], reason: Reason, update: dict[str, Any], **detail: Any
) -> Decision:
    """attempts ≥ MAX 且这是对上一问的回答 → R7；否则再问一次（attempts 在真正发问时 +1）。"""
    # A budget belongs to an actual question about the same evidence. Legacy
    # counters lack that binding and cannot prove the user was asked this field.
    subject = {"reason": reason, "unmatched_hints": detail.get("unmatched_hints", []),
               "known_symptoms": detail.get("known_symptoms", []),
               "expected_category": detail.get("expected_category"),
               "confirmed": detail.get("confirmed"), "mentioned": detail.get("mentioned")}
    attempts = int(clar.get("attempts") or 0) if clar.get("question") and clar.get("subject") == subject else 0
    if attempts >= MAX_CLARIFICATIONS:
        update.update(
            {
                "escalate_reason": "R7",
                "clarification": {**clar, "reason": reason, "resolved": False},
                "observations": [
                    *(update.get("observations") or []),
                    f"R7：已就同一信息发出 {attempts} 次澄清，仍缺少继续处理所需的信息；最近问题：{clar['question']}",
                ],
            }
        )
        return Decision("escalate", update, reason)
    update["clarification"] = {"reason": reason, "attempts": attempts, "subject": subject,
                               "expected_category": detail.get("expected_category"),
                               **({"question": clar["question"]} if clar.get("question") else {})}
    return Decision("clarify", update, reason, detail)


def count_attempt(state_clar: dict[str, Any] | None, reason: Reason, run_id: str,
                  *, question: str | None = None, input_id: str | None = None) -> dict[str, Any]:
    """真正发出一次澄清（文字追问或产品卡片）时调用：attempts + 1，记录发问的 run。"""
    clar = dict(state_clar or {})
    return {
        **(clar if clar.get("reason") == reason else {}),
        "reason": reason,
        "attempts": (int(clar.get("attempts") or 0) if clar.get("reason") == reason else 0) + 1,
        "asked_run_id": run_id,
        **({"question": question, "question_id": f"{input_id}:{reason}", "asked_input_id": input_id} if question else {}),
    }


def _confirm(cand: dict[str, Any]) -> dict[str, Any]:
    return {
        "product_confirmed": cand,
        "product_state": "confirmed_sku",
        "product_candidates": [],
        "category": cand.get("category"),
        "out_of_scope": not cand.get("in_scope", True),
    }


# 用户已声明不知道型号：视同选了「不确定」，不再出型号卡
UNKNOWN_MODEL = re.compile(
    r"(不知道|不清楚|不确定|不记得|忘了|忘记)[^，。；,.;]{0,4}(型号|哪一?款|哪个型号|什么型号)"
    r"|(型号|哪一?款)[^，。；,.;]{0,4}(不知道|不清楚|不确定|不记得|忘了|忘记)"
)
# 型号卡最多几个候选；超过就退回文字追问（当前数据不会触发）
MAX_MODEL_CARD = 6


def differentiated_candidates(catalog, category: str, state: dict[str, Any]) -> list[dict[str, Any]]:
    """品类已知、型号未知时，值得问一次型号的候选（spec 2026-09-19-0810 A，T1）。

    只列「知道了会改变下一步」的型号：型号专属计划、被通用计划排除的型号、知识索引里按型号分化的资料。
    sku_list 覆盖全品类的资料按通用处理。本会话已出过型号卡、用户已声明不知道型号、
    或情绪策略要求只问必要信息（skip_optional_clarify）时不问：这张卡可以跳过，品类通用计划照样能走。
    卡片带「其他型号 / 不确定」出口（prepare_card 的 allow_unknown），所以单候选也可以问。
    """
    from app.diagnose.decision import described, fact_codes
    from app.knowledge.adapter import sku_scoped_skus
    from app.knowledge.runtime import indexed_entries

    if (
        state.get("prepare_card_calls")
        or UNKNOWN_MODEL.search(state.get("text", "") or "")
        or "skip_optional_clarify" in (state.get("emotion_actions") or [])
    ):
        return []
    category_skus = _category_skus(catalog, category)
    codes = fact_codes(state)
    issue = (state.get("issues") or {}).get(state.get("active_issue_id"), {})
    # 计划层只按症状事实上的错误码定位型号；已描述现象但没有码时没有可按码定位的计划，不因计划触发型号卡。
    if codes or not described(state, issue):
        skus = get_plans().differentiated_skus(category=category, symptom_codes=codes)
    else:
        skus = set()
    skus |= sku_scoped_skus(indexed_entries(), category, category_skus)
    return _model_card(catalog, category_skus, skus)


def model_candidates_for_codes(catalog, category: str, state: dict[str, Any], codes: list[str]) -> list[dict[str, Any]]:
    """症状码已定、当前产品状态下没有计划覆盖时，能覆盖这些码的型号专属计划对应的型号。

    与 differentiated_candidates 一样：本会话已出过型号卡、或用户已声明不知道型号就不再问。
    """
    if state.get("prepare_card_calls") or UNKNOWN_MODEL.search(state.get("text", "") or ""):
        return []
    category_skus = _category_skus(catalog, category)
    skus = get_plans().differentiated_skus(category=category, symptom_codes=codes)
    return _model_card(catalog, category_skus, skus)


def _category_skus(catalog, category: str) -> tuple[str, ...]:
    return tuple(p.sku for p in catalog.products if p.category == category and p.in_scope)


def _model_card(catalog, category_skus: tuple[str, ...], skus: set[str]) -> list[dict[str, Any]]:
    records = [catalog.get(sku) for sku in sorted(skus & set(category_skus))]
    if not records or len(records) > MAX_MODEL_CARD:
        return []
    return [r.to_candidate().model_dump() for r in records if r is not None]


def _lookup(catalog, text: str, hints: list[str]) -> list[dict[str, Any]]:
    """本轮原话里的型号；原话没有时才退回会话累积的 product_hints。

    调用方在产品已确认时传空 hints。原因：hints 跨轮累积且只增不减（reduce.py 的
    `issue["product_hints"] = [...旧, ...新]`），而「S1 Pro」这类同名别名会同时命中扫地机与
    吸奶器两个候选。于是排障走到一半，客户回一句「Here are photos of the problem.」——
    本轮原话里没有任何型号——旧 hint 被重新查成两个候选，已确认的产品被判成「提到了别的型号」
    而作废，产品卡再弹一次（T55 实测弹两次，run 5 与 run 7）。
    已确认的产品是更强的证据：要推翻它，得靠本轮原话里真的出现了别的型号，而不是靠一条旧线索。
    """
    cands = [c.model_dump() for c in catalog.lookup_product(text)]
    if not cands:
        seen: set[str] = set()
        for h in hints:
            for c in catalog.lookup_product(h):
                if c.sku not in seen:
                    seen.add(c.sku)
                    cands.append(c.model_dump())
    return cands


# ---------------------------------------------------------------------------
# 追问文案
# ---------------------------------------------------------------------------


def fixed_question(reason: str, detail: dict[str, Any]) -> str:
    if reason == "product" and detail.get("expected_category"):
        return f"The device in the photo looks like a {detail['category_name']}. Is that right?"
    if reason == "product" and detail.get("unmatched_hints"):
        return "I couldn't match that model to our product list. Could you tell me the product type, or send a photo of the model label on the device?"
    tpl = FIXED_QUESTIONS.get(reason, FIXED_QUESTIONS["product"])
    try:
        return tpl.format(**detail)
    except (KeyError, IndexError):
        return FIXED_QUESTIONS["product"]


CLARIFY_INSTRUCTION = {
    "product": "当前信息尚未匹配到可用的产品或品类。结合历史问答，只追问仍缺少的信息；用户已提供型号但未匹配时，先说明已收到且目录未匹配，再请补充品类或机身型号标签，不要重复询问已回答的型号。不要给排查步骤，不要猜测型号。",
    "symptom": "设备已确认，但用户没有描述具体故障现象。请只输出一句具体的英文追问，给出两三个该类设备的常见现象让用户选择；不要给排查步骤。",
    "conflict": "用户之前确认的产品与这次提到的产品不一致。请只输出一句具体的英文追问，请用户确认要排查的是哪一台；不要给排查步骤。",
}


def build_messages(
    reason: str, text: str, *, strategy: str, summary: dict[str, Any] | None, detail: dict[str, Any]
) -> list[tuple[str, str]]:
    ctx = ""
    if reason == "conflict":
        ctx = f"之前确认：{detail.get('confirmed')}；这次提到：{detail.get('mentioned')}。"
    elif reason == "product" and detail.get("unmatched_hints"):
        ctx = wrap_data("、".join(detail["unmatched_hints"]), kind="unmatched_product_hints")
    return [
        ("system", compose_system_prompt(strategy, summary)),
        (
            "human",
            wrap_data(state_layer(summary or {}), kind="session_state")
            + f'{CLARIFY_INSTRUCTION[reason]}{ctx}\n只输出 JSON：{{"question": "..."}}\n{wrap_data(text)}',
        ),
    ]


@dataclass
class QuestionOutcome:
    text: str
    model_used: str  # skipped / fixed / 模型名
    model_trace: dict[str, Any] | None = None


# 同一句判别问题再问一次时先承接一下。一字不差地复读读起来像没听见（2026-09-16 实测）。
# 只改呈现：问题原文与 question_id 保持不变，模型仍按原文引用，状态里也不多一个字段。
REPEAT_LEAD = "Thanks, noted. I still need one thing first: "


def render_question(reason: str, detail: dict[str, Any], *, previous: str | None = None) -> str:
    text = fixed_question(reason, detail)
    return REPEAT_LEAD + text if previous and previous.endswith(text) else text


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
    previous_question: str | None = None,
) -> QuestionOutcome:
    # Preserve the existing async call signature for callers and historical tooling.
    return QuestionOutcome(render_question(reason, detail, previous=previous_question), "fixed")
