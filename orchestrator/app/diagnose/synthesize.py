"""diagnose.synthesize（03 §1.4 步骤 3；09 §3.2）：强推理档、tag=internal，输出最多 3 个假设。

每个假设必须引用当前允许集合内的 plan_id（枚举由 PlanLibrary.allowed_for 决定）与状态里已有的 evidence_ids；
不在枚举内的 plan_id 丢弃并记录，无效 evidence_id 剔除。无证据（no_match / unavailable）时不调模型，
按适用预写计划默认顺序给出 plans_ranked 并标注来源 standard_flow（09 §4）。
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from app.models.queue import CapacityExceeded
from app.models.router import ModelInvokeError, ModelRouter
from app.plans.models import Plan
from app.prompts import compose_system_prompt, wrap_data

log = logging.getLogger("diagnose.synthesize")


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: str = Field(description="只能是允许列表中的计划 id")
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(
        default_factory=list, description="支撑该假设的证据 id，取自提供的片段"
    )
    rationale: str = Field(default="", max_length=80)


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
        evidence_ids=(list[str], Field(default_factory=list)),
        rationale=(str, Field(default="", max_length=80)),
    )
    return create_model(
        "PlansRankedEnum",
        __config__=ConfigDict(extra="forbid"),
        hypotheses=(list[hyp], Field(default_factory=list, max_length=5)),
    )  # type: ignore[valid-type]


def default_plans_ranked(
    allowed: list[Plan], *, source: str = "standard_flow"
) -> list[dict[str, Any]]:
    """无证据 / 模型不可用时的降级：适用预写计划默认顺序，置信度统一 0.3，标注来源。"""
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


def filter_hypotheses(
    raw: list[dict[str, Any]], *, allowed: dict[str, Plan], evidence_ids: set[str], max_n: int
) -> tuple[list[dict[str, Any]], list[str]]:
    kept: list[dict[str, Any]] = []
    dropped: list[str] = []
    seen: set[str] = set()
    for h in raw:
        pid = h.get("plan_id")
        if pid not in allowed:
            dropped.append(f"plan_id:{pid}")
            continue
        if pid in seen:
            dropped.append(f"duplicate:{pid}")
            continue
        ev = [e for e in (h.get("evidence_ids") or []) if e in evidence_ids]
        bad = [e for e in (h.get("evidence_ids") or []) if e not in evidence_ids]
        if bad:
            dropped.append(f"evidence:{pid}:{','.join(bad)}")
        if not ev:
            dropped.append(f"no_evidence:{pid}")
            continue
        seen.add(pid)
        kept.append(
            {
                "plan_id": pid,
                "version": allowed[pid].version,
                "confidence": round(float(h.get("confidence", 0)), 3),
                "evidence_ids": ev,
                "rationale": (h.get("rationale") or "")[:80],
                "source": "synthesize",
            }
        )
    kept.sort(key=lambda x: -x["confidence"])
    return kept[:max_n], dropped


INSTRUCTION = (
    "根据 <data> 段中的用户描述、图片观察与检索片段，从「允许的排障计划」里选出最可能的假设，最多 {n} 个：\n"
    "- plan_id 只能取允许列表中的值；每个假设至少引用一条支撑它的 evidence_id（只能用给出的 id）；\n"
    "- confidence 为 0–1；rationale 不超过 40 字；不要编造检索片段里没有的现象或原因；\n"
    "- 标为「未解决工单」的片段只说明该次服务未确认解决，不能作为方案依据，只可用作反证；\n"
    "- 没有任何计划能解释时输出空列表。只输出 JSON。"
)

OUTCOME_LABELS = {"solved": "，已解决工单", "unsolved": "，未解决工单", "unknown": "，结果未知工单"}


def _evidence_text(e: dict[str, Any]) -> str:
    """阶段 4：有父块正文用父块（≤ 800 字），否则子块 snippet（≤ 300 字）。"""
    full = e.get("full_text")
    return str(full)[:800] if full else str(e.get("snippet", ""))[:300]


def _outcome_label(e: dict[str, Any]) -> str:
    """P0-4：工单结果标签；手册 / FAQ（n/a）与旧形状（无字段）不加。"""
    return OUTCOME_LABELS.get(str(e.get("case_outcome") or ""), "")


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
    """返回 {plans_ranked, dropped, model_trace, degraded}。"""
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
    ev_text = "\n".join(
        f"[{e['evidence_id']}] ({e.get('source')}{_outcome_label(e)}) {_evidence_text(e)}"
        for e in evidence[:12]
    )
    obs_text = "\n".join(observations) if observations else "（无图片观察）"
    human = (
        INSTRUCTION.format(n=max_hypotheses)
        + f"\n允许的排障计划：\n{plans_text}\n"
        + wrap_data(
            " ".join(
                [str(s) for s in state.get("symptoms") or []]
            ),
            kind="user_message",
        )
        + "\n"
        + wrap_data(obs_text, kind="image_observations")
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
    kept, dropped = filter_hypotheses(
        raw,
        allowed=allowed_by_id,
        evidence_ids={e["evidence_id"] for e in evidence},
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
            "plans_ranked": default_plans_ranked(allowed),
            "dropped": dropped,
            "model_trace": trace,
            "degraded": "all_dropped",
        }
    return {"plans_ranked": kept, "dropped": dropped, "model_trace": trace, "degraded": None}
