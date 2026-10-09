from datetime import UTC, datetime, timedelta

import pytest
from haike_contracts.common import FaultLocalization

from app.analytics.l3 import episode, metrics
from app.cases.service import CaseService
from app.cases.store import CaseConflict
from app.conversation.reply import OFFER_HUMAN, acknowledge_current_turn, offer_human_after_stream
from app.conversation.tasks import CONSULT_ONLY, enqueue, next_task, ordered_intents, settle
from app.diagnose.localization import (
    normalize,
    part_categories,
    signature_matches,
    signature_plans,
    vocabulary,
)
from app.emotion.policy import complaint_flagged, evaluate_emotion, load_policy
from app.evaluation.cli import KINDS, run
from app.prompts import emotion_layer
from app.sessions.cards import get_catalog
from app.sessions.clarify import differentiated_candidates


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


def test_every_emotion_prompt_comes_from_policy_config():
    strategies = load_policy()["strategies"]
    for name, spec in strategies.items():
        assert emotion_layer(name) == spec["prompt"]
        assert "承诺尽快" not in emotion_layer(name)
    assert emotion_layer("unknown-strategy") == strategies["normal"]["prompt"]


def test_offer_human_action_adds_a_fixed_way_out_on_the_unhappy_turn():
    angry = evaluate_emotion("angry", "", [{"input_id": "old", "level": "calm"}], "now", cues=None)
    assert angry["emotion"]["strategy"] == "de_escalate_and_offer_human"
    state = {"input_id": "now", **angry}
    assert acknowledge_current_turn(state, "我们换一种方式处理。").endswith(OFFER_HUMAN)
    # Already offered in the wording, or no emotion observed this turn: no duplicate sentence.
    assert OFFER_HUMAN not in acknowledge_current_turn(state, "可以为您转人工处理。")
    assert OFFER_HUMAN not in acknowledge_current_turn({**state, "input_id": "later"}, "好的。")


def test_offer_human_follows_a_streamed_reply_as_its_own_message():
    """模型流式回复已经结束，固定出口单独发一条短消息；模型已经提到人工就不补。"""
    angry = evaluate_emotion("angry", "", [{"input_id": "old", "level": "calm"}], "now")
    state = {"input_id": "now", "active_issue_id": "i", **angry}
    sent = []
    offer_human_after_stream(state, "我们先换一种方式处理。", sent.append)
    assert [e["type"] for e in sent] == ["message_start", "message", "message_end"]
    assert sent[1]["delta"] == OFFER_HUMAN
    sent.clear()
    offer_human_after_stream(state, "可以为您转人工处理。", sent.append)
    assert sent == []


def test_complaint_flag_follows_strategy_action_not_only_level():
    rising = evaluate_emotion("angry", "", [{"input_id": "old", "level": "calm"}], "now")
    assert rising["emotion"]["level"] == "angry" and complaint_flagged(rising)
    steady = evaluate_emotion("angry", "", [{"input_id": "old", "level": "angry"}], "now")
    assert steady["emotion"]["strategy"] == "direct_resolution" and not complaint_flagged(steady)
    assert complaint_flagged({"emotion": {"level": "complaint_risk"}})


def test_skip_optional_clarify_skips_the_model_card():
    state = {"text": "扫地机报错了", "category": "robot_vacuum"}
    assert differentiated_candidates(get_catalog(), "robot_vacuum", state)
    skipped = {**state, "emotion_actions": ["skip_optional_clarify", "prefer_proposal_over_more_steps"]}
    assert differentiated_candidates(get_catalog(), "robot_vacuum", skipped) == []


def test_tasks_order_dedupe_and_inline_completion():
    from app.conversation.business import BusinessContext
    from app.conversation.tasks import task_business
    order = ordered_intents(
        "logistics_query", ["refund_request", "replacement_request", "report_problem"]
    )
    assert order == ["refund_request", "replacement_request", "report_problem", "logistics_query"]
    queue, notice = enqueue([], "report_problem", ["logistics_query"], "设备不吸，物流到哪了", "i")
    again, _ = enqueue(queue, "report_problem", ["logistics_query"], "同一个问题", "i2")
    assert len(again) == 2 and "device troubleshooting → delivery status" in notice
    # An inline read must not finish the active diagnostic task.
    unchanged, task = next_task(queue, "logistics_query")
    assert task is None and unchanged[0]["status"] == "active"
    finished, task = next_task(queue, "report_problem")
    assert finished[0]["status"] == "done" and task["intent"] == "logistics_query"
    a = BusinessContext().accept("Anker016", "a")
    b = a.accept("Anker013", "b")
    queue, _ = enqueue([], "report_problem", ["logistics_query"], "设备不吸，查物流", "a", business=a)
    queue, _ = enqueue(queue, "order_query", ["logistics_query"], "型号和物流", "b", business=b)
    assert len([t for t in queue if t["intent"] == "logistics_query"]) == 2
    assert len([t for t in queue if t["status"] == "active"]) == 1
    queue, _ = next_task(queue, "logistics_query", business=b)
    assert queue[1]["status"] == "pending"
    checked, _ = next_task(queue, "logistics_query", business=b, task_id=queue[1]["task_id"])
    assert checked[1]["status"] == "pending"
    assert task_business(queue[1], b).bind("warranty.check").params == {"order_no": "Anker016"}
    assert task_business({"task_id": "old", "quote": "查物流"}, b).status == "missing"
    assert task_business({"task_id": "old", "quote": "查 Anker016 物流"}, b).bind("warranty.check").params == {"order_no": "Anker016"}


def test_vision_vocabulary_quality_and_prior():
    result = normalize(
        FaultLocalization(
            findings=[
                {"part": "滚刷", "phenomenon": "缠绕", "evidence": "刷体缠绕大量毛发", "cell": "中心"},
                {"part": "未知零件", "phenomenon": "奇怪变化", "evidence": "说不上来"},
            ]
        )
    )
    assert signature_plans(result) == ["qa_rv_0272", "qa_rv_0189", "qa_rv_0408"]
    assert (
        result["findings"][1]["part"] == "其他"
        and result["findings"][1]["raw"]["part"] == "未知零件"
    )
    result["image_quality"]["usable"] = False
    assert signature_plans(result) == []
    blurry = normalize(FaultLocalization(image_quality={"usable": False, "reasons": ["blurry"]}))
    assert "focus" in blurry["image_quality"]["guidance"][0]  # 客户可见，英文（D2）


def test_vision_unknown_and_evidence_gate_plan_prior():
    """A2/A3：说不上来的 finding 不驱动 plan；没有 evidence 的 finding 也不驱动 plan。"""
    both_unknown = normalize(
        FaultLocalization(findings=[{"part": "不可辨", "phenomenon": "不可辨"}])
    )
    assert both_unknown["findings"] == []  # 全未知的条目直接丢掉，不进下游
    no_evidence = normalize(
        FaultLocalization(findings=[{"part": "滚刷", "phenomenon": "缠绕"}])
    )
    assert signature_plans(no_evidence) == []
    half_unknown = normalize(
        FaultLocalization(findings=[{"part": "滚刷", "phenomenon": "不可辨", "evidence": "看不清"}])
    )
    assert signature_plans(half_unknown) == []
    bad_cell = normalize(
        FaultLocalization(findings=[{"part": "滚刷", "phenomenon": "缠绕", "evidence": "缠毛发"}])
    )
    assert bad_cell["findings"][0]["cell"] is None


def test_category_parts_are_confirmable_hints_from_known_parts():
    """2026-09-17（9db 重放）：品类特有部件 → 待确认的品类线索；配置引用的部件、品类、plan 都必须真实存在。"""
    from app.sessions.cards import get_catalog, get_plans

    vocab = vocabulary()
    known_parts = set(vocab["parts"]) - {"其他", vocab["unknown"]}
    for category, parts in vocab["category_parts"].items():
        assert category in get_catalog().categories, category
        assert set(parts) <= known_parts, (category, parts)
    assert {s["plan_id"] for s in vocab["signatures"]} <= set(get_plans().plan_ids)

    healthy_brush = normalize(FaultLocalization(findings=[{"part": "滚刷", "phenomenon": "正常"}]))
    assert part_categories(healthy_brush) == ["robot_vacuum"]  # 完好的滚刷同样说明这是扫地机器人
    generic = normalize(
        FaultLocalization(findings=[{"part": "传感器", "phenomenon": "污渍", "evidence": "有灰"}])
    )
    assert part_categories(generic) == []  # 各类设备都有的部件不作线索
    assert part_categories(None) == []

    wrapped = normalize(
        FaultLocalization(
            findings=[
                {"part": "滚刷", "phenomenon": "缠绕", "evidence": "缠满毛发"},
                {"part": "轮组", "phenomenon": "污渍", "evidence": "有灰"},
            ]
        )
    )
    # 按 finding 归因：没命中签名的观察也保留，plan_ids 为空
    assert [(f["part"], ids) for f, ids in signature_matches(wrapped)] == [
        ("滚刷", ["qa_rv_0272", "qa_rv_0189", "qa_rv_0408"]),
        ("轮组", []),
    ]
    assert signature_plans(wrapped) == ["qa_rv_0272", "qa_rv_0189", "qa_rv_0408"]


def test_model_hint_readable_is_derived_not_self_reported():
    """A3：铭牌可读性由字面派生，不接受模型自报。"""
    assert normalize(FaultLocalization(model_hint="X10 Pro"))["model_hint_readable"] == "full"
    assert normalize(FaultLocalization(model_hint="A26?7K8J2"))["model_hint_readable"] == "partial"
    assert normalize(FaultLocalization(model_hint="???"))["model_hint_readable"] == "unreadable"
    assert normalize(FaultLocalization())["model_hint_readable"] == "unreadable"


async def test_manual_close_commitment_and_reopen():
    service = CaseService()
    row = await service.open("s", "i", {})
    cid = row["case_id"]
    with pytest.raises(CaseConflict):
        await service.close(cid, user_confirmed=True, external_status="created")
    for _ in range(2):
        row = await service.record_commitment(cid, "服务单已提交，人工处理中", "receipt")
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
    # 跳过补拍回到消歧：首封带图时读图早于产品确认（T55 实测），直接检索会因无查询中断
    assert skipped["l3_route"] == "disambiguate" and skipped["retake_skipped"]


def test_a_task_waiting_for_a_colleague_releases_the_queue_but_is_not_done():
    """办不了的诉求转人工后：任务记 waiting_human（不是 done），队列继续推进其他任务，重复入队不生效。

    2026-10-09 T9：order_change 一直 active，排在后面的 logistics_query 永远 pending。
    """
    queue, _ = enqueue([], "order_change", ["logistics_query"], "If you have not shipped, don't", "i")
    assert [(t["intent"], t["status"]) for t in queue] == [("order_change", "active"), ("logistics_query", "pending")]
    queue, task = next_task(queue, "order_change", outcome="waiting_human")
    assert task["intent"] == "logistics_query"
    assert [(t["intent"], t["status"]) for t in queue] == [("order_change", "waiting_human"), ("logistics_query", "active")]
    queue, task = next_task(queue, "logistics_query")
    assert task is None and [t["status"] for t in queue] == ["waiting_human", "done"]
    # 客户把同一句话再说一遍：等人工的任务不再当成新任务加入
    again, _ = enqueue(queue, "order_change", ["logistics_query"], "If you have not shipped, don't", "i2")
    assert [t["status"] for t in again if t["intent"] == "order_change"] == ["waiting_human"]


async def test_hand_off_is_deduplicated_by_request_content():
    """交接 = 状态 + 诉求记录 + 摘要一次写入；同一诉求重试不重复，改口记为变更，驳回后可再入队。"""
    cases = CaseService()
    row = await cases.open("s", "i", {"sku": "T2292"})
    summary = {"reason": {"rule_id": "R6", "text": "x"}}
    row = await cases.hand_off(row["case_id"], requested="order_change", quote="hold it", input_id="i1",
                               reason="需人工", summary_of=lambda r: summary)
    assert row["status"] == "awaiting_approval"
    assert [e["type"] for e in row["events"]] == ["status_changed", "review_requested", "handoff_summary"]
    again = await cases.hand_off(row["case_id"], requested="order_change", quote="hold it", input_id="i2",
                                 reason="需人工", summary_of=lambda r: summary)
    assert again["revision"] == row["revision"]
    changed = await cases.hand_off(row["case_id"], requested="order_change", quote="cancel it", input_id="i3",
                                   reason="需人工", summary_of=lambda r: {**summary, "reason": {"rule_id": "R6", "text": "cancel it"}})
    assert [e["type"] for e in changed["events"]][-2:] == ["request_changed", "handoff_summary"]
    assert changed["events"][-2]["payload"]["quote"] == "cancel it"
    await cases.decide(row["case_id"], decision_id="d1", decision="reject", actor="agent:a",
                       expected_revision=changed["revision"], note="no")
    after = await cases.hand_off(row["case_id"], requested="order_change", quote="cancel it again", input_id="i4",
                                 reason="需人工", summary_of=lambda r: summary)
    assert after["status"] == "awaiting_approval"
    assert [e["payload"]["to"] for e in after["events"] if e["type"] == "status_changed"][-3:] == ["rejected", "proposing", "awaiting_approval"]


def test_waiting_for_a_colleague_only_lets_read_only_tasks_continue():
    """等人工时只推进查询类任务：排障、办理要等人工结论；人工决定后 settle 关联任务。"""
    queue, _ = enqueue([], "replacement_request", ["report_problem", "logistics_query"], "换货，顺便排查，物流到哪了", "i")
    queue, task = next_task(queue, "replacement_request", outcome="waiting_human", only=CONSULT_ONLY)
    assert task["intent"] == "logistics_query"
    assert {t["intent"]: t["status"] for t in queue} == {
        "replacement_request": "waiting_human", "report_problem": "pending", "logistics_query": "active"}
    queue, task = next_task(queue, "logistics_query", only=CONSULT_ONLY)
    assert task is None and {t["intent"]: t["status"] for t in queue}["report_problem"] == "pending"
    settled = settle(queue, "replacement_request", "done")
    assert {t["intent"]: t["status"] for t in settled}["replacement_request"] == "done"
    # 等人工的诉求改口：任务原话跟着更新，不另起一个任务
    queue, _ = enqueue([], "order_change", ["logistics_query"], "hold it", "a")
    queue, _ = next_task(queue, "order_change", outcome="waiting_human")
    queue, _ = enqueue(queue, "order_change", [], "cancel it", "b")
    held = [t for t in queue if t["intent"] == "order_change"]
    assert [(t["status"], t["quote"]) for t in held] == [("waiting_human", "cancel it")]


def test_remedy_closed_completes_the_active_task_even_when_it_is_troubleshooting():
    """T29 / T38 复跑：排障走完 → R1 → 过保。队列里只有 report_problem（active）和 order_query（pending），
    过保结论要把当前 active 任务记 done，让 order_query 得以推进，而不是留 active 把会话标 done。"""
    from app.sessions.l3 import remedy_closed

    state = {"requested_remedy": None, "task_queue": [
        {"task_id": "a", "intent": "report_problem", "status": "active"},
        {"task_id": "b", "intent": "order_query", "status": "pending"},
    ]}
    assert remedy_closed(state)["completed_task_intent"] == "report_problem"
    state = {"requested_remedy": "replace", "task_queue": [
        {"task_id": "a", "intent": "replacement_request", "status": "active"},
        {"task_id": "b", "intent": "report_problem", "status": "pending"},
    ]}
    assert remedy_closed(state)["completed_task_intent"] == "replacement_request"
