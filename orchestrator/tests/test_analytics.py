"""管理员观测台 Phase 1：结果分类、节点轨迹、sink 不阻塞、埋点旁路、迁移覆盖。

口径见 docs/planning/2026-09-13_admin-observability-console/01_design.md §5.3 / §8。
"""

from __future__ import annotations

import asyncio
import importlib.util
import re
from datetime import UTC, datetime, timedelta

import pytest

from app.analytics import derive, hooks
from app.analytics.schema import ROW_TYPES, TABLE_OF, ModelCall, NodeRun
from app.analytics.sink import AnalyticsSink
from app.analytics.store import InMemoryAnalyticsStore, _sql
from app.db import migrations as m
from tests.message_form import message_form

# ---------------------------------------------------------------- 迁移


def _analytics_migration():
    path = m.ORCHESTRATOR_ROOT / "migrations" / "versions" / "0004_analytics.py"
    spec = importlib.util.spec_from_file_location("rev0004", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_creates_every_table_used_by_the_sink():
    rev = _analytics_migration()
    assert rev.down_revision == "0003"
    created = set(re.findall(r"create table if not exists analytics\.(\w+)", "\n".join(rev.STATEMENTS)))
    assert created == set(rev.TABLES) == set(TABLE_OF.values())


def test_generated_sql_matches_dataclass_columns():
    """列顺序即 dataclass 字段顺序；改一边不改另一边会在这里炸。"""
    for kind, row_type in ROW_TYPES.items():
        sql = _sql(kind)
        cols = ", ".join(row_type.columns())
        assert f"analytics.{TABLE_OF[kind]} ({cols})" in sql
        assert sql.count("%s") == len(row_type.columns())


def test_upsert_keeps_created_at_and_updates_the_rest():
    sql = _sql("session_facts")
    assert "on conflict (session_id) do update set" in sql
    assert "created_at = excluded.created_at" not in sql  # 首次写入的创建时间不被覆盖
    assert "outcome = excluded.outcome" in sql


# ---------------------------------------------------------------- 结果分类

RESOLVED = {
    "stage": "done",
    "visible_messages": [{"kind": "closing", "text": "很高兴帮到你"}],
    "_verify": {"outcome": "done", "rule": "solved"},
}
ESCALATED = {
    "stage": "escalate",
    "escalation_summary": {"card_id": "c1", "summary": {}},
    "escalate_reason": "R2",
}


@pytest.mark.parametrize(
    ("values", "done_reason", "pending", "expected"),
    [
        (RESOLVED, "completed", False, ("resolved", "solved")),
        (ESCALATED, "completed", False, ("escalated", "R2")),
        ({"stage": "guide"}, "error", False, ("errored", "node_failed")),
        # 等用户反馈：不是失败，也不是完成
        ({"stage": "guide", "pending_card": {"kind": "step_feedback"}}, "awaiting_input", True,
         ("awaiting_user", "step_feedback")),
        # 澄清：本 run 真的问了问题
        ({"stage": "disambiguate", "run_id": "r1", "clarification": {"reason": "product", "attempts": 1, "asked_run_id": "r1"}},
         "completed", False, ("clarifying", "product")),
        # 升级流程进行中（摘要还没写）：不算已升级
        ({"stage": "escalate", "escalate_reason": "R1"}, "completed", False, ("in_progress", "R1")),
        ({"stage": "guide"}, "cancelled", False, ("in_progress", "cancelled")),
        ({"stage": "intake"}, "completed", False, ("in_progress", None)),
    ],
)
def test_classify(values, done_reason, pending, expected):
    assert derive.classify(
        values, done_reason=done_reason, error_code="node_failed", pending=pending
    ) == expected


def test_server_restart_is_not_a_product_failure():
    """进程重启打断的 run（票 08 reconcile）成败未知，不能算进解决率。"""
    assert derive.classify({"stage": "guide"}, done_reason="error", error_code="server_restarted") == (
        "interrupted",
        "server_restarted",
    )


def test_expired_checkpoint_is_unknown_not_in_progress():
    """会话数据已按 TTL 清理：不知道结局，标 unknown，不混进「仍在进行」。"""
    assert derive.classify({}, done_reason="completed") == ("unknown", "no_checkpoint")


def test_resolved_requires_the_closing_message_not_just_the_stage():
    """stage=done 但没有结束语（例如被取消后停在 done）不算已解决。"""
    assert derive.classify({"stage": "done"}, done_reason="cancelled")[0] != "resolved"


def test_session_facts_pulls_product_steps_and_tokens():
    now = datetime.now(UTC)
    facts = derive.session_facts(
        "s1",
        {
            **RESOLVED,
            "messages": [{"role": "user", "text": "X9 不吸了，电话 13800138000"}],
            "product_confirmed": {"sku": "EUFY-X9-PRO", "category": "robot_vacuum"},
            "product_state": "confirmed_sku",
            "emotion": {"level": "anxious", "strategy": "reassure_first"},
            "steps_executed": [
                {"plan_id": "rv_suction_hair_wrap", "step_id": "s1"},
                {"plan_id": "rv_suction_hair_wrap", "step_id": "s2"},
            ],
            "knowledge_status": "ok",
            "clarification": {"attempts": 2},
        },
        lane="domestic",
        done_reason="completed",
        error_code=None,
        pending=False,
        runs=3,
        created_at=now,
        last_run_at=now,
        model_calls=7,
        tokens_in=900,
        tokens_out=120,
    )
    assert facts.outcome == "resolved"
    assert facts.sku == "EUFY-X9-PRO" and facts.category == "robot_vacuum"
    assert facts.fault_plan_ids == ["rv_suction_hair_wrap"]
    assert facts.steps_executed == 2 and facts.clarifications == 2
    assert facts.emotion_level == "anxious" and facts.runs == 3
    assert (facts.tokens_in, facts.tokens_out, facts.model_calls) == (900, 120, 7)
    assert facts.outcome_at == now  # 终态才有
    # 首问脱敏：手机号不入库
    assert "13800138000" not in (facts.first_question or "")


def test_first_question_can_be_turned_off():
    facts = derive.session_facts(
        "s1", {"messages": [{"role": "user", "text": "hi"}]}, lane=None, done_reason="completed",
        error_code=None, pending=False, runs=1,
        created_at=datetime.now(UTC), last_run_at=datetime.now(UTC), store_text=False,
    )
    assert facts.first_question is None


def test_abandoned_only_for_unfinished_sessions():
    old = datetime.now(UTC) - timedelta(hours=8)
    assert derive.is_abandoned("awaiting_user", old, "guide", after_hours=6)
    assert not derive.is_abandoned("resolved", old, "done", after_hours=6)
    assert not derive.is_abandoned("awaiting_user", datetime.now(UTC), "guide", after_hours=6)


def test_auto_case_candidates_only_flag_for_review():
    assert derive.auto_case_verdict("escalated", "R5") == ("review", ["knowledge_missing"])
    assert derive.auto_case_verdict("escalated", "R2") == ("review", ["wrong_plan"])
    # 用户主动要人工 / 安全升级不是系统失败，不进复盘队列
    assert derive.auto_case_verdict("escalated", "R3") is None
    assert derive.auto_case_verdict("escalated", "R4") is None
    assert derive.auto_case_verdict("resolved", "solved") is None


# ---------------------------------------------------------------- 节点轨迹


def test_node_runs_keep_order_prev_node_and_duration():
    started = 100.0
    wall = datetime.now(UTC)
    rows = derive.node_runs_from_updates(
        "s1",
        "r1",
        [
            ("intake", {"stage": "intake", "product_state": "unknown"}, 100.5),
            ("disambiguate", {"_decision": {"outcome": "continue"}}, 101.0),
            ("retrieve", {"knowledge_status": "ok", "retrieval_rounds": 1}, 102.5),
        ],
        run_started=started,
        started_wall=wall,
    )
    assert [r.node for r in rows] == ["intake", "disambiguate", "retrieve"]
    assert [r.idx for r in rows] == [1, 2, 3]
    assert [r.prev_node for r in rows] == [None, "intake", "disambiguate"]
    assert [r.duration_ms for r in rows] == [500, 500, 1500]
    assert rows[1].summary == {"decision": "continue"}
    assert rows[2].summary == {"knowledge_status": "ok", "retrieval_rounds": 1}


def test_node_summary_keeps_enums_and_drops_free_text():
    summary = derive.node_summary(
        {
            "knowledge_status": "no_match",
            "plan_cursor": {"plan_id": "rv_suction_hair_wrap", "step_no": 2},
            "_verify": {"outcome": "escalate", "rule": "R2"},
            "safety_flags": [{"rule_id": "R4", "term": "冒烟"}],
            "visible_messages": [{"text": "任何自由文本都不该出现"}],
            "text": "用户原话",
            "evidence": {"e1": {"snippet": "手册片段"}},
        }
    )
    assert summary == {
        "knowledge_status": "no_match",
        "plan_id": "rv_suction_hair_wrap",
        "verify": "escalate",
        "rule": "R4",
    }
    assert derive.node_summary({"messages": []}) is None
    assert derive.node_summary("not a dict") is None


# ---------------------------------------------------------------- sink


async def test_sink_batches_and_writes():
    store = InMemoryAnalyticsStore()
    sink = AnalyticsSink(store, flush_ms=10)
    sink.start()
    for i in range(5):
        sink.put("node_run", NodeRun(session_id="s1", run_id="r1", idx=i + 1, node=f"n{i}"))
    await asyncio.wait_for(sink.close(), timeout=3)
    assert [r.node for r in store.of("node_run")] == ["n0", "n1", "n2", "n3", "n4"]
    assert sink.written == 5 and sink.dropped == 0


async def test_sink_drops_instead_of_blocking_when_full():
    """队列满时 put 立即返回并计数——业务线程永远不等写库。"""
    sink = AnalyticsSink(InMemoryAnalyticsStore(), capacity=2)  # 未 start，无人消费
    for i in range(10):
        sink.put("node_run", NodeRun(session_id="s1", run_id="r1", idx=i + 1, node="n"))
    assert sink.queue_depth == 2 and sink.dropped == 8


async def test_sink_survives_store_failures():
    class Broken:
        async def write(self, ops):
            raise RuntimeError("db down")

    sink = AnalyticsSink(Broken(), flush_ms=10)
    sink.start()
    sink.put("node_run", NodeRun(session_id="s1", run_id="r1", idx=1, node="intake"))
    await asyncio.wait_for(sink.close(), timeout=3)
    assert sink.failed == 1 and sink.written == 0  # 只计数，不抛


async def test_in_memory_store_upserts_by_conflict_key():
    store = InMemoryAnalyticsStore()
    await store.write([("node_run", NodeRun(session_id="s1", run_id="r1", idx=1, node="intake"))])
    await store.write([("node_run", NodeRun(session_id="s1", run_id="r1", idx=1, node="reassure"))])
    assert len(store.of("node_run")) == 1 and store.of("node_run")[0].node == "reassure"


# ---------------------------------------------------------------- record() 旁路


@pytest.fixture
def sink(monkeypatch):
    s = AnalyticsSink(InMemoryAnalyticsStore())
    hooks.set_sink(s)
    yield s
    hooks.set_sink(None)


def _drain(sink: AnalyticsSink) -> list:
    out = []
    while sink.queue_depth:
        out.append(sink._queue.get_nowait())
    return out


def test_model_call_becomes_a_fact_row(sink):
    hooks.observe(
        "model_call",
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "task": "intake",
            "session_id": "s1",
            "run_id": "r1",
            "lane": "domestic",
            "stream": False,
            "status": "ok",
            "model_used": "deepseek/deepseek-chat",
            "usage": {"input_tokens": 643, "output_tokens": 45},
            "latency_ms": 1434,
            "attempts": [
                {"alias": "qwen-flash", "outcome": "skipped", "error": "model not configured"},
                {"alias": "deepseek", "outcome": "ok", "error": None},
            ],
        },
    )
    (kind, row), = _drain(sink)
    assert kind == "model_call"
    assert (row.task, row.model_used, row.status) == ("intake", "deepseek/deepseek-chat", "ok")
    assert row.tokens_in == 643 and row.tokens_out == 45 and row.latency_ms == 1434
    # skipped 的候选不算一次尝试，也不算降级
    assert row.attempts == 1 and row.fallback_used is False


def test_fallback_is_counted_when_a_second_vendor_actually_ran(sink):
    hooks.observe(
        "model_call",
        {
            "timestamp": datetime.now(UTC).isoformat(), "task": "reply", "run_id": "r2",
            "status": "ok", "model_used": "zhipu/glm-4",
            "attempts": [
                {"alias": "deepseek", "outcome": "error", "error": "ReadTimeout"},
                {"alias": "zhipu", "outcome": "ok"},
            ],
        },
    )
    (_, row), = _drain(sink)
    assert row.fallback_used is True and row.attempts == 2 and row.error_type == "ReadTimeout"


def test_knowledge_search_becomes_a_retrieval_row(sink):
    hooks.observe(
        "knowledge_search",
        {
            "timestamp": datetime.now(UTC).isoformat(), "session_id": "s1", "run_id": "r1",
            "round": 1, "kb": "kb_manual", "query": "eufy X9 Pro 不吸了",
            "scope": {"product_state": "confirmed_sku", "category": "robot_vacuum", "sku": "EUFY-X9-PRO"},
            "status": "ok", "allowed_count": 2,
            "hit_ids": ["a", "b", "c"], "scores": [0.0164, 0.0161, 0.0158], "latency_ms": 243,
        },
    )
    (kind, row), = _drain(sink)
    assert kind == "retrieval_call"
    assert (row.kb, row.status, row.hits, row.allowed_count) == ("kb_manual", "ok", 3, 2)
    assert row.sku == "EUFY-X9-PRO" and row.top_score == pytest.approx(0.0164)


def test_run_counters_accumulate_then_are_taken_once(sink):
    for _ in range(3):
        hooks.observe(
            "model_call",
            {"timestamp": datetime.now(UTC).isoformat(), "task": "t", "run_id": "r9",
             "status": "ok", "usage": {"input_tokens": 10, "output_tokens": 2}, "attempts": []},
        )
    assert hooks.take_counters("r9") == {"model_calls": 3, "tokens_in": 30, "tokens_out": 6}
    assert hooks.take_counters("r9") == {}  # 取走即清，不泄漏


def test_observe_never_raises_on_malformed_data(sink):
    hooks.observe("model_call", {"attempts": "not a list", "usage": None})
    hooks.observe("knowledge_search", {})
    hooks.observe("unknown_event", {})


def test_observe_is_a_noop_without_a_sink():
    hooks.set_sink(None)
    hooks.observe("model_call", {"task": "t"})  # 不抛


def test_current_node_returns_none_outside_the_graph():
    assert hooks.current_node() is None


def test_model_call_row_column_count_matches_table():
    assert len(ModelCall("t").columns()) == _sql("model_call").count("%s")


# ---------------------------------------------------------------- 端到端（真图 + 内存存储）


@pytest.fixture
async def collecting_sink():
    """把 sink 挂上，run 结束后可直接读回落库的行（异步 fixture：start 需要事件循环）。"""
    store = InMemoryAnalyticsStore()
    s = AnalyticsSink(store, flush_ms=10)
    s.start()
    hooks.set_sink(s)
    yield s, store
    hooks.set_sink(None)


async def test_real_run_produces_node_runs_run_facts_and_session_facts(mem_runtime, collecting_sink):
    """一轮真实 run（内存图 + 假模型）落下完整事实：节点顺序、run 事实、会话事实。"""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    sink, store = collecting_sink
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        resp = await client.post(f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": "机器不亮了"}))
        assert resp.status_code == 200
    await asyncio.wait_for(sink.close(), timeout=5)

    nodes = [r for r in store.of("node_run") if r.session_id == sid]
    assert [r.node for r in nodes] == ["understand", "disambiguate", "clarify", "commit_issue"]
    assert [r.idx for r in nodes] == [1, 2, 3, 4]
    assert [r.prev_node for r in nodes] == [None, "understand", "disambiguate", "clarify"]
    assert all(r.duration_ms is not None and r.duration_ms >= 0 for r in nodes)

    (run,) = [r for r in store.of("run_facts") if r.session_id == sid]
    assert run.entry == "message" and run.seq_no == 1
    assert run.done_reason == "completed" and run.node_count == 4
    assert run.stage_to == "disambiguate" and run.duration_ms >= 0
    assert run.first_visible_ms is not None  # 澄清问句是本 run 的首个可见输出

    (facts,) = [r for r in store.of("session_facts") if r.session_id == sid]
    assert facts.outcome == "clarifying" and facts.runs == 1
    assert facts.user_messages == 1 and facts.first_question == "机器不亮了"
    assert facts.raw_available_until is not None


async def test_second_run_increments_seq_and_upserts_one_session_row(mem_runtime, collecting_sink):
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    sink, store = collecting_sink
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await client.post(f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": "第一句"}))
        await client.post(f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": "第二句"}))
    await asyncio.wait_for(sink.close(), timeout=5)

    runs = sorted([r for r in store.of("run_facts") if r.session_id == sid], key=lambda r: r.seq_no)
    assert [r.seq_no for r in runs] == [1, 2]
    # 会话事实是 upsert：两个 run 后仍只有一行，runs 计数跟上
    session_rows = [r for r in store.of("session_facts") if r.session_id == sid]
    assert len(session_rows) == 1 and session_rows[0].runs == 2


async def test_analytics_failure_does_not_break_the_run(mem_runtime, monkeypatch):
    """sink 抛异常时 run 照常完成——观测永远不阻断业务。"""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    class Exploding:
        def put(self, *a, **k):
            raise RuntimeError("boom")

    hooks.set_sink(Exploding())
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            resp = await client.post(f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": "机器不亮了"}))
        assert resp.status_code == 200
        assert '"reason":"completed"' in resp.text
    finally:
        hooks.set_sink(None)


# ---------------------------------------------------------------- 回填


def _rec(run_id, seq, event, at):
    from datetime import timedelta as _td
    base = datetime(2026, 9, 13, 10, 0, 0, tzinfo=UTC)
    return {"run_id": run_id, "created_at": base + _td(milliseconds=at), "event_json": {**event, "seq": seq}}


def test_runs_from_events_folds_boundaries_and_latencies():
    from app.analytics.backfill import runs_from_events

    runs = runs_from_events([
        _rec("r1", 1, {"type": "run_started", "resumed": False, "deadline_ms": 25000}, 0),
        _rec("r1", 2, {"type": "progress", "stage": "intake"}, 100),
        _rec("r1", 3, {"type": "message", "message_id": "m", "delta": "你好"}, 400),
        _rec("r1", 4, {"type": "progress", "stage": "guide"}, 800),
        _rec("r1", 5, {"type": "step_card", "card_id": "c1", "version": 3, "step": {}}, 900),
        _rec("r1", 6, {"type": "done", "reason": "awaiting_input", "version": 4}, 1000),
        _rec("r2", 7, {"type": "run_started", "resumed": True, "deadline_ms": 25000}, 2000),
        _rec("r2", 8, {"type": "error", "code": "node_failed", "message": "x", "recoverable": True}, 2100),
        _rec("r2", 9, {"type": "done", "reason": "error", "version": 6}, 2200),
    ])
    assert [r.run_id for r in runs] == ["r1", "r2"]
    first, second = runs
    assert first.entry == "message" and first.done_reason == "awaiting_input" and first.version == 4
    assert first.first_visible_ms == 400 and first.card_ready_ms == 900
    assert first.card_kind == "step_card"
    assert (first.stage_from, first.stage_to) == ("intake", "guide")
    assert second.entry == "action:resumed" and second.error_code == "node_failed"
    assert second.done_reason == "error"


def test_assign_nodes_splits_steps_across_runs_by_version():
    """区间取自真实会话 439795d8（A1 产品卡 → 排障 → 解决）的 checkpoint_writes 与 done.version：
    run 结束时 version = 该 run 最后一个节点的 write_step + 1。"""
    from app.analytics.backfill import _Run, assign_nodes

    base = datetime(2026, 9, 13, tzinfo=UTC)
    runs = [_Run("r1", base, version=4), _Run("r2", base, version=9), _Run("r3", base, version=12)]
    assign_nodes(runs, [
        (0, "intake"), (1, "disambiguate"), (2, "prepare_card"), (3, "await_input"),
        (4, "apply_action"), (5, "retrieve"), (6, "reply"), (7, "guide"), (8, "await_input"),
        (9, "apply_action"), (10, "close"),
    ])
    assert runs[0].nodes == ["intake", "disambiguate", "prepare_card", "await_input"]
    assert runs[1].nodes == ["apply_action", "retrieve", "reply", "guide", "await_input"]
    assert runs[2].nodes == ["apply_action", "close"]


def test_assign_nodes_puts_leftovers_on_the_last_run():
    from app.analytics.backfill import _Run, assign_nodes

    base = datetime(2026, 9, 13, tzinfo=UTC)
    runs = [_Run("r1", base, version=2)]
    assign_nodes(runs, [(0, "intake"), (9, "close")])
    assert runs[0].nodes == ["intake", "close"]


def test_backfilled_call_rows_are_insert_only_so_reruns_do_not_duplicate():
    """回填可反复跑：模型 / 检索事实按自然键去重，不是 upsert 覆盖。"""
    from app.analytics.schema import INSERT_ONLY

    assert INSERT_ONLY == {"model_call", "retrieval_call"}
    for kind in INSERT_ONLY:
        assert "do nothing" in _sql(kind)


async def test_in_memory_store_ignores_duplicate_call_rows():
    store = InMemoryAnalyticsStore()
    at = datetime.now(UTC)

    def row(model: str) -> ModelCall:
        return ModelCall(
            task="intake", session_id="s1", run_id="r1", model_used=model, created_at=at
        )

    await store.write([("model_call", row("a"))])
    await store.write([("model_call", row("b"))])
    calls = store.of("model_call")
    assert len(calls) == 1 and calls[0].model_used == "a"  # 先写的保留，不被覆盖
