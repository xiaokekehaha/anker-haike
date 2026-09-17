"""Context diagnostics survive the analytics path without storing prompt contents."""

import json
from types import SimpleNamespace

from httpx import ASGITransport, AsyncClient

from app.analytics import hooks
from app.analytics.context import take_context_events
from app.analytics.sink import AnalyticsSink
from app.analytics.store import InMemoryAnalyticsStore
from app.analytics.trace import RunTrace
from app.conversation.interpret import interpret_turn
from app.main import app
from app.models.config import load_models_config
from app.models.fake import FakeChatModel
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter
from app.models.runtime import set_model_router
from app.observability.runtime import record, run_id_context
from app.settings import CONFIG_DIR
from tests.message_form import message_form
from tests.test_context_capacity import incident_state


async def test_metrics_follow_each_node_execution_and_keep_usage_separate(monkeypatch):
    store = InMemoryAnalyticsStore()
    sink = AnalyticsSink(store)
    sink.start()
    hooks.set_sink(sink)
    monkeypatch.setattr(hooks, "current_node", lambda: "understand")
    token = run_id_context.set("metrics-run")
    trace = RunTrace("metrics-session", "metrics-run", entry="message", seq_no=1)
    try:
        fake = FakeChatModel(script=['{"primary_intent":"order_query"}'])
        router = ModelRouter(
            ModelRegistry(load_models_config(CONFIG_DIR / "models.yaml"), env={"DASHSCOPE_API_KEY": "test"}),
            model_factory=lambda resolved, route: fake,
        )
        _, context = await interpret_turn(router, incident_state(), lane="domestic")
        trace.on_updates({"understand": {}})
        record("context_budget", task="intake", required_tokens=18000, max_tokens=16000,
               token_breakdown={"authority": 18000})
        trace.on_updates({"understand": {}})
        trace.finish(SimpleNamespace(values={}), done_reason="completed", error_code=None,
                     stage_from=None, stage_to=None, first_visible_ms=None, card_ready_ms=None, card_kind=None)
    finally:
        run_id_context.reset(token)
        hooks.set_sink(None)
        await sink.close()
    first, second = store.of("node_run")
    built, called = first.summary["context_metrics"]
    assert built["tokens"] == context["tokens"]
    assert built["token_breakdown"] == context["token_breakdown"]
    assert called["actual_input_tokens"] == 10
    assert called["attempts"][0]["estimated_input_tokens"] > built["tokens"]
    assert called["attempts"][0]["input_budget"] == 16000
    assert [e["event"] for e in second.summary["context_metrics"]] == ["context_budget"]
    assert take_context_events("metrics-run", "understand") == []
    assert "我的产品" not in json.dumps(first.summary, ensure_ascii=False)


def test_unknown_provider_usage_is_not_recorded_as_zero(monkeypatch):
    sink = AnalyticsSink(InMemoryAnalyticsStore())
    hooks.set_sink(sink)
    monkeypatch.setattr(hooks, "current_node", lambda: "reply")
    try:
        hooks.observe("model_call", {"task": "reply.stream", "run_id": "missing-usage", "usage": {}})
        (event,) = take_context_events("missing-usage", "reply")
        assert "actual_input_tokens" not in event
    finally:
        hooks.set_sink(None)


async def test_real_graph_attaches_context_metrics_to_understand_node(mem_runtime):
    store = InMemoryAnalyticsStore()
    sink = AnalyticsSink(store)
    sink.start()
    hooks.set_sink(sink)
    fake = FakeChatModel(script=['{"primary_intent":"unknown","clarification":"请说明本轮需要查询的信息。"}'])
    set_model_router(ModelRouter(
        ModelRegistry(load_models_config(CONFIG_DIR / "models.yaml"), env={"DASHSCOPE_API_KEY": "test"}),
        model_factory=lambda resolved, route: fake,
    ))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            url = f"/sessions/{sid}/messages"
            response = await client.post(url, data=await message_form(client, url, {"text": "机器不亮了"}))
            assert response.status_code == 200
    finally:
        await app.state.run_manager.shutdown()
        set_model_router(None)
        hooks.set_sink(None)
        await sink.close()
    assert len(fake.calls) == 1
    nodes = [n for n in store.of("node_run") if n.session_id == sid]
    understand = next(n for n in nodes if n.node == "understand")
    metric, usage = understand.summary["context_metrics"]
    assert metric["task"] == "intake" and metric["event"] == "context_built"
    assert metric["tokens"] < metric["max_tokens"]
    assert usage["event"] == "model_call" and usage["actual_input_tokens"] == 10
