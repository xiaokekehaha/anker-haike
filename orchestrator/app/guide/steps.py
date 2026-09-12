"""步骤卡准备（票 34；03 §1.5、09 §1 / §2.5 / §3.2）。

1. 取 plan_cursor 指向的步骤，instruction_src 原文来自 plans.yaml 的证据索引（已审核文本）。
2. evidence_ids = 当前允许证据集合中与 instruction_src 同 doc 的条目 + 命中该计划的故障卡证据；
   若步骤引用了允许集合外的 id → 丢弃该步骤取下一步（09 §2.5）。
3. CP-pre-step：文字含 R4 → 升级；含高危动作且无 caution → 丢弃取下一步。
4. LLM（guide.step，internal）只改写为一句可执行话；动作词集合必须 ⊆ 原文，否则用原文。
card_id = uuid5(session_id, plan_id, step_id)，重跑稳定。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.queue import CapacityExceeded
from app.models.router import ModelInvokeError, ModelRouter
from app.plans.library import PlanLibrary
from app.plans.models import Plan, PlanStep
from app.prompts.guide import guide_messages
from app.rules.service import RulesService

log = logging.getLogger("guide.steps")
NS = uuid.UUID("2b0f5a9e-64c2-4c7d-9c0a-7f3d1e6a8b21")
GUIDE_BUDGET_MS = 6000
# 动作词干表：改写前后的动作集合必须相等（不得增删动作）。用词干而非完整词，避免「按下 / 按住」「装回 / 装上」
# 这类同义变体被误判为增删动作。
ACTION_VERBS = (
    "翻",
    "拆",
    "装",
    "取出",
    "清理",
    "割断",
    "冲洗",
    "清洗",
    "晾干",
    "更换",
    "关机",
    "断电",
    "重启",
    "按",
    "倒空",
    "擦",
    "检查",
    "移",
    "放回",
    "运行",
    "打开",
    "扳开",
    "抽出",
    "推入",
    "联系",
)


class StepRewrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instruction: str = Field(min_length=1, max_length=200)


def step_card_id(session_id: str, plan_id: str, step_id: str) -> str:
    return uuid.uuid5(NS, f"{session_id}|{plan_id}|{step_id}").hex


def action_verbs(text: str) -> set[str]:
    return {v for v in ACTION_VERBS if v in text}


def rewrite_is_faithful(source: str, rewritten: str) -> bool:
    """动作不增不删：改写后的动作词干集合与原文相同且非空。"""
    src, out = action_verbs(source), action_verbs(rewritten)
    return bool(out) and out == src


@dataclass
class StepPrep:
    outcome: str  # ready | exhausted | escalate
    step: dict[str, Any] | None = None  # 契约 TroubleshootStep 形状
    card_id: str | None = None
    plan_cursor: dict[str, Any] | None = None
    dropped: list[dict[str, Any]] = field(default_factory=list)
    escalate_reason: str | None = None
    rewritten: bool = False
    model_trace: dict[str, Any] | None = None


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
    """取 plan_cursor 指向的步骤并准备卡片；budget_ms ≤ 0 时跳过改写（08 §8 剩余不足跳过可选 task）。"""
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
        if pre.action == "escalate":
            return StepPrep("escalate", escalate_reason=pre.rule_id, dropped=dropped)
        if pre.action == "drop":
            dropped.append(
                {
                    "plan_id": plan.plan_id,
                    "step_id": step_id,
                    "reason": f"high_risk_without_caution:{pre.term}",
                }
            )
            step_id = _advance_in_plan(plan, step_id)
            continue
        instruction, rewritten, trace = await _rewrite(
            router, source_text, step, state, lane, session_id, budget_ms
        )
        card_id = step_card_id(session_id, plan.plan_id, step_id)
        return StepPrep(
            "ready",
            step={
                "step_id": step.step_id,
                "plan_id": plan.plan_id,
                "plan_version": plan.version,
                "step_no": step_no_of(plan, step_id),
                "title": step.title,
                "instruction": instruction,
                "expected_result": step.expected_result,
                "caution": step.caution,
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
            rewritten=rewritten,
            model_trace=trace,
        )
    return StepPrep("exhausted", dropped=dropped)


def step_no_of(plan: Plan, step_id: str) -> int:
    return next(i for i, s in enumerate(plan.steps, 1) if s.step_id == step_id)


async def _rewrite(
    router: ModelRouter | None,
    source_text: str,
    step: PlanStep,
    state: dict[str, Any],
    lane: str,
    session_id: str,
    budget_ms: int,
) -> tuple[str, bool, dict[str, Any] | None]:
    """guide.step（internal）：改写失败 / 不忠实 / 预算不足 → 原文（03 §1.5 降级）。"""
    if router is None:
        return source_text, False, None
    if budget_ms <= 0:
        log.info("guide.step rewrite skipped: no budget session=%s", session_id)
        return (
            source_text,
            False,
            {"task": "guide.step", "model_used": "skipped", "lane": lane, "attempts": 1},
        )
    strategy = (state.get("emotion") or {}).get("strategy", "normal")
    product = (state.get("product_confirmed") or {}).get("name")
    primary, _fallback = guide_messages(
        source_text=source_text,
        title=step.title,
        product=product,
        strategy=strategy,
        summary={"stage": "guide", "product": product},
    )
    try:
        res = await router.invoke(
            "guide.step",
            primary,
            StepRewrite,
            budget_ms=budget_ms,
            session_id=session_id,
            lane=lane,
        )
    except (ModelInvokeError, CapacityExceeded) as exc:
        log.info("guide.step rewrite unavailable session=%s: %s", session_id, str(exc)[:160])
        return (
            source_text,
            False,
            {"task": "guide.step", "model_used": "skipped", "lane": lane, "attempts": 1},
        )
    cand = " ".join(res.parsed.instruction.split())
    trace = {
        "task": "guide.step",
        "model_used": res.model_used,
        "lane": res.lane,
        "attempts": max(1, sum(1 for a in res.attempts if a.outcome != "skipped")),
    }
    if not rewrite_is_faithful(source_text, cand) or len(cand) > 120:
        log.info(
            "guide.step rewrite rejected session=%s src_verbs=%s out_verbs=%s",
            session_id,
            sorted(action_verbs(source_text)),
            sorted(action_verbs(cand)),
        )
        return source_text, False, trace
    return cand, True, trace
