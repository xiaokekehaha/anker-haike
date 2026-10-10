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

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.conversation.operation_conditions import answered_history, step_unavailable
from app.models.router import ModelRouter
from app.official.qa_index import ACTION_VERB, MATERIAL
from app.plans.library import PlanLibrary
from app.plans.models import Plan, PlanStep
from app.plans.qa import customer_voice, guide_of
from app.rules.service import RulesService

NS = uuid.UUID("2b0f5a9e-64c2-4c7d-9c0a-7f3d1e6a8b21")
GUIDE_BUDGET_MS = 6000


def step_card_id(session_id: str, plan_id: str, step_id: str) -> str:
    return uuid.uuid5(NS, f"{session_id}|{plan_id}|{step_id}").hex


@dataclass
class StepPrep:
    outcome: str  # ready | exhausted | blocked | explained | source_gap
    step: dict[str, Any] | None = None  # 契约 TroubleshootStep 形状
    card_id: str | None = None
    plan_cursor: dict[str, Any] | None = None
    dropped: list[dict[str, Any]] = field(default_factory=list)
    rewritten: bool = False
    model_trace: dict[str, Any] | None = None
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    # 主引用从哪儿来：qa_exact / kb_qa 表示本轮已有这条 Q&A，none 表示退回本地发布
    anchor: dict[str, Any] | None = None
    explanation: str = ""
    displayed_nodes: list[str] = field(default_factory=list)


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


def _advance_in_plan(plan: Plan, step_id: str, *, option: str | None = None) -> str | None:
    """消费节点后沿已回答分支推进；到 DONE / EXHAUSTED 返回 None。"""
    nxt = plan.next_step_id(step_id, "not_solved", option=option)
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
    answered = {s.get("instruction_src"): s for s in answered_history(state)}
    reported = user_reported_actions(state)
    dropped: list[dict[str, Any]] = []
    context: list[str] = []  # 说明段落不单独出卡，附在下一张卡上（I4：标题 / 结论不是操作，不要求反馈）
    explanation_evidence: dict[str, dict] = {}
    displayed_nodes = list(state.get("displayed_knowledge_nodes") or [])
    while step_id is not None:
        step = plan.step(step_id)
        if step.source_gap:
            source_text = library.evidence_snippet(step.instruction_src)
            _, published, _ = _primary_evidence(step, library, source_text, allowed_evidence)
            explanation_evidence.update(published)
            context.append("The supplied official source refers to further instructions, but does not include them or a link. I can't provide those missing steps from this source.")
            return StepPrep("source_gap", dropped=[*dropped, {
                "plan_id": plan.plan_id, "step_id": step_id, "reason": "source_reference_missing",
            }], explanation="\n\n".join(context), evidence=explanation_evidence, displayed_nodes=displayed_nodes)
        if step.kind == "statement":
            source_text = library.evidence_snippet(step.instruction_src)
            node_key = f"{step.instruction_src}@{library.evidence[step.evidence_key].doc_version}"
            if node_key not in displayed_nodes:
                context.append(customer_voice(source_text))
                displayed_nodes.append(node_key)
                _, published, _ = _primary_evidence(step, library, source_text, allowed_evidence)
                explanation_evidence.update(published)
            dropped.append({"plan_id": plan.plan_id, "step_id": step_id, "reason": "statement_context"})
            step_id = _advance_in_plan(plan, step_id)
            continue
        if step.kind == "handoff":
            # 「请联系客服继续保修流程」不是给用户的操作：计划到此耗尽，交给 decide_next 走质保 / 人工（I4）
            dropped.append({"plan_id": plan.plan_id, "step_id": step_id, "reason": "handoff_step"})
            break
        unavailable = step_unavailable(state, plan.plan_id, step)
        if unavailable == "condition_not_met":
            # 适用条件已被用户原话否定，或兄弟条件成立（fact_check）：这一步不适用，沿计划往后走
            dropped.append({"plan_id": plan.plan_id, "step_id": step_id, "reason": unavailable})
            step_id = _advance_in_plan(plan, step_id)
            continue
        if unavailable:
            return StepPrep("blocked", dropped=[*dropped, {
                "plan_id": plan.plan_id, "step_id": step_id, "reason": unavailable,
            }])
        # 跨计划去重：与已执行步骤 instruction_src 相同 → 跳过（09 §3.4）
        if step.instruction_src in answered:
            dropped.append(
                {"plan_id": plan.plan_id, "step_id": step_id, "reason": "duplicate_instruction_src"}
            )
            step_id = _advance_in_plan(plan, step_id, option=(answered[step.instruction_src].get("answer") or {}).get("option"))
            continue
        source_text = library.evidence_snippet(step.instruction_src)
        # 用户自述已做过的排查（已换滤网、已清洁触点）：同部件同动作的步骤不再让他做一遍（I5：T27 / T36 / T37）
        if step.kind == "action" and (done := matches_reported(source_text, reported)):
            dropped.append({"plan_id": plan.plan_id, "step_id": step_id, "reason": "user_reported", "reported": done})
            step_id = _advance_in_plan(plan, step_id)
            continue
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
                "kind": step.kind,
                "options": list(step.options),
                **({"context": "\n".join(context)} if context else {}),
            },
            card_id=card_id,
            displayed_nodes=displayed_nodes,
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
    only_explanation = all(s.kind == "statement" for s in plan.steps)
    return StepPrep("explained" if only_explanation else "exhausted", dropped=dropped,
                    explanation="\n\n".join(context), evidence=explanation_evidence, displayed_nodes=displayed_nodes)


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


# 未知对象不是通配符；未确认完整覆盖的复合卡保留，由客户反馈后再推进。
PART_WORDS = (
    "filter", "brush", "roller", "side brush", "tank", "contact", "valve", "shield", "mop", "sensor", "base", "dock",
    "station", "bin", "dust box", "lid", "cover", "seal", "ring", "nozzle", "pin", "port", "wheel", "tray", "hose",
    "tube", "bottle", "diaphragm", "pad", "battery", "charger", "cable", "case", "hub", "app", "firmware",
)
ACTION_WORDS = {
    "clean": ("clean", "cleaned", "wipe", "wiped", "rinse", "rinsed", "wash", "washed"),
    "replace": ("replace", "replaced", "change", "changed", "swap", "swapped"),
    "restart": ("restart", "restarted", "reboot", "rebooted", "reset", "power cycle", "powered off"),
    "refill": ("refill", "refilled", "fill", "filled", "top up", "topped up"),
    "reinstall": ("reinstall", "reinstalled", "reseat", "reseated", "reattach", "reattached", "re-install"),
    "update": ("update", "updated", "upgrade", "upgraded"),
}
ACTION_PATTERNS = {name: re.compile(r"\b(?:" + "|".join(re.escape(form) for form in forms) + r")\b", re.IGNORECASE)
                   for name, forms in ACTION_WORDS.items()}
PART_PATTERNS = {part: re.compile(r"\b" + re.escape(part) + r"(?:s|es)?\b", re.IGNORECASE) for part in PART_WORDS}
CONTACT_SYNONYMS = re.compile(r"\belectrical connections?\b", re.IGNORECASE)


def _parts(text: str) -> set[str]:
    normalized = CONTACT_SYNONYMS.sub("contact", text)
    return {part for part, pattern in PART_PATTERNS.items() if pattern.search(normalized)}


def _actions(text: str) -> set[str]:
    return {name for name, pattern in ACTION_PATTERNS.items() if pattern.search(text)}


def user_reported_actions(state: dict[str, Any]) -> list[dict[str, Any]]:
    issue = (state.get("issues") or {}).get(state.get("active_issue_id"), {})
    out = []
    for fact in issue.get("facts", []):
        if (fact.get("status") == "active" and fact.get("kind") == "action_taken"
                and fact.get("polarity", "affirmed") == "affirmed"
                and fact.get("source_kind", "user_report") == "user_report"
                and fact.get("source") in {None, "user_statement", "device_message"}):
            text = " ".join(filter(None, [fact.get("value"), fact.get("subject")]))
            out.append({"value": fact.get("value"), "parts": _parts(text), "actions": _actions(text)})
    return out


def matches_reported(instruction: str, reported: list[dict[str, Any]]) -> str | None:
    """只有明确对象、全部动作被同一用户报告覆盖的卡才能整体跳过；疑问或材料要求不消费。"""
    parts, actions = _parts(instruction), _actions(instruction)
    verbs = [match.group() for match in ACTION_VERB.finditer(instruction)]
    if not parts or not actions or not verbs or "?" in instruction or MATERIAL.search(instruction):
        return None
    # Unknown operations (inspect/remove/ensure…) cannot disappear because a cleaning word also occurs.
    if any(not _actions(verb) for verb in verbs):
        return None
    for item in reported:
        if actions <= item["actions"] and parts <= item["parts"]:
            return item["value"]
    return None


def step_media(plan_id: str, step_id: str) -> list[dict[str, str]]:
    """官方 Q&A 步骤附带的图片 / 视频链接；非 Q&A 计划（测试夹具）为空。"""
    guide = guide_of(plan_id)
    if guide is None:
        return []
    index = int(step_id.removeprefix("s")) - 1 if step_id.startswith("s") and step_id[1:].isdigit() else -1
    if index < 0:
        return []
    media = guide.steps[index].media if guide.kind == "steps" and 0 <= index < len(guide.steps) else guide.media
    return [{"url": m.url, "kind": m.kind} for m in media]


def step_no_of(plan: Plan, step_id: str) -> int:
    return next(i for i, s in enumerate(plan.steps, 1) if s.step_id == step_id)
