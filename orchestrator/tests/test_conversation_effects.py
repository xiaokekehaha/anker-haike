from app.conversation import effects
from app.conversation.effects import durable_node, writer


async def say(state):
    writer()({"type": "message", "message_id": state["text"], "delta": state["text"]})
    return {}


async def test_second_visit_of_a_node_in_one_run_keeps_its_effects(monkeypatch):
    # consult → advance_tasks → consult in one run: the second answer must not be taken for a replay.
    monkeypatch.setattr(effects, "get_stream_writer", lambda: (lambda payload: None))
    node = durable_node(say)
    state = {"input_id": "i1", "base_version": 0, "text": "first"}
    first = await node(state)
    second = await node({**state, "text": "second", "pending_effects": first["pending_effects"]})
    assert [e["payload"]["delta"] for e in second["pending_effects"]] == ["first", "second"]


async def test_replaying_a_node_from_its_checkpoint_reuses_effect_ids(monkeypatch):
    monkeypatch.setattr(effects, "get_stream_writer", lambda: (lambda payload: None))
    node = durable_node(say)
    state = {"input_id": "i1", "base_version": 0, "text": "first"}
    first = await node(state)
    replay = await node(state)
    assert [e["effect_id"] for e in replay["pending_effects"]] == [e["effect_id"] for e in first["pending_effects"]]
