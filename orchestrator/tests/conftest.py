import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.main import app
from app.sessions.graph import build_graph
from app.sessions.store import InMemorySessionStore


@pytest.fixture
def mem_runtime():
    """把应用切到内存存储 + 内存 checkpointer（不跑 lifespan）。"""
    store = InMemorySessionStore()
    app.state.session_store = store
    app.state.session_graph = build_graph(InMemorySaver())
    yield store
    app.state.session_store = None
    app.state.session_graph = None
