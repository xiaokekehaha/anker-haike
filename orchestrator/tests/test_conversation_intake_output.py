"""Replay the output-cap failure in session 1ad8e1eb148f4e88a3fba20f5c7f6689."""

import pytest
from openai import LengthFinishReasonError
from openai.types.chat import ChatCompletion
from openai.types.completion_usage import CompletionUsage

from app.conversation.interpret import TurnInterpretation
from app.models.config import load_models_config
from app.models.fake import FakeChatModel
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter
from app.models.runtime import set_model_router
from app.settings import REPO_ROOT
from tests import conversation_runtime

conversation = conversation_runtime.conversation
TEXT = "Anker 737 充电宝型号 A1289"


@pytest.mark.parametrize("scenario", ["recorded-cap", "configured-cap", "timed-fallback"])
async def test_product_answer_survives_recorded_output_limit(conversation, monkeypatch, scenario):
    await conversation.send(
        "电池掉电很快",
        {
            "primary_intent": "report_problem",
            "device_relation": "current",
            "facts": [{"value": "电池掉电很快", "quote": "电池掉电很快"}],
        },
    )
    state = await conversation.state()
    issue_id = state["active_issue_id"]
    assert state["clarification"]["reason"] == "product"

    config = load_models_config(REPO_ROOT / "config/models.yaml")
    route = config.route("intake", "domestic")
    if scenario == "recorded-cap":
        route.max_tokens = 512
    primary = config.models[route.chain[0]]
    provider = config.providers[primary.provider]
    env = {provider.api_key_env: "offline-test"}
    backup = config.models[route.chain[1]]
    if scenario == "timed-fallback":
        env[config.providers[backup.provider].api_key_env] = "offline-test"
    registry = ModelRegistry(config, env=env)
    capped_error = LengthFinishReasonError(completion=ChatCompletion(
        id="recorded-length-limit",
        object="chat.completion",
        created=0,
        model=primary.id,
        choices=[],
        usage=CompletionUsage(completion_tokens=512, prompt_tokens=4986, total_tokens=5498),
    ))
    # The trace proves the answer exceeded 512 tokens; its partial body was not saved.
    # Reconstruct a valid answer only for the successful provider branch, without
    # claiming its text or tokenizer matches the original provider completion.
    completed = TurnInterpretation(
        primary_intent="supplement",
        target_issue_id=issue_id,
        device_relation="current",
        device_category="power_bank",
        product_hints=["Anker 737", "A1289"],
    ).model_dump_json()
    calls = []

    def init_fake(model, *, max_tokens, **kwargs):
        assert model in {primary.id, backup.id}
        fails = max_tokens <= 512 or (scenario == "timed-fallback" and model == primary.id)
        fake = FakeChatModel(script=[capped_error if fails else completed])
        calls.append(fake)
        return fake

    monkeypatch.setattr("app.models.registry.init_chat_model", init_fake)
    now = 0.0
    timeouts = []
    router = ModelRouter(registry, clock=lambda: now)
    original_call = router._call

    async def timed_call(runnable, msgs, call_config, timeout_s, method, schema):
        nonlocal now
        timeouts.append(timeout_s)
        elapsed = 5.687 if call_config["metadata"]["alias"] == route.chain[0] else 3.0
        now += min(elapsed, timeout_s)
        if elapsed > timeout_s:
            return "timeout", "TimeoutError: ", None
        return await original_call(runnable, msgs, call_config, timeout_s, method, schema)

    if scenario == "timed-fallback":
        monkeypatch.setattr(router, "_call", timed_call)
    set_model_router(router)
    before = await conversation.snapshot()
    response = await conversation.client.post(
        f"/sessions/{conversation.sid}/messages",
        data={"input_id": "product-answer", "expected_version": before["version"], "text": TEXT},
    )
    conversation.check(response)
    state = await conversation.state()
    snapshot = await conversation.snapshot()
    reply = next(e["text"] for e in reversed(snapshot["timeline"]) if e["kind"] == "assistant_message")
    assert len(calls) == (2 if scenario == "timed-fallback" else 1)
    assert all(len(fake.calls) == 1 for fake in calls)
    assert state["active_issue_id"] == issue_id
    if scenario == "recorded-cap":
        assert state["turn_decision"]["primary_intent"] == "unknown"
        assert state["product_state"] == "unknown"
        assert "暂时无法完成这次理解" in reply
    else:
        assert state["turn_decision"]["primary_intent"] == "supplement", reply
        assert state["product_state"] == "confirmed_sku"
        assert state["product_confirmed"]["sku"] == "ANKER-A1289"
        assert "暂时无法完成这次理解" not in reply
        if scenario == "timed-fallback":
            assert timeouts == pytest.approx([15.0, 15.0 - 5.687])
