"""票 13 / 14：ModelRouter.stream 事件序列、中断切换（aborted → start(replaces) → fallback tier）、简化 Prompt 变体、user_visible 标签。"""

from __future__ import annotations

import re

import pytest

from app.models.config import load_models_config
from app.models.fake import FakeChatModel
from app.models.registry import ModelRegistry
from app.models.router import ModelInvokeError, ModelRouter, StreamEvent
from tests.test_models_fallback import CONFIG, KEYS, rate_limited


@pytest.fixture
def cfg(tmp_path):
    p = tmp_path / "models.yaml"
    p.write_text(
        re.sub(
            r"reply\.stream:\s+\{chain: \[a\], stream: true\}",
            "reply.stream: {chain: [a, b], stream: true}",
            CONFIG,
        ),
        encoding="utf-8",
    )
    return load_models_config(p)


def build(cfg, scripts, sleeps=None):
    fakes = {k: FakeChatModel(script=list(v), name_for_trace=k) for k, v in scripts.items()}

    async def sleep(s):
        (sleeps if sleeps is not None else []).append(s)

    router = ModelRouter(
        ModelRegistry(cfg, env=KEYS),
        model_factory=lambda r, _: fakes[r.alias],
        sleep=sleep,
        rng=lambda: 0.0,
    )
    return router, fakes


async def collect(router, **kw) -> list[StreamEvent]:
    return [
        e
        async for e in router.stream(
            "reply.stream", [("human", "hi")], budget_ms=10_000, message_id="m1", **kw
        )
    ]


async def test_normal_stream_sequence(cfg):
    router, fakes = build(cfg, {"a": [["你好", "，", "我在"]]})
    evs = await collect(router, session_id="s1")
    assert [e.kind for e in evs] == ["start", "delta", "delta", "delta", "end"]
    assert all(e.message_id == "m1" and e.model_tier == "primary" for e in evs)
    assert "".join(e.text for e in evs if e.kind == "delta") == "你好，我在"
    call = fakes["a"].calls[0]
    assert (
        call["stream"] is True
        and "user_visible" in call["tags"]
        and call["metadata"]["tier"] == "primary"
    )


async def test_mid_stream_failure_aborts_and_fallback_replaces(cfg):
    router, fakes = build(
        cfg,
        {"a": [["为了您", RuntimeError("upstream closed")]], "b": [["为了您的安全", "，请关机"]]},
    )
    evs = await collect(router, fallback_messages=[("system", "简化模式"), ("human", "hi")])
    kinds = [e.kind for e in evs]
    assert kinds == ["start", "delta", "aborted", "switched", "start", "delta", "delta", "end"]
    aborted = evs[2]
    assert aborted.message_id == "m1" and "upstream closed" in aborted.reason
    new_start = evs[4]
    assert (
        new_start.replaces == "m1"
        and new_start.message_id != "m1"
        and new_start.model_tier == "fallback"
    )
    assert evs[-1].model_tier == "fallback" and evs[-1].message_id == new_start.message_id
    # 备用模型用了简化模式变体
    assert fakes["b"].calls[0]["messages"][0].content == "简化模式"
    assert fakes["a"].calls[0]["messages"][0].content == "hi"


async def test_failure_before_any_delta_retries_same_model_silently(cfg):
    sleeps: list[float] = []
    router, fakes = build(cfg, {"a": [rate_limited(), ["ok"]]}, sleeps)
    evs = await collect(router)
    assert [e.kind for e in evs] == ["start", "delta", "end"] and evs[0].model_tier == "primary"
    assert sleeps == [1.0] and len(fakes["a"].calls) == 2


async def test_chain_exhausted_after_partial_raises(cfg):
    router, _ = build(cfg, {"a": [["半句", TimeoutError()]], "b": [["又半句", TimeoutError()]]})
    evs = []
    with pytest.raises(ModelInvokeError):
        async for e in router.stream(
            "reply.stream", [("human", "hi")], budget_ms=10_000, message_id="m1"
        ):
            evs.append(e)
    kinds = [e.kind for e in evs]
    assert kinds == ["start", "delta", "aborted", "switched", "start", "delta", "aborted"]
    assert evs[-1].model_tier == "fallback"


async def test_empty_stream_counts_as_error(cfg):
    router, _ = build(cfg, {"a": [[]], "b": [["有内容"]]})
    evs = await collect(router)
    assert [e.kind for e in evs] == ["start", "delta", "end"] and evs[0].model_tier == "fallback"
    assert evs[0].replaces is None  # 主模型没吐字，无需替换


async def test_budget_exhausted_raises(cfg):
    router, _ = build(cfg, {"a": [["x"]]})
    with pytest.raises(ModelInvokeError, match="budget exhausted"):
        async for _ in router.stream(
            "reply.stream", [("human", "hi")], budget_ms=0, message_id="m1"
        ):
            pass


async def test_skipped_models_do_not_make_first_attempt_fallback(cfg):
    """链首未配置（无 key）被跳过时，第一家真正调用的模型仍是 primary（07 §6：fallback 只指故障切换）。"""
    fakes = {"b": FakeChatModel(script=[["ok"]])}
    router = ModelRouter(
        ModelRegistry(cfg, env={"K2": "x", "K3": "x"}), model_factory=lambda r, _: fakes[r.alias]
    )
    evs = [
        e
        async for e in router.stream(
            "reply.stream", [("human", "hi")], budget_ms=5_000, message_id="m1"
        )
    ]
    assert (
        [e.kind for e in evs] == ["start", "delta", "end"]
        and evs[0].model_tier == "primary"
        and evs[0].alias == "b"
    )
