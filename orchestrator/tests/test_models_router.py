"""票 10：三种结构化策略、统一校验、带错误重试、tag / metadata。"""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.models.config import load_models_config
from app.models.fake import FakeChatModel
from app.models.registry import ModelRegistry
from app.models.router import ModelInvokeError, ModelRouter

CONFIG = """
version: t
default_lane: domestic
providers:
  p_native: {sdk: openai, api_key_env: K_NATIVE}
  p_json:   {sdk: openai, api_key_env: K_JSON}
  p_tools:  {sdk: openai, api_key_env: K_TOOLS}
  p_over:   {sdk: anthropic, api_key_env: K_OVER, lane: overseas}
models:
  m_native: {provider: p_native, id: n1, structured: native, vision: true}
  m_json:   {provider: p_json,   id: j1, structured: json_object, vision: true}
  m_tools:  {provider: p_tools,  id: t1, structured: none, vision: true}
  m_over:   {provider: p_over,   id: o1, structured: native, vision: true}
  emb: {provider: p_json, id: e, kind: embedding}
  rr:  {provider: p_json, id: r, kind: rerank}
lanes:
  domestic:
    intake:               {chain: [m_json, m_tools, m_over], effort: low, max_tokens: 64}
    disambiguate.clarify: {chain: [m_native]}
    diagnose.vision:      {chain: [m_json], needs_vision: true}
    diagnose.synthesize:  {chain: [m_tools]}
    guide.step:           {chain: [m_json]}
    reply.stream:         {chain: [m_json], stream: true}
    escalate.summary:     {chain: [m_json]}
    warranty.receipt_ocr: {chain: [m_json], needs_vision: true}
"""
ALL_KEYS = {"K_NATIVE": "x", "K_JSON": "x", "K_TOOLS": "x", "K_OVER": "x"}


class Emotion(BaseModel):
    level: str = Field(pattern="^(calm|anxious|angry)$")
    score: float = Field(ge=0, le=1)


GOOD = {"level": "anxious", "score": 0.7}
MSGS = [("system", "你是客服"), ("human", "充不进电，急死了")]


@pytest.fixture
def cfg(tmp_path):
    p = tmp_path / "models.yaml"
    p.write_text(CONFIG, encoding="utf-8")
    return load_models_config(p)


def make_router(cfg, scripts: dict[str, list], env=None):
    fakes = {
        alias: FakeChatModel(script=list(s), name_for_trace=alias) for alias, s in scripts.items()
    }
    reg = ModelRegistry(cfg, env=env if env is not None else ALL_KEYS)
    router = ModelRouter(reg, model_factory=lambda r, route: fakes[r.alias])
    return router, fakes


async def test_json_object_strategy(cfg):
    router, fakes = make_router(cfg, {"m_json": [json.dumps(GOOD)]})
    res = await router.invoke("intake", MSGS, Emotion, budget_ms=5000, session_id="s1")
    assert res.parsed == Emotion(**GOOD)
    assert res.method == "json_object" and res.alias == "m_json" and res.model_used == "p_json/j1"
    assert [a.outcome for a in res.attempts] == ["ok"]
    assert res.usage["total_tokens"] == 15
    call = fakes["m_json"].calls[0]
    assert call["kwargs"]["response_format"] == {"type": "json_object"}
    first = call["messages"][0]
    assert (
        isinstance(first, SystemMessage)
        and "JSON Schema" in first.content
        and "level" in first.content
    )
    assert "internal" in call["tags"]
    assert call["metadata"]["task"] == "intake"
    assert call["metadata"]["session_id"] == "s1"
    assert call["metadata"]["lane"] == "domestic"


async def test_native_strategy(cfg):
    router, fakes = make_router(cfg, {"m_native": [json.dumps(GOOD)]})
    res = await router.invoke("disambiguate.clarify", MSGS, Emotion, budget_ms=5000)
    assert res.method == "json_schema" and res.parsed.level == "anxious"
    assert fakes["m_native"].calls[0]["kwargs"]["structured_method"] == "json_schema"


async def test_tools_strategy(cfg):
    router, fakes = make_router(cfg, {"m_tools": [GOOD]})
    res = await router.invoke("diagnose.synthesize", MSGS, Emotion, budget_ms=5000)
    assert res.method == "tools" and res.parsed == Emotion(**GOOD)
    kw = fakes["m_tools"].calls[0]["kwargs"]
    assert kw["tool_choice"] == "Emotion" and len(kw["tools"]) == 1


async def test_same_schema_across_all_strategies(cfg):
    for task, alias, item in (
        ("guide.step", "m_json", '```json\n{"level":"calm","score":0.1}\n```'),
        ("disambiguate.clarify", "m_native", {"level": "calm", "score": 0.1}),
        ("diagnose.synthesize", "m_tools", {"level": "calm", "score": 0.1}),
    ):
        router, _ = make_router(cfg, {alias: [item]})
        res = await router.invoke(task, MSGS, Emotion, budget_ms=5000)
        assert res.parsed == Emotion(level="calm", score=0.1), task


async def test_schema_failure_retries_once_with_error_hint(cfg):
    bad = json.dumps({"level": "furious", "score": 2})
    router, fakes = make_router(cfg, {"m_json": [bad, json.dumps(GOOD)]})
    res = await router.invoke("intake", MSGS, Emotion, budget_ms=5000)
    assert [a.outcome for a in res.attempts] == ["schema_error", "ok"]
    assert "score" in res.attempts[0].error and "level" in res.attempts[0].error
    second = fakes["m_json"].calls[1]["messages"]
    assert len(second) == len(fakes["m_json"].calls[0]["messages"]) + 1
    assert isinstance(second[-1], HumanMessage) and "未通过校验" in second[-1].content
    assert "score" in second[-1].content


async def test_two_failures_move_to_next_model_then_raise(cfg):
    router, fakes = make_router(
        cfg,
        {
            "m_json": ["not json", "still not"],
            "m_tools": [{"level": "nope"}, {"level": "nope"}],
            "m_over": [],
        },
        env={"K_JSON": "x", "K_TOOLS": "x"},  # m_over 无 key → skipped
    )
    with pytest.raises(ModelInvokeError) as ei:
        await router.invoke("intake", MSGS, Emotion, budget_ms=5000)
    outcomes = [(a.alias, a.outcome) for a in ei.value.attempts]
    assert outcomes == [
        ("m_json", "schema_error"),
        ("m_json", "schema_error"),
        ("m_tools", "schema_error"),
        ("m_tools", "schema_error"),
        ("m_over", "skipped"),
    ]
    assert "missing env K_OVER" in ei.value.attempts[-1].error
    assert len(fakes["m_json"].calls) == 2 and len(fakes["m_tools"].calls) == 2


async def test_fallback_to_next_model_succeeds_with_lane_annotation(cfg):
    router, _ = make_router(
        cfg, {"m_json": ["x", "y"], "m_tools": [RuntimeError("boom")], "m_over": [GOOD]}
    )
    res = await router.invoke("intake", MSGS, Emotion, budget_ms=5000)
    assert res.alias == "m_over" and res.lane == "overseas"
    assert [a.outcome for a in res.attempts] == ["schema_error", "schema_error", "error", "ok"]
    assert res.attempts[2].error.startswith("RuntimeError: boom")
    assert [a.lane for a in res.attempts] == ["domestic", "domestic", "domestic", "overseas"]


async def test_method_override_forces_strategy(cfg):
    router, fakes = make_router(cfg, {"m_json": [GOOD]})
    res = await router.invoke("intake", MSGS, Emotion, budget_ms=5000, method="tools")
    assert res.method == "tools" and fakes["m_json"].calls[0]["kwargs"]["tool_choice"] == "Emotion"


async def test_budget_exhausted_stops_before_calling(cfg):
    router, fakes = make_router(cfg, {"m_json": [json.dumps(GOOD)]})
    with pytest.raises(ModelInvokeError):
        await router.invoke("intake", MSGS, Emotion, budget_ms=0)
    assert fakes["m_json"].calls == []
