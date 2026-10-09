"""diagnose.synthesize（03 §1.4 步骤 3；09 §3.2）：强推理档、tag=internal，输出最多 3 个假设。

每个假设必须引用当前允许集合内的 plan_id（枚举由 PlanLibrary.allowed_for 决定）与状态里已有的 evidence_ids；
不在枚举内的 plan_id 丢弃并记录，无效 evidence_id 剔除。无证据（no_match / unavailable）时不调模型，
按候选（本轮命中的官方 Q&A，已按检索顺序）给出 plans_ranked 并标注来源 retrieval_order。
"""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from app.knowledge.context import render_evidence
from app.models.queue import CapacityExceeded
from app.models.router import ModelInvokeError, ModelRouter
from app.plans.models import Plan
from app.prompts import compose_system_prompt, wrap_data

log = logging.getLogger("diagnose.synthesize")


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: str = Field(description="只能是允许列表中的计划 id")
    confidence: float = Field(ge=0, le=1)
    applicability: Literal["supported", "needs_confirmation", "not_applicable"] = Field(
        description="证据是否支持用户的实际现象和必要条件；同型号或关键词接近不算支持"
    )
    supported_symptoms: list[str] = Field(description="逐字选择本次有效症状中该方案能解释的项目，未覆盖的不填")
    evidence_ids: list[str] = Field(
        default_factory=list, description="支撑该假设的证据 id，取自提供的片段"
    )
    rationale: str = Field(default="", max_length=80)
    clarification_question: str | None = Field(
        default=None, max_length=300,
        description="needs_confirmation 时用一句英文询问文档要求但尚未知的入口前提；只确认事实，不要求执行操作",
    )
    matched_subject: str | None = Field(default=None, max_length=80, description="该方案针对的部件或对象，摘自候选标题/正文原话")
    matched_timing: str | None = Field(default=None, max_length=80, description="该方案针对的时机或方向，摘自候选原话；没有留空")


class PlansRanked(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hypotheses: list[Hypothesis] = Field(default_factory=list, max_length=5)


def _schema_with_enum(plan_ids: list[str]) -> type[BaseModel]:
    """把 plan_id 收窄为枚举（09 §3.2）。"""
    if not plan_ids:
        return PlansRanked
    lit = Literal[tuple(plan_ids)]  # type: ignore[valid-type]
    hyp = create_model(
        "HypothesisEnum",
        __config__=ConfigDict(extra="forbid"),
        plan_id=(lit, Field(description="只能是允许列表中的计划 id")),
        confidence=(float, Field(ge=0, le=1)),
        applicability=(Literal["supported", "needs_confirmation", "not_applicable"], Field()),
        supported_symptoms=(list[str], Field()),
        evidence_ids=(list[str], Field(default_factory=list)),
        rationale=(str, Field(default="", max_length=80)),
        clarification_question=(str | None, Field(default=None, max_length=300)),
        matched_subject=(str | None, Field(default=None, max_length=80)),
        matched_timing=(str | None, Field(default=None, max_length=80)),
    )
    return create_model(
        "PlansRankedEnum",
        __config__=ConfigDict(extra="forbid"),
        hypotheses=(list[hyp], Field(default_factory=list, max_length=5)),
    )  # type: ignore[valid-type]


def default_plans_ranked(allowed: list[Plan], *, source: str = "retrieval_order") -> list[dict[str, Any]]:
    """无证据 / 模型不可用时的降级：候选按检索命中顺序（错误码精确命中在前），置信度统一 0.3，标注来源。"""
    return [
        {
            "plan_id": p.plan_id,
            "version": p.version,
            "confidence": 0.3,
            "evidence_ids": [],
            "source": source,
        }
        for p in allowed
    ]


# 用户说「提前 / 过早」而候选讲「没能启动」：同一个关键词（schedule）下两种相反的事实（T61）。
EARLY = ("before", "early", "earlier", "ahead", "too soon", "提前", "过早", "早了")
NOT_STARTED = ("failed to start", "not start", "won't start", "doesn't start", "did not start", "无法启动", "没有启动", "未启动")


def _norm(text: str | None) -> str:
    return " ".join((text or "").casefold().split())


def _timing_conflicts(user_timing: str, candidate_timing: str | None, candidate_title: str) -> bool:
    user = _norm(user_timing)
    cand = _norm(candidate_timing) + " " + _norm(candidate_title)
    early, failed = any(k in user for k in EARLY), any(k in user for k in NOT_STARTED)
    return (early and any(k in cand for k in NOT_STARTED)) or (failed and any(k in cand for k in EARLY))


# 「left one / my pump / the robot / stofzuiger」是整机或品类词，不是部件：候选讲滚刷、鸭嘴阀都是在说这台机器的某个部件，
# 不构成对象层级冲突。只有用户点名了具体部件（charging case、duckbill valve）才和候选的部件比对（T52 对 T55 / T36 / T62）。
_PART_WORDS = (
    "case", "hub", "motor", "valve", "shield", "bowl", "diaphragm", "bottle", "tube", "tubing", "hose", "cable", "charger",
    "adapter", "battery", "brush", "roller", "filter", "tank", "tray", "mop", "pad", "sensor", "wheel", "dock", "station",
    "base", "bin", "lid", "cover", "seal", "ring", "nozzle", "contact", "pin", "port", "light", "indicator", "button", "app",
    "map", "schedule", "wifi", "wi-fi", "firmware", "camera", "lens", "speaker",
    # 吸奶器的 pump hub 是盒子里的部件；单说「my pump」仍按整机（_is_part 先查目录品类词）
    "pump",
)
# 耗材与介质不是部件：「floor detergent」对「cleaning solution bottle / clean water tank」讲的是同一件事的容器与液位，
# 不能按中心词判成对象不同（T40）。它们不进 _PART_WORDS，中心词为空就不比对。
_DEVICE_WORDS = ("one", "unit", "device", "machine", "robot", "robovac", "vacuum", "hoover", "pump", "stofzuiger", "borstkolf", "camera")
_FILLER_WORDS = {"the", "my", "this", "it", "left", "right", "side", "eufy", "anker", "both", "either", "other"}


def _is_part(subject: str) -> bool:
    """主语是否指向某个部件，而不是整机、型号名或品类词。"""
    from app.sessions.cards import get_catalog

    norm = _norm(subject)
    words = set(re.findall(r"[a-z][a-z\-]+", norm))
    catalog = get_catalog()
    named_part = any(w in _PART_WORDS or w.rstrip("s") in _PART_WORDS for w in words if w not in _DEVICE_WORDS)
    # 「my pump」「the robot」「Eufy S1 pro breast pump」：目录认得出品类或型号、又没点名部件 → 整机（T54）
    if (catalog.category_hint(subject) or catalog.lookup_product(subject)) and not named_part:
        return False
    if named_part:
        return True
    return not (words <= set(_DEVICE_WORDS) | _FILLER_WORDS)


_PREPOSITIONS = (" in ", " on ", " of ", " inside ", " at ", " with ", " into ", " from ")


def _head_part(subject: str) -> str | None:
    """部件短语的中心词：「charging case」→ case、「cleaning tray」→ tray、「pump in the case」→ pump。
    介词前的是主语，介词后的只是位置修饰。"""
    norm = _norm(subject)
    for prep in _PREPOSITIONS:
        if prep in norm:
            norm = norm.split(prep, 1)[0]
            break
    parts = [w.rstrip("s") for w in re.findall(r"[a-z][a-z\-]+", norm) if w in _PART_WORDS or w.rstrip("s") in _PART_WORDS]
    return parts[-1] if parts else None


def _subject_conflicts(user_subject: str, candidate_subject: str) -> bool:
    user, cand = _norm(user_subject), _norm(candidate_subject)
    if not (user and cand) or user in cand or cand in user:
        return False
    if not _is_part(user_subject):
        return False
    # 「Water tray」对「cleaning tray」是同一类部件的不同叫法（T29），中心词相同不算冲突；
    # 「charging case」对「pump in the case」中心词是 case 对 pump，才是对象不同（T52）。
    user_head, cand_head = _head_part(user_subject), _head_part(candidate_subject)
    return user_head is not None and cand_head is not None and user_head != cand_head


CLARIFY_TEMPLATES = {
    "polarity_uncertain": 'You mentioned "{quote}". Which side or part has the problem, and what exactly is it doing?',
    "timing_mismatch": "You said it happened {timing}. Is that right, and does the app show any warning at that moment?",
    "subject_mismatch": "Is the problem with the {subject} itself (for example its own charging light or power input), or with how it works together with other parts?",
}


def filter_hypotheses(
    raw: list[dict[str, Any]], *, allowed: dict[str, Plan], evidence_ids: set[str], symptoms: set[str],
    facts: list[dict[str, Any]] = (), error_codes: list[str] = (), max_n: int,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    """模型的假设先过服务端核对，再决定可执行 / 待澄清 / 丢弃。

    返回 (kept, dropped, clarifications)。核对只用结构化事实（极性、对象、时机、错误码），
    不信模型对 applicability 的自评：同型号、关键词相近都不等于适用（T50 / T52 / T61）。
    """
    kept: list[dict[str, Any]] = []
    dropped: list[str] = []
    clarifications: list[dict[str, Any]] = []
    seen: set[str] = set()
    by_value = {f.get("value"): f for f in facts if f.get("kind") == "symptom" and f.get("status", "active") == "active"}
    codes = {c.upper() for c in error_codes}

    def clarify(h, reason, question):
        ev = [e for e in (h.get("evidence_ids") or []) if e in evidence_ids]
        if not ev or not question:
            return
        if codes and any(code.casefold() in question.casefold() for code in codes):
            return  # 不问用户已经告诉我们的错误码（T18）
        clarifications.append({"plan_id": h["plan_id"], "question": question.strip(), "evidence_ids": ev,
                               "confidence": float(h.get("confidence", 0)), "reason": reason})

    for h in raw:
        pid = h.get("plan_id")
        if pid not in allowed:
            dropped.append(f"plan_id:{pid}")
            continue
        if pid in seen:
            dropped.append(f"duplicate:{pid}")
            continue
        seen.add(pid)
        plan = allowed[pid]
        if codes and plan.symptom_codes and not codes.intersection(c.upper() for c in plan.symptom_codes):
            dropped.append(f"code_mismatch:{pid}")  # 同型号异码不是候选，也不值得追问
            continue
        covered = list(dict.fromkeys(s for s in h.get("supported_symptoms", []) if s in symptoms))
        covered_facts = [by_value[s] for s in covered if s in by_value]
        uncertain = next((f for f in covered_facts if f.get("polarity") == "uncertain"), None)
        if uncertain:
            dropped.append(f"polarity_uncertain:{pid}")
            clarify(h, "polarity_uncertain", CLARIFY_TEMPLATES["polarity_uncertain"].format(quote=uncertain.get("quote") or uncertain["value"]))
            continue
        timed = next((f for f in covered_facts if f.get("timing") and _timing_conflicts(f["timing"], h.get("matched_timing"), plan.fault)), None)
        if timed:
            dropped.append(f"timing_mismatch:{pid}")
            clarify(h, "timing_mismatch", CLARIFY_TEMPLATES["timing_mismatch"].format(timing=timed["timing"]))
            continue
        mismatched = next((f for f in covered_facts if f.get("subject") and h.get("matched_subject")
                           and _subject_conflicts(f["subject"], h["matched_subject"])), None)
        if mismatched:
            dropped.append(f"subject_mismatch:{pid}")
            clarify(h, "subject_mismatch", CLARIFY_TEMPLATES["subject_mismatch"].format(subject=mismatched["subject"]))
            continue
        if h.get("applicability") != "supported":
            dropped.append(f"not_supported:{pid}")
            if h.get("applicability") == "needs_confirmation":
                clarify(h, "needs_confirmation", h.get("clarification_question") or "")
            continue
        if not covered:
            dropped.append(f"no_supported_symptom:{pid}")
            continue
        ev = [e for e in (h.get("evidence_ids") or []) if e in evidence_ids]
        bad = [e for e in (h.get("evidence_ids") or []) if e not in evidence_ids]
        if bad:
            dropped.append(f"evidence:{pid}:{','.join(bad)}")
        if not ev:
            dropped.append(f"no_evidence:{pid}")
            continue
        kept.append(
            {
                "plan_id": pid,
                "version": plan.version,
                "confidence": round(float(h.get("confidence", 0)), 3),
                "evidence_ids": ev,
                "rationale": (h.get("rationale") or "")[:80],
                "supported_symptoms": covered,
                "source": "synthesize",
            }
        )
    kept.sort(key=lambda x: -x["confidence"])
    clarifications.sort(key=lambda item: -item["confidence"])
    return kept[:max_n], dropped, clarifications


INSTRUCTION = (
    "根据 <data> 段中的用户描述、图片观察与检索片段，从「允许的排障计划」里选出最可能的假设，最多 {n} 个：\n"
    "- plan_id 只能取允许列表中的值；每个假设至少引用一条支撑它的 evidence_id（只能用给出的 id）；\n"
    "- confidence 为 0–1；rationale 不超过 40 字；不要编造检索片段里没有的现象或原因；\n"
    "- 标为「未解决工单」的片段只说明该次服务未确认解决，不能作为方案依据，只可用作反证；\n"
    "- 先判断 applicability：supported 必须是同一现象且必要前提已成立；前提未知用 needs_confirmation；现象矛盾用 not_applicable。\n"
    "- 入口前提是用户观察到的现象/操作条件，不是尚待检查的故障原因。步骤本来用于检查某个可能原因时，不要求用户先证明该原因。\n"
    "- needs_confirmation 必须填写 clarification_question：只问一个缺失的入口前提，用英文，不给操作指令；结合上一问和本轮回答，已回答的不重复问。\n"
    "- 必须区分方向、时间和结果，例如提前发生与未能发生、始终离线与偶发离线不能仅凭共享关键词相互代用。\n"
    "- 文档有错误码而用户没有提供错误码，不是拒绝依据；用户现象和文档适用条件一致仍可 supported。\n"
    "- supported_symptoms 只能逐字选择给定的有效症状；不能把共同主题当作覆盖，不能声称一个方案解决所有并列问题。\n"
    "- matched_subject / matched_timing 摘自候选标题或正文：该方案针对哪个部件、哪种时机；structured_facts 里用户的 subject / timing 与之不同层级或方向相反时不是 supported。\n"
    "- action_taken 是用户已经做过的操作；候选只是重复这些动作则 not_applicable，否则在 rationale 里说明新增的检查点。\n"
    "- 没有任何计划能解释时输出空列表。只输出 JSON。"
)

def active_facts(state: dict[str, Any]) -> list[dict[str, Any]]:
    issue = (state.get("issues") or {}).get(state.get("active_issue_id"), {})
    return [f for f in issue.get("facts", []) if f.get("status") == "active"]


async def synthesize(
    router: ModelRouter | None,
    *,
    state: dict[str, Any],
    allowed: list[Plan],
    evidence: list[dict[str, Any]],
    observations: list[str],
    budget_ms: int,
    max_hypotheses: int,
    session_id: str | None,
    lane: str,
) -> dict[str, Any]:
    """evidence 由检索上下文层选择并预算；输入、引用白名单与模型实际可见集合一致。"""
    allowed_by_id = {p.plan_id: p for p in allowed}
    if not allowed:
        return {
            "plans_ranked": [],
            "dropped": [],
            "model_trace": None,
            "degraded": "no_allowed_plans",
        }
    if not evidence or router is None:
        reason = "no_evidence" if not evidence else "router_unavailable"
        return {
            "plans_ranked": default_plans_ranked(allowed),
            "dropped": [],
            "model_trace": {
                "task": "diagnose.synthesize",
                "model_used": "skipped",
                "lane": lane,
                "attempts": 1,
            },
            "degraded": reason,
        }
    plans_text = "\n".join(f"- {p.plan_id}：{p.fault}（首步：{p.steps[0].title}）" for p in allowed)
    ev_text = "\n".join(render_evidence(e) for e in evidence)
    obs_text = "\n".join(observations) if observations else "（无图片观察）"
    symptoms = list(dict.fromkeys(str(s) for s in [*(state.get("symptoms") or []), *observations] if str(s).strip()))
    facts = active_facts(state)
    error_codes = list(state.get("error_codes") or [])
    facts_text = "\n".join(
        f"- kind={f.get('kind')} subject={f.get('subject') or '-'} polarity={f.get('polarity', 'affirmed')} "
        f"timing={f.get('timing') or '-'} value={f.get('value')}"
        for f in facts
    ) or "（无）"
    human = (
        INSTRUCTION.format(n=max_hypotheses)
        + f"\n允许的排障计划：\n{plans_text}\n"
        + "有效症状（supported_symptoms 只能逐字选取）：\n" + wrap_data("\n".join(symptoms), kind="active_symptoms") + "\n"
        + wrap_data(facts_text, kind="structured_facts") + "\n"
        + wrap_data(", ".join(error_codes) or "（无）", kind="error_codes") + "\n"
        + wrap_data(
            " ".join(
                [str(s) for s in state.get("symptoms") or []]
            ),
            kind="user_message",
        )
        + "\n"
        + wrap_data(obs_text, kind="image_observations")
        + "\n"
        + wrap_data(str(state.get("observations") or []), kind="confirmed_observations")
        + "\n"
        + wrap_data(
            str({"question": (state.get("diagnose_outcome") or {}).get("question"),
                 "answer": state.get("text")}), kind="current_turn",
        )
        + "\n"
        + wrap_data(ev_text, kind="retrieved_snippets")
    )
    messages = [
        (
            "system",
            compose_system_prompt(
                (state.get("emotion") or {}).get("strategy", "normal"),
                {
                    "stage": "diagnose",
                    "product": (state.get("product_confirmed") or {}).get("name"),
                    "symptoms": state.get("symptoms"),
                },
            ),
        ),
        ("human", human),
    ]
    # 宽松解析再按枚举过滤：单个越界 plan_id 只丢弃该假设，不让整批作废（枚举写在提示里；
    # _schema_with_enum 供原生 json_schema 模型或票 33 严格模式选用）
    try:
        res = await router.invoke(
            "diagnose.synthesize",
            messages,
            PlansRanked,
            budget_ms=budget_ms,
            session_id=session_id,
            lane=lane,
        )
        raw = [
            h.model_dump() if isinstance(h, BaseModel) else dict(h) for h in res.parsed.hypotheses
        ]
        trace = {
            "task": "diagnose.synthesize",
            "model_used": res.model_used,
            "lane": res.lane,
            "attempts": max(1, sum(1 for a in res.attempts if a.outcome != "skipped")),
        }
    except (ModelInvokeError, CapacityExceeded, ValidationError) as exc:
        attempts = [f"{a.alias}:{a.outcome}:{a.error}" for a in getattr(exc, "attempts", [])]
        log.warning(
            "synthesize degraded session=%s: %s attempts=%s", session_id, str(exc)[:200], attempts
        )
        return {
            "plans_ranked": default_plans_ranked(allowed),
            "dropped": [],
            "attempts": attempts,
            "model_trace": {
                "task": "diagnose.synthesize",
                "model_used": "skipped",
                "lane": lane,
                "attempts": 1,
            },
            "degraded": f"model:{type(exc).__name__}",
        }
    # 前提未知不能成为可执行计划，但有官方证据的候选可以发起事实澄清。
    kept, dropped, clarifications = filter_hypotheses(
        raw,
        allowed=allowed_by_id,
        evidence_ids={e["evidence_id"] for e in evidence},
        symptoms=set(symptoms),
        facts=facts,
        error_codes=error_codes,
        max_n=max_hypotheses,
    )
    for d in dropped:
        log.info(
            "synthesize dropped hypothesis session=%s %s",
            session_id,
            d,
            extra={"event": "hypothesis_dropped", "detail": d, "session_id": session_id},
        )
    if not kept:
        return {
            "plans_ranked": [],
            "dropped": dropped,
            "model_trace": trace,
            "degraded": "no_applicable_plan",
            "clarifications": clarifications[:1],
        }
    return {"plans_ranked": kept, "dropped": dropped, "model_trace": trace, "degraded": None}
