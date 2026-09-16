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
    "product": "请告诉我设备的品类，例如扫地机器人、吸奶器或充电宝；知道型号也可以一起提供。",
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
            if category and category in catalog.categories:
                spec = catalog.categories.get(category)
                update.update(
                    {
                        "product_state": "category_only",
                        "product_confirmed": None,
                        "category": category,
                        "out_of_scope": bool(spec is not None and not spec.in_scope),
                    }
                )
            else:
                update["product_state"] = "unknown"
                visual_category = visual.get("category")
                spec = catalog.categories.get(visual_category)
                return _clarify(clar, "product", update, unmatched_hints=hints,
                                known_symptoms=sorted(set(state.get("symptom_codes") or state.get("symptoms") or [])),
                                expected_category=visual_category if spec else None,
                                category_name=spec.name if spec else None)

    if update.get("out_of_scope"):
        return Decision("continue", update)

    # One diagnostic decision consumes accepted facts and quoted answers.
    from app.diagnose.decision import decide_symptoms
    product = confirmed or {}
    decision = decide_symptoms({**state, **update}, available_plans=get_plans().allowed_for(
        category=product.get("category") or update.get("category") or category,
        sku=product.get("sku"),
    ))
    update["symptom_codes"] = decision.codes
    update["diagnostic_decision"] = decision.snapshot(state)
    if decision.outcome == "continue":
        update["clarification"] = None
        return Decision("continue", update)
    if decision.outcome == "escalate":
        coverage_missing = decision.reason == "question_coverage_missing"
        rule_id = "R4" if decision.reason == "safety_restriction" else "R5" if coverage_missing else "R7"
        update.update(escalate_reason=rule_id, symptom_interview=decision.interview,
                      clarification={**clar, "reason": "symptom", "resolved": False},
                      observations=[*state.get("observations", []),
                                    "仍需核对的信息：" + "；".join(decision.missing_information) if decision.missing_information else "当前无法继续排查"])
        return Decision("escalate", update, "symptom")
    if decision.interview is None:
        return _clarify(clar, "symptom", update)
    # Product clarification budget is separate from useful symptom questions.
    # 上一次真正问出去的那句话要留着：clarify 节点靠它认出「同一个问题又要问一遍」。
    update["clarification"] = {"reason": "symptom", "attempts": int(clar.get("attempts") or 0),
                               **({"question": clar["question"]} if clar.get("question") else {})}
    return Decision("clarify", update, "symptom", {
        "symptom_interview": decision.interview,
        "discriminator": decision.interview.get("question"),
    })


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


# ---------------------------------------------------------------------------
# 追问文案
# ---------------------------------------------------------------------------


def fixed_question(reason: str, detail: dict[str, Any]) -> str:
    if detail.get("discriminator"):
        return detail["discriminator"]["question"]
    if reason == "product" and detail.get("expected_category"):
        return f"照片中的设备看起来是{detail['category_name']}，请确认是这个品类吗？"
    if reason == "product" and detail.get("unmatched_hints"):
        return "您提供的型号暂未匹配到产品目录。请补充设备品类，或拍一张机身型号标签。"
    if reason == "symptom":
        from app.conversation.taxonomy import discriminator, taxonomy
        question = discriminator(detail.get("fault_families") or [f["fault_family"] for f in taxonomy()["families"]])
        if question:
            return question
    tpl = FIXED_QUESTIONS.get(reason, FIXED_QUESTIONS["product"])
    try:
        return tpl.format(**detail)
    except (KeyError, IndexError):
        return FIXED_QUESTIONS["product"]


CLARIFY_INSTRUCTION = {
    "product": "当前信息尚未匹配到可用的产品或品类。结合历史问答，只追问仍缺少的信息；用户已提供型号但未匹配时，先说明已收到且目录未匹配，再请补充品类或机身型号标签，不要重复询问已回答的型号。不要给排查步骤，不要猜测型号。",
    "symptom": "设备已确认，但用户没有描述具体故障现象。请只输出一句具体的中文追问，给出两三个常见现象让用户选择（如吸力变弱 / 无法启动 / 异响）；不要给排查步骤。",
    "conflict": "用户之前确认的产品与这次提到的产品不一致。请只输出一句具体的中文追问，请用户确认要排查的是哪一台；不要给排查步骤。",
}


def build_messages(
    reason: str, text: str, *, strategy: str, summary: dict[str, Any] | None, detail: dict[str, Any]
) -> list[tuple[str, str]]:
    ctx = ""
    if reason == "conflict":
        ctx = f"之前确认：{detail.get('confirmed')}；这次提到：{detail.get('mentioned')}。"
    elif reason == "product" and detail.get("unmatched_hints"):
        ctx = wrap_data("、".join(detail["unmatched_hints"]), kind="unmatched_product_hints")
    if detail.get("discriminator"):
        ctx += "原样保留下列核心问题，只允许在前面加一句简短引导，不增加其他问题或选项：" + detail["discriminator"]["question"]
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
REPEAT_LEAD = "您说的我记下了。还需要先确认一项："


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
