import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.main import app
from app.sessions.graph import build_graph
from app.sessions.locks import InMemorySessionLock
from app.sessions.manager import RunManager
from app.sessions.store import InMemorySessionStore


@pytest.fixture
def mem_runtime(request, monkeypatch):
    """把应用切到内存存储 + 内存 checkpointer（不跑 lifespan）。"""
    # Domain-flow fixtures prescribe a report intent when no model is configured.
    # New conversation tests exercise the actual degraded interpreter independently.
    if not request.module.__name__.split(".")[-1].startswith("test_conversation_"):
        import app.conversation.interpret as semantic
        original = semantic.interpret_turn
        async def business_interpret(router, state, **kwargs):
            if router is not None or state.get("entry") == "action":
                return await original(router, state, **kwargs)
            from app.rules import get_rules_service
            cp = get_rules_service().check_in(text=state.get("text", ""), session_id=state.get("session_id"))
            intent = "request_human" if any(h.rule_id == "R3" for h in cp.hits) else "report_problem"
            return semantic.TurnInterpretation(primary_intent=intent, device_relation="current"), {"source": "business-flow-fixture"}
        monkeypatch.setattr(semantic, "interpret_turn", business_interpret)
    store = InMemorySessionStore()
    app.state.session_store = store
    app.state.session_graph = build_graph(InMemorySaver())
    app.state.run_manager = RunManager(store, app.state.session_graph)
    app.state.session_lock = InMemorySessionLock()
    yield store
    app.state.session_store = None
    app.state.session_graph = None
    app.state.run_manager = None
    app.state.session_lock = None
