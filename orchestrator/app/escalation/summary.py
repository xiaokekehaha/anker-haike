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
    Feedback,
    HandoffBusiness,
    ModelTraceItem,
    PendingRequest,
    ReceiptOutcome,
)

from app.conversation.business import BusinessContext
from app.conversation.operation_conditions import conditions_for, feedback_history
from app.conversation.tasks import NOT_EXECUTABLE
from app.diagnose.query import category_label
from app.official.message import parse_message
from app.sessions.receipt import receipt_outcome
from app.warranty.service import decide_by_dealer, today

REASON_TEXT = {
    "R1": "排障步骤已达上限（executed ≥ 4）",
    "R1b": "用户连续无法操作（skipped ≥ 3）",
    "R1c": "排障步数达到硬上限",
    "R2": "官方 Q&A 的排查步骤已用尽",
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


# design §3.5：R2 只是兼容映射，真实结束原因来自 next_action.reason
NEXT_ACTION_TEXT = {
    "no_supported_followup": "{steps}，现有资料没有进一步可执行的排查操作",
    "knowledge_coverage_missing": "当前资料没有适用于该现象的排查路径",
    "user_requested_human": "用户明确要求人工服务",
    "safety_risk": "存在待核实的安全风险，已停止相关操作",
    "burden_prefer_proposal": "用户不愿继续逐步排查，转为服务方案",
}


FEEDBACK_LABELS: dict[Feedback, str] = {
    "solved": "已解决",
    "not_solved": "已操作，仍有问题",
    "cannot_do": "无法操作",
}


def _executed_steps_text(executed: list[tuple[str, Feedback]]) -> str:
    """结束原因区分实际操作与无法操作，不能把缺少反馈当作已尝试。"""
    prefixes: dict[Feedback, str] = {
        "solved": "已操作并解决",
        "not_solved": "已操作但未解决",
        "cannot_do": "无法操作",
    }
    parts = []
    for feedback, prefix in prefixes.items():
        titles = dict.fromkeys(title for title, result in executed if result == feedback)
        if titles:
            parts.append(prefix + "、".join(f"「{title}」" for title in titles))
    return "，".join(parts) or "尚无已执行的排查记录"


def next_action_text(state: dict[str, Any], next_action: dict[str, Any] | None) -> str | None:
    if not next_action or next_action.get("issue_id") not in {None, state.get("active_issue_id")}:
        return None
    template = NEXT_ACTION_TEXT.get(next_action.get("reason") or "")
    if not template:
        return None
    steps = _executed_steps_text([
        (step.get("title") or step["step_id"], step["feedback"])
        for step in feedback_history(state)
        if step.get("feedback") in FEEDBACK_LABELS
    ])
    return template.format(steps=steps)


def _diagnostic_observations(state) -> list[str]:
    decision = state.get("diagnostic_decision") or {}
    if decision.get("issue_id", state.get("active_issue_id")) != state.get("active_issue_id"):
        decision = {}
    observations = [f"待确认：{item}" for item in decision.get("missing_information", [])]
    ranked = state.get("plans_ranked") or []
    assessed = [entry for entry in ranked if "supported_symptoms" in entry]
    if assessed or (state.get("escalate_reason") == "R5" and state.get("knowledge_status") == "ok"):
        supported = {symptom for entry in assessed for symptom in entry["supported_symptoms"]}
        issue = (state.get("issues") or {}).get(state.get("active_issue_id"), {})
        observations.extend(
            f"尚无适用步骤，待人工核实：{fact['value']}"
            for fact in issue.get("facts", [])
            if fact.get("status") == "active" and fact.get("kind") == "symptom" and fact["value"] not in supported
        )
    pending = state.get("pending_card") or {}
    if pending.get("kind") == "step_feedback":
        step = (pending.get("payload") or {}).get("step") or {}
        observations.append(f"已提供但未反馈：{step.get('title', step.get('step_id', '排查步骤'))}")
    return observations


def build_summary(
    state: dict[str, Any],
    *,
    reason: str,
    lane: str,
    polish_model_used: str | None = None,
) -> EscalationSummary:
    issue = (state.get("issues") or {}).get(state.get("active_issue_id"), {})
    diagnostic_observations = _diagnostic_observations(state)
    facts = [f for f in issue.get("facts", []) if f.get("status") == "active"]
    product = state.get("product_confirmed") or {}
    # 品类中文名只有一个真源（products.yaml categories[].name）：category_only 时按目录渲染，
    # 不写死品类（2026-09-17 会话 c9e11 移动电源被写成扫地机器人）
    category = state.get("category") or (product.get("category") if isinstance(product, dict) else None)
    product_text = (
        product.get("name") or product.get("sku") if isinstance(product, dict) else str(product)
    ) or (
        f"{category_label(category)}（型号未确认）"
        if state.get("product_state") == "category_only" and category
        else "未确认"
    )
    hints = state.get("product_hints") or []
    if product_text == "未确认" and hints:
        product_text = f"未确认（线索：{'、'.join(map(str, hints))}）"
    flags = state.get("safety_flags") or []
    reason_terms = sorted(
        {f["term"] for f in flags if f.get("rule_id") == reason and f.get("term")}
    )
    reason_text = REASON_TEXT.get(reason, reason)
    if reason == "R7":
        reason_text = {"product": "设备品类仍待确认", "symptom": "仍缺少选择适用步骤所需的故障现象", "conflict": "设备信息存在待确认的冲突"}.get((state.get("clarification") or {}).get("reason"), reason_text)
    next_action = state.get("next_action") or {}
    if next_action.get("compat_rule", reason) == reason and next_action_text(state, next_action):
        reason_text = next_action_text(state, next_action)
    if reason_terms:
        reason_text += f"；命中词：{'、'.join(reason_terms)}"
    emotion = state.get("emotion") or {}
    steps = [
        ExecutedStep(step_id=s["step_id"], title=s.get("title", s["step_id"]), feedback=s["feedback"])
        for s in feedback_history(state)
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
        warranty=state.get("warranty"),
        recommended_options=(state.get("proposal") or {}).get("options", []),
        gate_result=state.get("gate_result"),
        task_queue=state.get("task_queue") or [],
        emotion_track=state.get("emotion_track") or [],
        draft_reply="已整理订单、质保判断与证据，请核实后继续处理。" if state.get("case_id") else None,
        product=product_text,
        problem=problem_text(state, facts),
        business=handoff_business(state, facts, product_text),
        observations=list(dict.fromkeys([
            *list(state.get("observations") or []), *diagnostic_observations, *first_message_facts(state),
            *(f"操作限制：{b.quote or '该步骤暂时无法执行，原因未确认'}" for b in conditions_for(state).blockers if not b.cleared),
        ])),
        hypotheses=list(dict.fromkeys(
            h.get("fault") or h.get("plan_id")
            for h in state.get("plans_ranked") or []
            if isinstance(h, dict) and (h.get("fault") or h.get("plan_id"))
        )),
        steps=steps,
        reason=EscalationReason(
            rule_id=reason,
            text=reason_text,
            cause=next_action.get("reason") if next_action.get("compat_rule", reason) == reason else None,
        ),
        emotion=Emotion(
            level=emotion.get("level"), strategy=emotion.get("strategy", "normal")
        ),
        # 票 39：凭证子流程结果从 state.receipt 派生；未进入 / 未收集时为 not_collected
        receipt=ReceiptOutcome(**receipt_outcome(state, reason)),
        model_trace=trace,
    )


def first_message_facts(state: dict[str, Any]) -> list[str]:
    """首封表单里可核对的事实（PN、SN、订单号、购买商家与国家）原样带给人工；
    商家与国家齐全时附经销商名录判定（T45：安全转人工，人工仍需要知道是不是授权经销商）。"""
    parsed = parse_message(state.get("text") or "")
    out = []
    if parsed.product_name or parsed.pn:
        out.append("客户填写的产品：" + " / ".join(filter(None, [parsed.product_name, parsed.pn])))
    if parsed.sn:
        out.append(f"客户填写的 SN：{parsed.sn}")
    if parsed.order_no:
        out.append(f"客户填写的订单号：{parsed.order_no}")
    if parsed.seller or parsed.country:
        out.append("客户自述购买渠道：" + " / ".join(filter(None, [parsed.seller, parsed.country])))
    if parsed.login_country:
        out.append(f"客户登录 / 注册国家：{parsed.login_country}")
    if parsed.seller and parsed.country and not state.get("warranty"):
        decision = decide_by_dealer(parsed.seller, parsed.country, None, today(state.get("at")))
        out.append(f"经销商名录：{decision.reason}")
    return out


def problem_text(state: dict[str, Any], facts: list[dict[str, Any]]) -> str:
    """问题字段：肯定极性的症状事实 → 表单推送 / 描述原文 → issue 标题；都没有才写占位。

    T22 / T34 首测：模型没抽出事实，摘要就写「尚未记录具体故障现象」，而表单里明明写着「Wiel raakt de grond niet」。"""
    symptoms = [f["value"] for f in facts if f["kind"] == "symptom" and f.get("polarity", "affirmed") != "negated"]
    if symptoms:
        return "；".join(symptoms)
    parsed = parse_message(state.get("text") or "")
    if parsed.problem_text:
        return parsed.problem_text
    issue = (state.get("issues") or {}).get(state.get("active_issue_id"), {})
    title = (issue.get("title") or "").strip()
    if title and title != "待描述的问题":
        return title
    return "（尚未记录具体故障现象）"


# 每种业务交接至少要给人工的字段；缺哪项就写进 missing，让接手的人一眼看到还要问什么
REQUIRED_BY_KIND = {
    "device_fault": ("product", "symptoms"),
    "order_change": ("order_no", "condition"),
    "parts_purchase": ("product", "part"),
    "warranty_review": ("product", "order_no", "symptoms"),
    "safety": ("product", "symptoms"),
    "unknown": ("product", "symptoms"),
}


def handoff_business(state: dict[str, Any], facts: list[dict[str, Any]], product_text: str) -> HandoffBusiness:
    """按业务类型组织交接内容：已知 / 缺失 / 待办分别标明，摘要不再从最后一句答复反推（I7 / I8）。"""
    remedy = state.get("requested_remedy")
    symptoms = [f for f in facts if f["kind"] == "symptom" and f.get("polarity", "affirmed") != "negated"]
    if state.get("escalate_reason") == "R4":
        kind = "safety"
    elif remedy == "parts_purchase":
        kind = "parts_purchase"
    elif remedy in NOT_EXECUTABLE:
        kind = "order_change"
    elif state.get("warranty"):
        kind = "warranty_review"
    elif symptoms or parse_message(state.get("text") or "").problem_text:
        kind = "device_fault"
    else:
        kind = "unknown"
    known: dict[str, str] = {}
    if product_text and not product_text.startswith("未确认"):
        known["product"] = product_text
    problem = problem_text(state, facts)
    if problem != "（尚未记录具体故障现象）":
        known["symptoms"] = "；".join(
            f"{f['value']}" + (f"（{f['subject']}）" if f.get("subject") else "") + (f"，{f['timing']}" if f.get("timing") else "")
            for f in symptoms
        ) or problem
    actions = [f["value"] for f in facts if f["kind"] == "action_taken"]
    if actions:
        known["actions_taken"] = "；".join(actions)
    tasks = state.get("task_queue") or []
    order_no = state.get("case_order_no")
    business = BusinessContext.restore(state) if state.get("business_context") else None
    subject = business.subjects.get(business.active_subject_id) if business else None
    if subject is not None:
        order_no = order_no or (subject.identifiers.get("order_no").value if subject.identifiers.get("order_no") else None)
        status = subject.facts.get("logistics_status")
        if status:
            known["package_status"] = status.value
    if order_no:
        known["order_no"] = order_no
    condition = next((t["quote"] for t in tasks if t.get("intent") in {"order_change", "address_update"} and t.get("quote")), None)
    if condition:
        known["condition"] = condition
    if kind == "parts_purchase":
        part = next((f.get("subject") or f["value"] for f in facts if f["kind"] == "symptom" and f.get("subject")), None) \
            or next((t["quote"] for t in tasks if t.get("intent") == "parts_purchase" and t.get("quote")), None)
        if part:
            known["part"] = part
    parsed = parse_message(state.get("text") or "")
    if parsed.login_country:
        known["login_country"] = parsed.login_country
    missing = [field for field in REQUIRED_BY_KIND[kind] if field not in known]
    pending = [PendingRequest(intent=t["intent"], quote=t.get("quote") or "", status=t["status"])
               for t in tasks if t.get("status") in {"pending", "active", "waiting_human"}]
    return HandoffBusiness(kind=kind, known=known, missing=missing, pending_requests=pending)


def _receipt_facts_text(facts: dict[str, str]) -> str:
    labels = {
        "order_no": "订单号",
        "purchase_date": "购买日期",
        "address": "收货地址",
        "dealer": "授权经销商",
        "country": "购买国家",
    }
    return (
        "；".join(
            f"{labels.get(k, k)}："
            + v
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
        "【排查记录】"
        + (
            "；".join(
                f"{x.title}（{FEEDBACK_LABELS[x.feedback]}）"
                for x in s.steps
            )
            or "无"
        ),
        f"【升级原因】{s.reason.rule_id}：{s.reason.text}",
        *([
            f"【业务】{s.business.kind}；已知：" + ("；".join(f"{k}={v}" for k, v in s.business.known.items()) or "无")
            + "；缺失：" + ("、".join(s.business.missing) or "无")
            + "；待办：" + ("；".join(f"{r.intent}({r.status})" for r in s.business.pending_requests) or "无")
        ] if s.business else []),
        f"【情绪】{s.emotion.level or '未判断'} / {s.emotion.strategy}",
        f"【凭证】{s.receipt.status}"
        + (f"，下一步：{s.receipt.next_step}" if s.receipt.next_step else ""),
        "【凭证核实事实】" + _receipt_facts_text(s.receipt.verified_facts),
        "【凭证待核实差异】" + ("；".join(s.receipt.conflicts) or "无"),
    ]
    return "\n".join(lines)


# 给客户看的结束说明（英文，D2 2026-10-08）；转人工摘要本身仍是中文，给客服看。
REASSURANCE = {
    "R5": (
        "I couldn't confirm official troubleshooting guidance for the symptoms you reported. "
        "I've put together a record of this issue so a support colleague can continue from here."
    ),
    "R4": (
        "For your safety, please stop using the device and do not charge it. "
        "I've put together a record of this issue so a support colleague can look into it."
    ),
    "R3": "I've prepared a summary of your issue for our support team. Live hand-over to an agent isn't connected yet.",
}
DEFAULT_REASSURANCE = "I've put together a record of this issue so a support colleague can continue from here."
CUSTOMER_BOUNDARY = {
    "no_supported_followup": "The official troubleshooting steps for this issue have all been tried",
    "knowledge_coverage_missing": "I couldn't find official guidance that covers this issue",
}


def reassurance_text(reason: str, state: dict[str, Any] | None = None) -> str:
    """结束时对用户的说明：有真实原因时如实说明覆盖边界（design §4），并保持「已整理 / 未接入」的区分。"""
    next_action = (state or {}).get("next_action") or {}
    if state is not None and next_action.get("kind") == "handoff_offer" and next_action.get("compat_rule") == reason:
        detail = next_action_text(state, next_action)
        boundary = CUSTOMER_BOUNDARY.get(next_action.get("reason") or "")
        if detail and boundary:
            return (
                f"{boundary}. I've put together the issue and the steps you tried so a support colleague can continue; "
                "live hand-over isn't connected yet. If anything changes, tell me and we'll continue from the record."
            )
    return REASSURANCE.get(reason, DEFAULT_REASSURANCE)
