import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.main import app
from app.sessions.graph import build_graph
from app.sessions.locks import InMemorySessionLock
from app.sessions.manager import RunManager
from app.sessions.store import InMemorySessionStore


@pytest.fixture
def mem_runtime():
    """把应用切到内存存储 + 内存 checkpointer（不跑 lifespan）。"""
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
