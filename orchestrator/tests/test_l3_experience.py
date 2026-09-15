from datetime import UTC, datetime, timedelta

import pytest
from haike_contracts.common import FaultLocalization

from app.analytics.l3 import episode, metrics
from app.cases.service import CaseService
from app.cases.store import CaseConflict
from app.conversation.tasks import enqueue, next_task, ordered_intents
from app.diagnose.localization import normalize, signature_plans
from app.emotion.policy import evaluate_emotion
from app.evaluation.cli import KINDS, run


async def test_case_order_binding_is_immutable_and_survives_execution_attachment():
    cases = CaseService()
    row = await cases.open("s", "issue", {"sku": "sku"})
    row = await cases.bind_order(row["case_id"], "order-a")
    assert await cases.bind_order(row["case_id"], "order-a") == row
    with pytest.raises(CaseConflict, match="其他订单"):
        await cases.bind_order(row["case_id"], "order-b")
    for status in ("proposing", "awaiting_confirmation", "executing"):
        await cases.transition(row["case_id"], status, "test")
    with pytest.raises(CaseConflict, match="不一致"):
        await cases.attach_execution(
            row["case_id"], {"order_no": "order-b", "service_order_no": "srv-b"}
        )
    row = await cases.attach_execution(
        row["case_id"], {"order_no": "order-a", "service_order_no": "srv-a"}
    )
    assert row["external_refs"] == {"order_no": "order-a", "service_order_no": "srv-a"}
    assert (
        await cases.attach_execution(
            row["case_id"], {"order_no": "order-a", "service_order_no": "srv-a"}
        )
        == row
    )


async def test_manual_action_recovery_does_not_repeat_reopen():
    cases = CaseService()
    row = await cases.open("s", "i", {})
    closed = await cases.manual_action(row["case_id"], "close", command_id="close", actor="agent:a", expected_revision=row["revision"])
    args = {"command_id": "reopen", "actor": "agent:a", "expected_revision": closed["revision"]}
    reopened = await cases.manual_action(row["case_id"], "reopen", **args)
    # Retry after the case commit, before the graph checkpoint was committed.
    assert await cases.manual_action(row["case_id"], "reopen", **args) == reopened
    assert reopened["reopened_count"] == 1
    with pytest.raises(CaseConflict):
        await cases.manual_action(row["case_id"], "close", **args)
    closed = await cases.close(row["case_id"], actor="agent:a")
    args = {"input_id": "user-followup", "quote": "仍未解决", "expected_revision": closed["revision"]}
    reopened = await cases.reopen(row["case_id"], **args)
    assert await cases.reopen(row["case_id"], **args) == reopened
    assert reopened["reopened_count"] == 2


@pytest.mark.parametrize("kind", KINDS)
def test_eval_schemas_and_deterministic_regressions(kind):
    result = run(kind)
    assert result["failures"] == []
    assert result["status"] == ("pending_data" if kind == "vision" else "passed")


def test_metric_denominator_ratings_and_exclusion():
    now = datetime.now(UTC)
    rows = [
        {"outcome": o, "rating": score, "source": "live", "updated_at": now}
        for o, score in [
            ("resolved", 5),
            ("executed_closed", 4),
            ("consult_answered", 3),
            ("escalated_human", 1),
            ("human_executed", 2),
            ("awaiting_human", None),
            ("in_progress", None),
        ]
    ]
    rows += [
        {"outcome": "resolved", "source": "smoke", "rating": 5},
        {"outcome": "resolved", "source": "replay", "rating": 5},
    ]
    rows[0]["intent_correct"], rows[1]["intent_correct"] = True, False
    result = metrics(rows, now=now)
    assert result["managed_rate"] == 3 / 5
    assert result["nss"] == 0
    assert result["rating_coverage"] == 5 / 7
    assert result["intent_accuracy"] == 0.5
    assert metrics([])["nss"] is None
    stale = {"outcome": "in_progress", "updated_at": now - timedelta(days=2)}
    assert metrics([stale], now=now)["terminal"] == 1
    assert metrics([stale | {"case_id": "c"}], now=now)["terminal"] == 0


def test_case_submission_never_counts_as_closed():
    state = {
        "session_id": "s",
        "active_issue_id": "i",
        "case_id": "c",
        "stage": "done",
        "consult_answered": True,
    }
    assert episode(state, {"status": "tracking"})["outcome"] == "in_progress"
    assert episode(state, {"status": "closed"})["outcome"] == "executed_closed"
    assert episode(state, {"status": "closed", "decisions": [{}]})["outcome"] == "human_executed"


def test_emotion_negation_recovery_and_window():
    assert evaluate_emotion("calm", "我不会投诉", [], "1")["emotion"]["level"] == "calm"
    assert evaluate_emotion("anxious", "", [], "1")["emotion"]["level"] == "dissatisfied"
    result = evaluate_emotion("calm", "谢谢", [{"input_id": "old", "level": "angry"}], "new")
    assert result["emotion_trend"] == "falling" and result["emotion"]["strategy"] == "normal"
    assert (
        evaluate_emotion("dissatisfied", "", [], "i", unresolved_turns=3)["emotion"]["strategy"]
        == "direct_resolution"
    )
    track = [{"input_id": str(i), "level": "calm"} for i in range(9)]
    assert len(evaluate_emotion("calm", "", track, "10")["emotion_track"]) == 6


def test_tasks_order_dedupe_and_inline_completion():
    from app.conversation.business import BusinessContext
    from app.conversation.tasks import task_business
    order = ordered_intents(
        "logistics_query", ["refund_request", "replacement_request", "report_problem"]
    )
    assert order == ["refund_request", "replacement_request", "report_problem", "logistics_query"]
    queue, notice = enqueue([], "report_problem", ["logistics_query"], "设备不吸，物流到哪了", "i")
    again, _ = enqueue(queue, "report_problem", ["logistics_query"], "同一个问题", "i2")
    assert len(again) == 2 and "设备排障 → 物流查询" in notice
    # An inline read must not finish the active diagnostic task.
    unchanged, task = next_task(queue, "logistics_query")
    assert task is None and unchanged[0]["status"] == "active"
    finished, task = next_task(queue, "report_problem")
    assert finished[0]["status"] == "done" and task["intent"] == "logistics_query"
    a = BusinessContext().accept("DEMO-X10-001", "a")
    b = a.accept("DEMO-CN-003", "b")
    queue, _ = enqueue([], "report_problem", ["logistics_query"], "设备不吸，查物流", "a", business=a)
    queue, _ = enqueue(queue, "order_query", ["logistics_query"], "型号和物流", "b", business=b)
    assert len([t for t in queue if t["intent"] == "logistics_query"]) == 2
    assert len([t for t in queue if t["status"] == "active"]) == 1
    queue, _ = next_task(queue, "logistics_query", business=b)
    assert queue[1]["status"] == "pending"
    checked, _ = next_task(queue, "logistics_query", business=b, task_id=queue[1]["task_id"])
    assert checked[1]["status"] == "pending"
    assert task_business(queue[1], b).bind("warranty.check").params == {"order_no": "DEMO-X10-001"}
    assert task_business({"task_id": "old", "quote": "查物流"}, b).status == "missing"
    assert task_business({"task_id": "old", "quote": "查 DEMO-X10-001 物流"}, b).bind("warranty.check").params == {"order_no": "DEMO-X10-001"}


def test_vision_vocabulary_quality_and_prior():
    result = normalize(
        FaultLocalization(
            findings=[
                {"part": "滚刷", "phenomenon": "缠绕", "severity": "medium", "confidence": 0.9},
                {
                    "part": "未知零件",
                    "phenomenon": "奇怪变化",
                    "severity": "low",
                    "confidence": 0.2,
                },
            ]
        )
    )
    assert signature_plans(result) == ["rv_suction_hair_wrap"]
    assert (
        result["findings"][1]["part"] == "其他"
        and result["findings"][1]["raw"]["part"] == "未知零件"
    )
    result["image_quality"]["usable"] = False
    assert signature_plans(result) == []
    blurry = normalize(FaultLocalization(image_quality={"usable": False, "reasons": ["blurry"]}))
    assert "对焦" in blurry["image_quality"]["guidance"][0]


async def test_manual_close_commitment_and_reopen():
    service = CaseService()
    row = await service.open("s", "i", {})
    cid = row["case_id"]
    with pytest.raises(CaseConflict):
        await service.close(cid, user_confirmed=True, external_status="created")
    for _ in range(2):
        row = await service.record_commitment(cid, "申请换货", "clause")
    assert len([e for e in row["events"] if e["type"] == "commitment"]) == 1
    with pytest.raises(ValueError):
        await service.record_commitment(cid, "赔偿100元", "model")
    row = await service.close(cid, actor="agent:test", expected_revision=row["revision"])
    assert row["status"] == "closed"
    assert (await service.reopen(cid))["status"] == "reopened"


async def test_retake_limit_and_skip_path(monkeypatch):
    from app.sessions import l3

    monkeypatch.setattr(l3, "writer", lambda: lambda e: None)
    state = {
        "input_id": "i",
        "run_id": "r",
        "active_issue_id": "issue",
        "image_quality": {"usable": False, "reasons": ["blurry"], "guidance": ["请对焦"]},
    }
    first = await l3.prepare_retake(state)
    assert first["pending_card"]["kind"] == "upload_retake"
    second = await l3.prepare_retake(state | first)
    third = await l3.prepare_retake(state | second)
    assert third["l3_route"] == "summarize" and third["escalate_reason"] == "R7"
    skipped = await l3.apply_l3_action(state, {"kind": "skip_retake"}, first["pending_card"])
    assert skipped["l3_route"] == "retrieve" and skipped["retake_skipped"]
