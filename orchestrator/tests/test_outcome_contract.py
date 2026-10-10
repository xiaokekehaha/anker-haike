"""完成状态一处定义（2026-10-10 第 4 项，K9）：任务办完、案件结案、整个问题结束是三件事。

- T53：换货案件过保 closed_unresolved，维修诉求（report_problem）仍 active → 整体 in_progress(partial_closed)，不是已结束。
- T35：产品咨询 product_question.status=answered、没有案件也没有待办 → consult_answered，不再 in_progress。
checkpoint 派生（classify）、episode 投影、看板 SQL 读同一口径。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.analytics.derive import classify
from app.analytics.l3 import episode
from app.analytics.outcome import derive_outcome
from app.cases.service import CaseService
from app.cases.store import PostgresCaseStore
from tests.test_l3_postgres import l3_pool as l3_pool_fixture

l3_pool = l3_pool_fixture

REPAIR_ACTIVE = {"task_id": "t2", "intent": "report_problem", "status": "active", "quote": "fix it"}
REPLACE_DONE = {"task_id": "t1", "intent": "replacement_request", "status": "done", "quote": "replacement"}


def test_t53_closed_case_with_active_repair_task_is_still_in_progress():
    state = {"session_id": "s", "active_issue_id": "i", "case_status": "closed_unresolved", "stage": "diagnose",
             "task_queue": [REPLACE_DONE, REPAIR_ACTIVE]}
    assert classify(state, done_reason="completed") == ("in_progress", "partial_closed")
    assert episode(state, {"status": "closed_unresolved"})["outcome"] == "in_progress"
    # 分支问句还挂着：等用户
    assert classify({**state, "pending_card": {"kind": "step_feedback"}}, done_reason="completed", pending=True) == ("awaiting_user", "step_feedback")
    # 维修诉求也收口后才是已结束未解决
    settled = {**state, "task_queue": [REPLACE_DONE, {**REPAIR_ACTIVE, "status": "done"}]}
    assert classify(settled, done_reason="completed") == ("closed_unresolved", "case_closed_unresolved")
    waiting = {**state, "task_queue": [REPLACE_DONE, {**REPAIR_ACTIVE, "status": "waiting_human"}]}
    assert classify(waiting, done_reason="completed")[0] == "closed_unresolved"


def test_t35_product_question_answered_is_consult_answered():
    state = {"session_id": "s", "active_issue_id": "i", "stage": "intake", "consult_answered": False,
             "product_question": {"status": "answered", "question": "Low battery, return to recharge"}, "task_queue": []}
    assert classify(state, done_reason="completed") == ("consult_answered", None)
    assert episode(state)["outcome"] == "consult_answered"
    # 流式没完成（answer_unavailable）不算已回答
    assert classify({**state, "product_question": {"status": "answer_unavailable"}}, done_reason="completed")[0] == "in_progress"
    # 回答了咨询，但还有排障诉求排队：整体仍在进行
    assert classify({**state, "task_queue": [{**REPAIR_ACTIVE, "status": "pending"}]}, done_reason="completed")[0] == "in_progress"


@pytest.mark.parametrize("status,expected", [
    ("tracking", "in_progress"), ("proposing", "in_progress"), ("awaiting_approval", "awaiting_human"),
    ("escalated_summary", "escalated"), ("closed", "executed_closed"),
])
def test_case_status_rules_are_shared_by_classify_and_episode(status, expected):
    state = {"session_id": "s", "active_issue_id": "i", "stage": "done", "consult_answered": True,
             "visible_messages": [{"kind": "closing"}], "task_queue": []}
    assert derive_outcome({**state, "case_status": status}, done_reason="completed")[0] == expected
    assert episode(state, {"status": status})["outcome"] == expected


async def test_metric_sql_keeps_partial_closed_unless_case_changed_afterwards(l3_pool):
    """episode 写入时是 in_progress(partial_closed)；案件之后没再变，SQL 不得按案件状态改成 closed_unresolved。"""
    service = CaseService(PostgresCaseStore(l3_pool))
    row = await service.open("partial-session", "issue", {})
    async with l3_pool.connection() as conn:
        await conn.execute("update cases set status='closed_unresolved', updated_at=now() - interval '1 minute' where case_id=%s", (row["case_id"],))
    value = {"session_id": "partial-session", "active_issue_id": "issue", "case_id": row["case_id"],
             "task_queue": [REPLACE_DONE, REPAIR_ACTIVE]}
    fact = episode(value, {**row, "status": "closed_unresolved"})
    assert fact["outcome"] == "in_progress"
    await service.store.record_episode(fact)
    projected = (await service.store.metric_rows(datetime.now(UTC) - timedelta(days=1)))[0]
    assert projected["outcome"] == "in_progress"
    # 人工之后把案件改了（updated_at 晚于 episode）：以案件为准
    async with l3_pool.connection() as conn:
        await conn.execute("update cases set status='closed', updated_at=now() + interval '1 minute' where case_id=%s", (row["case_id"],))
    projected = (await service.store.metric_rows(datetime.now(UTC) - timedelta(days=1)))[0]
    assert projected["outcome"] == "executed_closed"
