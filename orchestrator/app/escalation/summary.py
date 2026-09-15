"""escalate.summarize：从图状态直接渲染 EscalationSummary（08 §5、09 §4、03 §1.7）。

- 不调模型即可生成；图节点可选调用 polish_summary（escalate.summary）整理问题字段；默认 model_trace 标 summary_polish=skipped。
- receipt 默认 not_collected（安全升级 / request_human 路径先摘要、凭证可选补充，09 §5.1）。
- card_id 稳定：uuid5(session_id, "escalation_summary", reason)，重跑得到同一卡片。
"""

from __future__ import annotations

import uuid
from typing import Any

from haike_contracts.common import (
    Emotion,
    EscalationReason,
    EscalationSummary,
    ExecutedStep,
    ModelTraceItem,
    ReceiptOutcome,
)

from app.sessions.receipt import receipt_outcome

REASON_TEXT = {
    "R1": "排障步骤已达上限（executed ≥ 4）",
    "R1b": "用户连续无法操作（skipped ≥ 3）",
    "R1c": "排障步数达到硬上限",
    "R2": "预写排障计划已耗尽",
    "R3": "用户明确要求人工服务",
    "R4": "检测到安全风险信号（冒烟 / 烧焦 / 电池鼓包等），立即升级",
    "R5": "当前产品的这一问题没有可用的排障计划",
    "R6": "用户提出退换 / 保修诉求",
    "R7": "缺少继续处理所需的信息",
    "R8": "产品不在本期支持范围内",
}
NS = uuid.UUID("7c4d0a7e-9d0e-4c4f-9a53-16a5d0d5f9e1")


def summary_card_id(session_id: str, reason: str) -> str:
    return uuid.uuid5(NS, f"{session_id}:escalation_summary:{reason}").hex


def _user_texts(state: dict[str, Any]) -> list[str]:
    return [
        m.get("text", "")
        for m in state.get("messages", [])
        if m.get("role") == "user" and m.get("text")
    ]


def build_summary(
    state: dict[str, Any],
    *,
    reason: str,
    lane: str,
    polish_model_used: str | None = None,
) -> EscalationSummary:
    issue = (state.get("issues") or {}).get(state.get("active_issue_id"), {})
    facts = [f for f in issue.get("facts", []) if f.get("status") == "active"]
    product = state.get("product_confirmed") or {}
    product_text = (
        product.get("name") or product.get("sku") if isinstance(product, dict) else str(product)
    ) or ("扫地机器人（型号未确认）" if state.get("product_state") == "category_only" else "未确认")
    hints = state.get("product_hints") or []
    if product_text == "未确认" and hints:
        product_text = f"未确认（线索：{'、'.join(map(str, hints))}）"
    flags = state.get("safety_flags") or []
    reason_terms = sorted(
        {f["term"] for f in flags if f.get("rule_id") == reason and f.get("term")}
    )
    reason_text = REASON_TEXT.get(reason, reason)
    if reason == "R5" and (state.get("diagnostic_decision") or {}).get("reason") == "question_coverage_missing":
        reason_text = "系统缺少适用的澄清问题，无法继续选择排查方案"
    if reason == "R7":
        reason_text = {"product": "设备品类仍待确认", "symptom": "仍缺少选择适用步骤所需的故障现象", "conflict": "设备信息存在待确认的冲突"}.get((state.get("clarification") or {}).get("reason"), reason_text)
        reason_text = {"answers_unavailable": "用户暂时无法确认所询问的故障现象",
                       "question_coverage_missing": "系统缺少适用的澄清问题",
                       "no_discriminating_question": "系统缺少适用的澄清问题"}.get((state.get("diagnostic_decision") or {}).get("reason"), reason_text)
    if reason_terms:
        reason_text += f"；命中词：{'、'.join(reason_terms)}"
    emotion = state.get("emotion") or {}
    steps = [
        ExecutedStep(
            step_id=s["step_id"], title=s.get("title", s["step_id"]), feedback=s["feedback"]
        )
        for s in state.get("steps_executed") or []
        if s.get("feedback")
    ]
    trace = [
        ModelTraceItem(
            task=t["task"],
            model_used=t["model_used"],
            lane=t.get("lane", lane),
            attempts=max(1, int(t.get("attempts", 1))),
        )
        for t in state.get("model_trace") or []
    ]
    trace.append(
        ModelTraceItem(
            task="escalate.summary_polish",
            model_used=polish_model_used or "skipped",
            lane=lane,
            attempts=1,  # 契约要求 ≥ 1；skipped 表示未发起调用
        )
    )
    return EscalationSummary(
        case_id=state.get("case_id"),
        policy_decision_brief={k: (state.get("policy_decision") or {}).get(k) for k in ("policy_id", "policy_version", "within_warranty", "needs_human_reasons")} if state.get("policy_decision") else None,
        recommended_options=(state.get("proposal") or {}).get("options", []),
        gate_result=state.get("gate_result"),
        task_queue=state.get("task_queue") or [],
        emotion_track=state.get("emotion_track") or [],
        draft_reply="已整理订单与政策依据，请核实后继续处理。" if state.get("case_id") else None,
        product=product_text,
        problem="；".join(f["value"] for f in facts if f["kind"] == "symptom") or "；".join(
            f"问：{a['question']}；用户回答：{a['quote']}" for a in (state.get("symptom_interview") or {}).get("answers", [])
        ) or "（尚未记录具体故障现象）",
        observations=[*list(state.get("observations") or []), *[
            f"问：{a['question']}；用户回答：{a['quote']}"
            for a in (state.get("symptom_interview") or {}).get("answers", [])
        ]],
        hypotheses=[
            h.get("fault") or h.get("plan_id")
            for h in state.get("plans_ranked") or []
            if isinstance(h, dict)
        ],
        steps=steps,
        reason=EscalationReason(rule_id=reason, text=reason_text),
        emotion=Emotion(
            level=emotion.get("level", "calm"), strategy=emotion.get("strategy", "normal")
        ),
        # 票 39：凭证子流程结果从 state.receipt 派生；未进入 / 未收集时为 not_collected
        receipt=ReceiptOutcome(**receipt_outcome(state, reason)),
        model_trace=trace,
    )


def _receipt_facts_text(facts: dict[str, str]) -> str:
    labels = {
        "channel": "订单渠道",
        "purchase_date": "购买日期",
        "dealer.name": "经销商",
        "authorized": "名录授权状态",
    }
    return (
        "；".join(
            f"{labels.get(k, k)}："
            + ({"true": "已授权", "false": "未授权"}.get(v, v) if k == "authorized" else v)
            for k, v in facts.items()
        )
        or "无"
    )


def summary_to_text(s: EscalationSummary) -> str:
    """可读文本（前端 SummaryCard 一键复制同款格式；五要素：产品、问题、观察 / 假设、步骤、原因）。"""
    lines = [
        f"【产品】{s.product}",
        f"【问题】{s.problem}",
        f"【观察】{'；'.join(s.observations) or '无'}",
        f"【假设】{'；'.join(s.hypotheses) or '无'}",
        "【已执行步骤】" + ("；".join(f"{x.title}（{x.feedback}）" for x in s.steps) or "无"),
        f"【升级原因】{s.reason.rule_id}：{s.reason.text}",
        f"【情绪】{s.emotion.level} / {s.emotion.strategy}",
        f"【凭证】{s.receipt.status}"
        + (f"，下一步：{s.receipt.next_step}" if s.receipt.next_step else ""),
        "【凭证核实事实】" + _receipt_facts_text(s.receipt.verified_facts),
        "【凭证待核实差异】" + ("；".join(s.receipt.conflicts) or "无"),
    ]
    return "\n".join(lines)


REASSURANCE = {
    "R4": "您提到了设备安全风险，请停止使用，不要继续充电。我已整理这台设备的问题记录，您可以交给人工客服进一步核实。",
    "R3": "已为您整理当前问题摘要，您可以复制给人工客服。目前尚未接入真实转接服务。",
}


def reassurance_text(reason: str) -> str:
    return REASSURANCE.get(reason, "我已整理当前问题记录，您可以复制给人工客服继续处理。")
