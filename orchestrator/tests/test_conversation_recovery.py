from langgraph.checkpoint.memory import InMemorySaver

from app.sessions.graph import build_graph
from app.sessions.manager import RunManager
from app.sessions.store import InMemorySessionStore


async def test_recovery_delivers_committed_effect_without_reinterpreting(monkeypatch):
    store = InMemorySessionStore()
    sid = (await store.create_session()).session_id
    receipt, _ = await store.reserve_input(
        sid, "i1", {"kind": "message", "text": "回顾"}, expected_version=0
    )
    graph = build_graph(InMemorySaver())
    effect = {
        "effect_id": "stable-effect",
        "input_id": "i1",
        "payload": {
            "type": "issue_changed",
            "active_issue_id": "issue",
            "issues": [],
            "input_id": "i1",
            "resolved_issue_id": "issue",
            "version": 1,
        },
    }
    await graph.aupdate_state(
        {"configurable": {"thread_id": sid}},
        {
            "session_id": sid,
            "input_id": "i1",
            "committed_input_id": "i1",
            "committed_version": 1,
            "base_version": 0,
            "applied_input_ids": ["i1"],
            "stage": "intake",
            "pending_effects": [effect],
        },
        as_node="commit_issue",
    )

    async def fail(*args, **kwargs):
        raise AssertionError("committed input must not call interpreter")

    monkeypatch.setattr("app.conversation.interpret.interpret_turn", fail)
    # The display effect landed immediately before the crash, but its delivered flag did not.
    await store.append_event(
        sid,
        receipt["run_id"],
        {
            **effect["payload"],
            "event_id": "stable-effect",
            "recorded_at": receipt["received_at"],
            "seq": 3,
            "run_id": receipt["run_id"],
        },
    )
    manager = RunManager(store, graph)
    assert await manager.reconcile_orphans() == [(sid, receipt["run_id"])]
    events = await store.list_events(sid)
    assert sum(e.get("event_id") == "stable-effect" for e in events) == 1
    assert events[-1]["type"] == "done" and events[-1]["reason"] == "completed"
    assert (await store.get_input(sid, "i1"))["status"] == "completed"
    assert (await store.get_session(sid)).version == 1


async def test_accepted_input_without_checkpoint_fails_without_model_replay(monkeypatch):
    store = InMemorySessionStore()
    sid = (await store.create_session()).session_id
    receipt, _ = await store.reserve_input(
        sid, "i1", {"kind": "message", "text": "你好"}, expected_version=0
    )
    graph = build_graph(InMemorySaver())

    async def interpret(*args, **kwargs):
        raise AssertionError("uncommitted input must not auto-run model on restart")

    monkeypatch.setattr("app.conversation.interpret.interpret_turn", interpret)
    manager = RunManager(store, graph)
    await manager.reconcile_orphans()
    events = await store.list_events(sid)
    assert sum(e["type"] == "input_received" for e in events) == 1
    assert sum(e["type"] == "run_started" for e in events) == 1
    assert events[-1]["reason"] == "error" and events[-1]["version"] == 0
    assert events[-1]["run_id"] == receipt["run_id"]


async def test_cancel_before_publish_does_not_publish_candidate_facts_but_retains_risk(
    mem_runtime, monkeypatch
):
    import asyncio

    from app.conversation.history import fold_history
    from app.conversation.interpret import TurnInterpretation
    from app.conversation.policy import pending_risk_sources
    from app.main import app
    from app.rules import get_rules_service
    from app.sessions.snapshot import build_snapshot

    async def interpret(*args, **kwargs):
        return TurnInterpretation(
            primary_intent="report_problem",
            device_relation="other",
            product_hints=["机器人"],
            facts=[{"value": "冒烟", "quote": "冒烟"}],
            device_safety_assertion="reported",
            device_safety_quote="冒烟",
        ), {"source": "test"}

    monkeypatch.setattr("app.conversation.interpret.interpret_turn", interpret)
    import app.sessions.graph as graph_module

    waiting = asyncio.Event()

    async def paused_summary(state):
        waiting.set()
        await asyncio.Future()

    monkeypatch.setattr(graph_module, "summarize", paused_summary)
    app.state.session_graph = graph_module.build_graph(InMemorySaver())
    app.state.run_manager = RunManager(mem_runtime, app.state.session_graph)
    sid = (await mem_runtime.create_session()).session_id
    manager, graph = app.state.run_manager, app.state.session_graph
    handle = await manager.start(sid, "机器人冒烟了")
    await asyncio.wait_for(waiting.wait(), timeout=3)
    await manager.cancel(sid, handle.run_id)
    snapshot = await build_snapshot(mem_runtime, graph, sid)
    assert snapshot.version == 0 and snapshot.active_issue_id is None
    history = [e.as_dict() for e in fold_history(sid, await mem_runtime.list_event_records(sid))]
    risks = pending_risk_sources({"session_id": sid, "history": history}, get_rules_service())
    assert len(risks) == 1 and risks[0]["issue_id"] is None
    assert risks[0]["restriction"] == "no_operations"
