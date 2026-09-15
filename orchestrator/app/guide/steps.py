"""步骤卡准备（票 34；03 §1.5、09 §1 / §2.5 / §3.2）。

1. 取 plan_cursor 指向的步骤，instruction_src 原文来自 plans.yaml 的证据索引（已审核文本）。
2. evidence_ids = 当前允许证据集合中与 instruction_src 同 doc 的条目 + 命中该计划的故障卡证据；
   若步骤引用了允许集合外的 id → 丢弃该步骤取下一步（09 §2.5）。
3. CP-pre-step：文字含 R4 或含高危动作且无 caution → 丢弃取下一步。
4. 原样发布已审核操作；停止条件独立附在 caution 中，不参与用户风险判定。
card_id = uuid5(session_id, plan_id, step_id)，重跑稳定。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.models.router import ModelRouter
from app.plans.library import PlanLibrary
from app.plans.models import Plan, PlanStep
from app.rules.service import RulesService

NS = uuid.UUID("2b0f5a9e-64c2-4c7d-9c0a-7f3d1e6a8b21")
GUIDE_BUDGET_MS = 6000


def step_card_id(session_id: str, plan_id: str, step_id: str) -> str:
    return uuid.uuid5(NS, f"{session_id}|{plan_id}|{step_id}").hex


@dataclass
class StepPrep:
    outcome: str  # ready | exhausted
    step: dict[str, Any] | None = None  # 契约 TroubleshootStep 形状
    card_id: str | None = None
    plan_cursor: dict[str, Any] | None = None
    dropped: list[dict[str, Any]] = field(default_factory=list)
    rewritten: bool = False
    model_trace: dict[str, Any] | None = None
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)


def _evidence_for(
    step: PlanStep,
    plan: Plan,
    allowed_evidence: dict[str, dict[str, Any]],
    ranked_evidence: list[str],
) -> list[str]:
    """步骤引用的证据：同 doc 的允许条目 + 命中该计划的故障卡 + diagnose 为该计划给出的 evidence_ids。

    前两类天然在允许集合内；第三类来自模型输出，可能越界，由调用方校验后丢弃该步骤（09 §2.5）。
    """
    doc_id = step.evidence_key.split("#", 1)[0]
    ids = [eid for eid, e in allowed_evidence.items() if e.get("doc_id") == doc_id]
    ids += [
        eid
        for eid, e in allowed_evidence.items()
        if e.get("source") == "fault_card" and e.get("chunk_id") == plan.plan_id
    ]
    ids += list(ranked_evidence)
    return sorted(set(ids))


def _advance_in_plan(plan: Plan, step_id: str) -> str | None:
    """步骤被丢弃时的「取下一步」：按 not_solved 路径推进；到 DONE / EXHAUSTED 返回 None。"""
    nxt = plan.next_step_id(step_id, "not_solved")
    return None if nxt in ("DONE", "EXHAUSTED") else nxt


async def prepare_step(
    *,
    state: dict[str, Any],
    library: PlanLibrary,
    rules: RulesService,
    router: ModelRouter | None,
    lane: str,
    session_id: str,
    budget_ms: int = GUIDE_BUDGET_MS,
) -> StepPrep:
    """校验并发布已审核步骤；router/budget 参数保留以兼容现有编排接口。"""
    cursor = dict(state.get("plan_cursor") or {})
    if not cursor.get("plan_id"):
        return StepPrep("exhausted")
    plan = library.get(cursor["plan_id"])
    step_id = cursor.get("step_id") or plan.first_step().step_id
    allowed_evidence: dict[str, dict[str, Any]] = dict(state.get("evidence") or {})
    ranked_evidence = next(
        (
            list(p.get("evidence_ids") or [])
            for p in state.get("plans_ranked") or []
            if p.get("plan_id") == plan.plan_id
        ),
        [],
    )
    executed_src = {s.get("instruction_src") for s in state.get("steps_executed") or []}
    dropped: list[dict[str, Any]] = []
    while step_id is not None:
        step = plan.step(step_id)
        # 跨计划去重：与已执行步骤 instruction_src 相同 → 跳过（09 §3.4）
        if step.instruction_src in executed_src:
            dropped.append(
                {"plan_id": plan.plan_id, "step_id": step_id, "reason": "duplicate_instruction_src"}
            )
            step_id = _advance_in_plan(plan, step_id)
            continue
        source_text = library.evidence_snippet(step.instruction_src)
        evidence_ids = _evidence_for(step, plan, allowed_evidence, ranked_evidence)
        bad = [e for e in evidence_ids if e not in allowed_evidence]
        if bad:
            dropped.append(
                {
                    "plan_id": plan.plan_id,
                    "step_id": step_id,
                    "reason": f"evidence_out_of_scope:{','.join(bad)}",
                }
            )
            step_id = _advance_in_plan(plan, step_id)
            continue
        pre = rules.check_pre_step(
            instruction=source_text, title=step.title, caution=step.caution, session_id=session_id
        )
        if pre.action == "drop":
            dropped.append(
                {
                    "plan_id": plan.plan_id,
                    "step_id": step_id,
                    "reason": (
                        f"safety_term_in_step:{pre.term}"
                        if pre.rule_id == "R4"
                        else f"high_risk_without_caution:{pre.term}"
                    ),
                }
            )
            step_id = _advance_in_plan(plan, step_id)
            continue
        # Local approved sources remain inspectable even if retrieval is down.
        # They are publication evidence, not model-proposed or user-reported facts.
        doc_id, chunk_id = step.evidence_key.split("#", 1)
        source = library.evidence[step.evidence_key]
        published_evidence = {}
        if not any(
            e.get("doc_id") == doc_id
            and e.get("chunk_id") == chunk_id
            and e.get("snippet") == source_text
            for e in allowed_evidence.values()
        ):
            eid = f"plan:{step.evidence_key}:{source.doc_version}"
            published_evidence[eid] = {
                "evidence_id": eid,
                "source": "approved_plan",
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "doc_version": source.doc_version,
                "snippet": source_text,
                "score": 1.0,
                "status": "ok",
            }
            evidence_ids = sorted({*evidence_ids, eid})
        card_id = step_card_id(session_id, plan.plan_id, step_id)
        return StepPrep(
            "ready",
            step={
                "step_id": step.step_id,
                "plan_id": plan.plan_id,
                "plan_version": plan.version,
                "step_no": step_no_of(plan, step_id),
                "title": step.title,
                "instruction": source_text,
                "expected_result": step.expected_result,
                "caution": "；".join(filter(None, [step.caution, *step.stop_conditions])) or None,
                "evidence_ids": evidence_ids,
            },
            card_id=card_id,
            plan_cursor={
                "plan_id": plan.plan_id,
                "version": plan.version,
                "step_id": step_id,
                "source": cursor.get("source"),
            },
            dropped=dropped,
            evidence=published_evidence,
        )
    return StepPrep("exhausted", dropped=dropped)


def step_no_of(plan: Plan, step_id: str) -> int:
    return next(i for i, s in enumerate(plan.steps, 1) if s.step_id == step_id)
