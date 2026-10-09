"""从 LangGraph checkpoint 状态派生会话事实与结果分类（纯函数，可离线单测）。

口径见 docs/planning/2026-09-13_admin-observability-console/01_design.md §5.3 / §8。
判定只看 checkpoint 权威状态 + 本 run 的 done.reason，不看事件文本。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.analytics.schema import NodeRun, SessionFacts
from app.observability.privacy import sanitize

# 升级原因分类（§8）：系统没解决 vs 用户 / 政策决定，解决率只把前者算作失败
SYSTEM_FAILURE_RULES = {"R1", "R1b", "R1c", "R2", "R5", "R7"}
POLICY_RULES = {"R3", "R4", "R8"}

FIRST_QUESTION_MAX = 200

# 复盘原因标签（01_design.md §9.2）：固定枚举才能统计趋势；新增标签要同步前端文案
REASON_TAGS: tuple[str, ...] = (
    "knowledge_missing",      # 知识缺失
    "retrieval_mismatch",     # 检索错配
    "wrong_plan",             # 计划不对
    "bad_step_wording",       # 步骤话术差
    "model_quality",          # 模型输出差
    "model_fallback",         # 降级导致
    "rule_false_positive",    # 规则误触
    "product_unrecognized",   # 产品未识别
    "emotion_mishandled",     # 情绪处理不当
    "latency",                # 太慢
    "ui_flow",                # 交互问题
    "user_abandoned",         # 用户中途离开
    "intent_correct",
    "intent_wrong",
    "exemplary",              # 值得沉淀
)

# node_runs.summary 的白名单：只留可枚举的判定字段，绝不落自由文本
_SUMMARY_KEYS: dict[str, str] = {
    "product_state": "product_state",
    "category": "category",
    "knowledge_status": "knowledge_status",
    "vision_status": "vision_status",
    "escalate_reason": "escalate_reason",
    "stage": "stage",
    "substage": "substage",
    "out_of_scope": "out_of_scope",
    "rewrite_used": "rewrite_used",
    "retrieval_rounds": "retrieval_rounds",
}


def node_summary(update: Any) -> dict[str, Any] | None:
    """从节点返回的 state 更新里抽白名单字段；没有可记录的返回 None。"""
    if not isinstance(update, dict):
        return None
    out: dict[str, Any] = {}
    for key, name in _SUMMARY_KEYS.items():
        if key in update and isinstance(update[key], (str, bool, int, type(None))):
            out[name] = update[key]
    turn = update.get("turn_decision")
    if isinstance(turn, dict):
        for key in ("primary_intent", "reply_mode", "target_issue_id", "escalation_trigger", "allowed_operations", "human_request_source"):
            if key in turn: out[key] = turn[key]
        out["patch_count"] = len(turn.get("patches", []))
    if "context_revision" in update: out["context_revision"] = update["context_revision"]
    # 嵌套判定：只取枚举值
    decision = update.get("_decision")
    if isinstance(decision, dict) and decision.get("outcome"):
        out["decision"] = decision["outcome"]
    verify = update.get("_verify")
    if isinstance(verify, dict):
        if verify.get("outcome"):
            out["verify"] = verify["outcome"]
        if verify.get("rule"):
            out["rule"] = verify["rule"]
    outcome = update.get("diagnose_outcome")
    if isinstance(outcome, dict) and outcome.get("kind"):
        out["diagnose_outcome"] = outcome["kind"]
    cursor = update.get("plan_cursor")
    if isinstance(cursor, dict) and cursor.get("plan_id"):
        out["plan_id"] = cursor["plan_id"]
    receipt = update.get("receipt")
    if isinstance(receipt, dict) and receipt.get("status"):
        out["receipt_status"] = receipt["status"]
    flags = update.get("safety_flags")
    if isinstance(flags, list) and flags:
        last = flags[-1]
        if isinstance(last, dict) and last.get("rule_id"):
            out["rule"] = last["rule_id"]
    return out or None


def classify(
    values: dict[str, Any],
    *,
    done_reason: str | None,
    error_code: str | None = None,
    pending: bool = False,
) -> tuple[str, str | None]:
    """(outcome, outcome_reason)。判定顺序即 01_design.md §5.3 的表格顺序。"""
    if not values:
        # checkpoint 已按 TTL 清理：不知道这会话是怎么收尾的，不要算进任何率
        return "unknown", "no_checkpoint"
    if done_reason == "error":
        # 进程重启打断的 run 不是产品失败（票 08 reconcile 写的 server_restarted）：
        # 用户可能重发后继续，成败未知，不进解决率的分子与分母
        if error_code == "server_restarted":
            return "interrupted", error_code
        return "errored", error_code
    case_status = values.get("case_status")
    if case_status == "closed":
        return ("human_executed" if values.get("human_involved") else "executed_closed"), "case_closed"
    if case_status in {"awaiting_approval", "approved", "rejected"} or values.get("stage") == "awaiting_human":
        return "awaiting_human", case_status
    if values.get("consult_answered"):
        return "consult_answered", None
    stage = values.get("stage")
    closing = any(
        isinstance(m, dict) and m.get("kind") == "closing"
        for m in (values.get("visible_messages") or [])
    )
    if stage == "done" and closing:
        verify = values.get("_verify") or {}
        return "resolved", verify.get("rule") or "solved"
    issue = (values.get("issues") or {}).get(values.get("active_issue_id"), {})
    summary = issue.get("latest_summary")
    if summary and issue.get("handoff", {}).get("status") == "prepared":
        return "escalated", summary["summary"]["reason"]["rule_id"]
    if not values.get("issues") and values.get("escalation_summary"):
        return "escalated", values.get("escalate_reason")
    if stage == "escalate":
        # 摘要还没写完（等凭证 / 等确认）：仍在升级流程里，不算已升级
        return "awaiting_user" if pending else "in_progress", values.get("escalate_reason")
    if pending:
        return "awaiting_user", _pending_kind(values)
    if done_reason == "cancelled":
        return "in_progress", "cancelled"
    clarification = values.get("clarification")
    if isinstance(clarification, dict) and clarification.get("asked_run_id") == values.get(
        "run_id"
    ):
        return "clarifying", clarification.get("reason")
    return "in_progress", None


def _pending_kind(values: dict[str, Any]) -> str | None:
    card = values.get("pending_card")
    return card.get("kind") if isinstance(card, dict) else None


def is_abandoned(outcome: str, last_run_at: datetime, stage: str | None, *, after_hours: float) -> bool:
    """未终结且久无新 run → 放弃。由查询层现算（黑客松范围不跑后台改判任务）。"""
    if outcome not in ("awaiting_user", "clarifying", "in_progress"):
        return False
    return datetime.now(UTC) - last_run_at > timedelta(hours=after_hours)


def first_question(values: dict[str, Any]) -> str | None:
    """首条用户消息，脱敏并截断；用于会话列表的「他问了什么」。"""
    for m in values.get("history") or values.get("messages") or []:
        if isinstance(m, dict) and m.get("role") == "user" and (m.get("text") or "").strip():
            return str(sanitize(m["text"]))[:FIRST_QUESTION_MAX]
    return None


def session_facts(
    session_id: str,
    values: dict[str, Any],
    *,
    lane: str | None,
    done_reason: str | None,
    error_code: str | None,
    pending: bool,
    runs: int,
    created_at: datetime,
    last_run_at: datetime,
    model_calls: int = 0,
    tokens_in: int = 0,
    tokens_out: int = 0,
    total_latency_ms: int = 0,
    raw_ttl_hours: float = 24.0,
    store_text: bool = True,
) -> SessionFacts:
    outcome, reason = classify(
        values, done_reason=done_reason, error_code=error_code, pending=pending
    )
    product = values.get("product_confirmed") or {}
    steps = values.get("steps_executed") or []
    clarification = values.get("clarification") or {}
    receipt = values.get("receipt") or {}
    plan_ids = sorted(
        {
            str(s.get("plan_id"))
            for s in steps
            if isinstance(s, dict) and s.get("plan_id")
        }
        | {
            str(p.get("plan_id"))
            for p in (values.get("plans_ranked") or [])
            if isinstance(p, dict) and p.get("plan_id")
        }
    )
    terminal = outcome in ("resolved", "escalated", "errored")
    return SessionFacts(
        session_id=session_id,
        lane=lane,
        created_at=created_at,
        last_run_at=last_run_at,
        runs=runs,
        user_messages=sum(
            1 for m in (values.get("history") or values.get("messages") or []) if isinstance(m, dict) and m.get("role") == "user" and m.get("kind", "message") == "message"
        ),
        first_question=first_question(values) if store_text else None,
        product_state=values.get("product_state"),
        sku=product.get("sku"),
        category=values.get("category") or product.get("category"),
        emotion_level=(values.get("emotion") or {}).get("level"),
        fault_plan_ids=plan_ids,
        steps_executed=len(steps),
        clarifications=int(clarification.get("attempts") or 0),
        knowledge_status=values.get("knowledge_status"),
        receipt_status=receipt.get("status"),
        outcome=outcome,
        outcome_reason=reason,
        outcome_at=last_run_at if terminal else None,
        total_latency_ms=total_latency_ms,
        model_calls=model_calls,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        raw_available_until=last_run_at + timedelta(hours=raw_ttl_hours),
    )


def auto_case_verdict(outcome: str, reason: str | None) -> tuple[str, list[str]] | None:
    """自动候选（只进 review 队列，不自动定性）：值得人看一眼的会话及其初步原因标签。"""
    if outcome == "errored":
        return "review", ["latency" if reason == "deadline_exceeded" else "model_quality"]
    if outcome == "escalated" and reason in SYSTEM_FAILURE_RULES:
        tags = {
            "R1": ["wrong_plan"],
            "R1b": ["wrong_plan"],
            "R1c": ["wrong_plan"],
            "R2": ["wrong_plan"],
            "R5": ["knowledge_missing"],
            "R7": ["product_unrecognized"],
        }[reason]
        return "review", tags
    if outcome == "abandoned":
        return "review", ["user_abandoned"]
    return None


def node_runs_from_updates(
    session_id: str,
    run_id: str,
    updates: list[tuple[str, Any, float]],
    *,
    run_started: float,
    started_wall: datetime,
) -> list[NodeRun]:
    """updates 流（节点名, 状态更新, 到达时刻 monotonic）→ node_runs 行。

    duration_ms 取「上一个节点产出到本节点产出」的间隔：图内节点串行执行，该间隔即本节点耗时
    （含框架调度开销），第一个节点从 run 开始计。
    """
    rows: list[NodeRun] = []
    prev_node: str | None = None
    prev_at = run_started
    for idx, (node, update, at) in enumerate(updates, start=1):
        rows.append(
            NodeRun(
                session_id=session_id,
                run_id=run_id,
                idx=idx,
                node=node,
                prev_node=prev_node,
                started_at=started_wall + timedelta(seconds=prev_at - run_started),
                duration_ms=max(0, int((at - prev_at) * 1000)),
                status="ok",
                summary=node_summary(update),
            )
        )
        prev_node, prev_at = node, at
    return rows
