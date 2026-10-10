"""会话结果的唯一聚合定义（2026-10-10 第 4 项，K9）。

三种终点是不同的事实：某个诉求办完（task_queue 里的一条 done）、业务案件结案（cases.status）、整个问题结束。
以前 classify / episode / METRIC_ROWS_SQL 各写一套 if 链，案件状态一律覆盖整体问题：
- T53：换货案件过保 closed_unresolved，维修诉求还 active、分支问句还挂着，统计却是「已结束未解决」；
- T35：产品咨询 product_question.status=answered，但只有 l3 的 consult_answered 字段被读，统计成 in_progress。
这里只定义一次；checkpoint 派生、episode 投影、看板 SQL 都读它。规则顺序即口径顺序。
"""

from __future__ import annotations

from typing import Any

CASE_CLOSED = {"closed", "closed_unresolved"}
CASE_WAITING = {"awaiting_approval", "approved", "rejected"}
OPEN_TASK = {"active", "pending"}  # waiting_human 已交人工、done 已办结，都不再是机器人手上的事


def open_tasks(values: dict[str, Any]) -> list[dict[str, Any]]:
    return [t for t in values.get("task_queue") or [] if isinstance(t, dict) and t.get("status") in OPEN_TASK]


def consult_done(values: dict[str, Any]) -> bool:
    """任一答复入口记录的「已回答」：l3 查询的 consult_answered，或产品咨询任务 answered。
    流式输出完成不等于已回答：product_questions 只在 result.completed 时写 answered。"""
    question = values.get("product_question") or {}
    return bool(values.get("consult_answered")) or question.get("status") == "answered"


def derive_outcome(
    values: dict[str, Any],
    *,
    done_reason: str | None,
    error_code: str | None = None,
    pending: bool = False,
    case: dict[str, Any] | None = None,
) -> tuple[str, str | None]:
    """(outcome, outcome_reason)。case 给出时以它的 status 为准（commit_issue 时的实时案件行）。"""
    if not values:
        return "unknown", "no_checkpoint"
    if done_reason == "error":
        if error_code == "server_restarted":
            return "interrupted", error_code
        return "errored", error_code
    case_status = (case or {}).get("status") if case else values.get("case_status")
    human = bool(values.get("human_involved")) or bool(case and case.get("decisions"))
    remaining = open_tasks(values)
    if case_status in CASE_CLOSED and not remaining:
        if case_status == "closed":
            return ("human_executed" if human else "executed_closed"), "case_closed"
        return "closed_unresolved", "case_closed_unresolved"
    if case_status == "escalated_summary":
        return "escalated", values.get("escalate_reason")
    if case_status in CASE_WAITING or values.get("stage") == "awaiting_human":
        return "awaiting_human", case_status
    if case_status and case_status not in CASE_CLOSED:
        # 案件还在办（proposing / executing / tracking / reopened…）：提交过服务单不等于结案
        return "in_progress", case_status
    partial = case_status in CASE_CLOSED and remaining
    if consult_done(values) and not pending and not remaining:
        return "consult_answered", None
    stage = values.get("stage")
    closing = any(isinstance(m, dict) and m.get("kind") == "closing" for m in values.get("visible_messages") or [])
    if stage == "done" and closing and not remaining:
        verify = values.get("_verify") or {}
        return "resolved", verify.get("rule") or "solved"
    issue = (values.get("issues") or {}).get(values.get("active_issue_id"), {})
    summary = issue.get("latest_summary")
    if summary and issue.get("handoff", {}).get("status") == "prepared":
        return "escalated", summary["summary"]["reason"]["rule_id"]
    if not values.get("issues") and values.get("escalation_summary"):
        return "escalated", values.get("escalate_reason")
    if stage == "escalate":
        return "awaiting_user" if pending else "in_progress", values.get("escalate_reason")
    if pending:
        card = values.get("pending_card")
        return "awaiting_user", card.get("kind") if isinstance(card, dict) else None
    if partial:
        # 案件结了，机器人手上还有没办完的诉求（T53：换货过保关闭，维修排障还在）
        return "in_progress", "partial_closed"
    if done_reason == "cancelled":
        return "in_progress", "cancelled"
    clarification = values.get("clarification")
    if isinstance(clarification, dict) and clarification.get("asked_run_id") == values.get("run_id"):
        return "clarifying", clarification.get("reason")
    return "in_progress", None
