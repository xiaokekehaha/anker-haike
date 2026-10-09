"""步骤卡准备（票 34；03 §1.5、09 §1 / §2.5 / §3.2）。

1. 取 plan_cursor 指向的步骤，instruction_src 原文来自官方 Q&A 生成的计划证据索引（app/plans/qa.py）。
2. evidence_ids = 当前允许证据集合中与 instruction_src 同一条 Q&A 的条目 + diagnose 为该计划给出的证据；
   若步骤引用了允许集合外的 id → 丢弃该步骤取下一步（09 §2.5）。
2b. primary_evidence_id = 这一步出自的那条官方 Q&A：本轮已有（错误码精确命中或检索命中）就用它，
   没有才本地发布 Q&A 原文。
3. CP-pre-step：文字含 R4 或含高危动作且无 caution → 丢弃取下一步。
4. 原样发布已审核操作；停止条件独立附在 caution 中，不参与用户风险判定。
card_id = uuid5(session_id, plan_id, step_id)，重跑稳定。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.conversation.operation_conditions import execution_history, step_unavailable
from app.models.router import ModelRouter
from app.plans.library import PlanLibrary
from app.plans.models import Plan, PlanStep
from app.plans.qa import customer_voice
from app.rules.service import RulesService

NS = uuid.UUID("2b0f5a9e-64c2-4c7d-9c0a-7f3d1e6a8b21")
GUIDE_BUDGET_MS = 6000


def step_card_id(session_id: str, plan_id: str, step_id: str) -> str:
    return uuid.uuid5(NS, f"{session_id}|{plan_id}|{step_id}").hex


@dataclass
class StepPrep:
    outcome: str  # ready | exhausted | blocked
    step: dict[str, Any] | None = None  # 契约 TroubleshootStep 形状
    card_id: str | None = None
    plan_cursor: dict[str, Any] | None = None
    dropped: list[dict[str, Any]] = field(default_factory=list)
    rewritten: bool = False
    model_trace: dict[str, Any] | None = None
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    # 主引用从哪儿来：qa_exact / kb_qa 表示本轮已有这条 Q&A，none 表示退回本地发布
    anchor: dict[str, Any] | None = None


def _evidence_for(
    step: PlanStep,
    plan: Plan,
    allowed_evidence: dict[str, dict[str, Any]],
    ranked_evidence: list[str],
) -> list[str]:
    """步骤引用的证据：同一条 Q&A 的允许条目 + diagnose 为该计划给出的 evidence_ids。

    前者天然在允许集合内；后者来自模型输出，可能越界，由调用方校验后丢弃该步骤（09 §2.5）。
    """
    doc_id = step.evidence_key.split("#", 1)[0]
    ids = [eid for eid, e in allowed_evidence.items() if e.get("doc_id") == doc_id]
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
    product = state.get("product_confirmed") or {}
    if not plan.applies(category=state.get("category") or product.get("category"), sku=product.get("sku")):
        return StepPrep("exhausted", dropped=[{"plan_id": plan.plan_id, "reason": "plan_model_mismatch"}])
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
    executed_src = {s.get("instruction_src") for s in execution_history(state)}
    dropped: list[dict[str, Any]] = []
    while step_id is not None:
        step = plan.step(step_id)
        unavailable = step_unavailable(state, plan.plan_id, step)
        if unavailable:
            return StepPrep("blocked", dropped=[*dropped, {
                "plan_id": plan.plan_id, "step_id": step_id, "reason": unavailable,
            }])
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
            instruction=source_text, title=step.title, caution=step.caution, session_id=session_id,
            conditional_notice=source_text in step.stop_conditions,
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
        primary_id, published_evidence, anchor_match = _primary_evidence(
            step, library, source_text, allowed_evidence
        )
        if published_evidence:
            evidence_ids = sorted({*evidence_ids, *published_evidence})
        card_id = step_card_id(session_id, plan.plan_id, step_id)
        return StepPrep(
            "ready",
            step={
                "step_id": step.step_id,
                "plan_id": plan.plan_id,
                "plan_version": plan.version,
                "step_no": step_no_of(plan, step_id),
                "title": customer_voice(step.title),
                "instruction": customer_voice(source_text),
                "expected_result": step.expected_result,
                "caution": "；".join(filter(None, [step.caution, *[c for c in step.stop_conditions if c != source_text]])) or None,
                "evidence_ids": evidence_ids,
                "primary_evidence_id": primary_id,
                "media": step_media(plan.plan_id, step_id),
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
            anchor={
                "evidence_key": step.evidence_key,
                "match": anchor_match,
                "primary_evidence_id": primary_id,
                "retrieved": not published_evidence,
            },
        )
    return StepPrep("exhausted", dropped=dropped)


def _primary_evidence(
    step: PlanStep,
    library: PlanLibrary,
    source_text: str,
    allowed_evidence: dict[str, dict[str, Any]],
) -> tuple[str, dict[str, dict[str, Any]], str]:
    """这一步的主引用：本轮已有的同一条官方 Q&A（错误码精确命中优先，其次检索命中），没有才本地发布。

    返回 (primary_evidence_id, 需要额外发布的证据, 命中方式 qa_exact / kb_qa / none)。
    一条 Q&A 入库为一个知识、基本一块，doc_id 即 qa_id，按 doc_id 认就是这一步的出处，
    不必像手册那样按小节锚点在同文档的多块里认人。认不出（检索没召回、知识库不可用）时
    本地发布 Q&A 原文：原文即便检索挂了也应当可查，调用方记 anchor_not_retrieved 以便归因。
    """
    doc_id, chunk_id = step.evidence_key.split("#", 1)
    same = [(eid, e) for eid, e in allowed_evidence.items() if e.get("doc_id") == doc_id]
    for source in ("qa_exact", "kb_qa"):
        found = next((eid for eid, e in same if e.get("source") == source), None)
        if found is not None:
            return found, {}, source
    source = library.evidence[step.evidence_key]
    pid = f"plan:{step.evidence_key}:{source.doc_version}"
    return (
        pid,
        {
            pid: {
                "evidence_id": pid,
                "source": "approved_plan",
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "doc_version": source.doc_version,
                "snippet": source_text,
                "score": 1.0,
                "status": "ok",
            }
        },
        "none",
    )


def step_media(plan_id: str, step_id: str) -> list[dict[str, str]]:
    """官方 Q&A 步骤附带的图片 / 视频链接；非 Q&A 计划（测试夹具）为空。"""
    from app.plans.qa import guide_of

    guide = guide_of(plan_id)
    if guide is None:
        return []
    index = int(step_id.removeprefix("s")) - 1 if step_id.startswith("s") and step_id[1:].isdigit() else -1
    media = guide.steps[index].media if guide.kind == "steps" and 0 <= index < len(guide.steps) else guide.media
    return [{"url": m.url, "kind": m.kind} for m in media]


def step_no_of(plan: Plan, step_id: str) -> int:
    return next(i for i, s in enumerate(plan.steps, 1) if s.step_id == step_id)
