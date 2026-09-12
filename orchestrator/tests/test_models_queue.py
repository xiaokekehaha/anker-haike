"""票 12：429 指数退避、全局有界门快速失败、结构化日志。"""

from __future__ import annotations

import asyncio
import json
import logging

import pytest
from pydantic import BaseModel

from app.models.config import load_models_config
from app.models.fake import FakeChatModel
from app.models.queue import BoundedGate, CapacityExceeded
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter
from tests.test_models_fallback import CONFIG, KEYS, rate_limited


class Out(BaseModel):
    v: int


OK = json.dumps({"v": 1})


@pytest.fixture
def cfg(tmp_path):
    p = tmp_path / "models.yaml"
    p.write_text(
        CONFIG.replace("rate_limit_max: 1", "rate_limit_max: 3").replace(
            "max_in_flight: 50", "max_in_flight: 5"
        ),
        encoding="utf-8",
    )
    return load_models_config(p)


def test_repo_config_has_queue_and_backoff_settings():
    from app.settings import REPO_ROOT

    c = load_models_config(REPO_ROOT / "config" / "models.yaml")
    assert c.concurrency.max_in_flight == 50
    assert c.retry.rate_limit_max == 3


async def test_429_exponential_backoff_1_2_4_then_next_model(cfg):
    sleeps: list[float] = []

    async def sleep(s):
        sleeps.append(s)

    fakes = {"a": FakeChatModel(script=[rate_limited()] * 4), "b": FakeChatModel(script=[OK])}
    router = ModelRouter(
        ModelRegistry(cfg, env=KEYS),
        model_factory=lambda r, _: fakes[r.alias],
        sleep=sleep,
        rng=lambda: 0.0,
    )
    res = await router.invoke("intake", [("human", "x")], Out, budget_ms=60_000)
    assert sleeps == [1.0, 2.0, 4.0]
    assert [a.outcome for a in res.attempts] == ["rate_limited"] * 4 + ["ok"]
    assert res.alias == "b"


async def test_429_backoff_respects_budget(cfg):
    clock = {"t": 0.0}
    sleeps: list[float] = []

    async def sleep(s):
        sleeps.append(s)
        clock["t"] += s

    fakes = {"a": FakeChatModel(script=[rate_limited()] * 4), "b": FakeChatModel(script=[OK])}
    router = ModelRouter(
        ModelRegistry(cfg, env=KEYS),
        model_factory=lambda r, _: fakes[r.alias],
        sleep=sleep,
        rng=lambda: 0.0,
        clock=lambda: clock["t"],
    )
    # 预算 4.5 s：1 s 退避可以，2 s 退避后剩 1.5 s 可以，4 s 退避 + 1 s 余量超预算 → 停
    from app.models.router import ModelInvokeError

    with pytest.raises(ModelInvokeError, match="budget exhausted"):
        await router.invoke("intake", [("human", "x")], Out, budget_ms=4_500)
    assert sleeps == [1.0, 2.0]
    assert fakes["b"].calls == []


class BlockingFake(FakeChatModel):
    """挂住直到 release 被 set，用来把并发数顶到上限。"""

    release: asyncio.Event | None = None

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        assert self.release is not None
        await self.release.wait()
        return self._next(messages, run_manager, kwargs)


async def test_gate_rejects_fast_when_full_and_recovers(cfg, caplog):
    release = asyncio.Event()
    gate = BoundedGate(cfg.concurrency.max_in_flight)  # 5
    fakes = {"a": BlockingFake(script=[OK] * 5, release=release)}
    router = ModelRouter(
        ModelRegistry(cfg, env=KEYS), model_factory=lambda r, _: fakes[r.alias], gate=gate
    )

    async def one():
        try:
            return await router.invoke("intake", [("human", "x")], Out, budget_ms=10_000)
        except CapacityExceeded as exc:
            return exc

    caplog.set_level(logging.DEBUG, logger="models.queue")
    tasks = [asyncio.create_task(one()) for _ in range(8)]
    await asyncio.sleep(0.05)  # 前 5 个占满门，后 3 个应已被立即拒绝
    rejected = [t for t in tasks if t.done()]
    assert len(rejected) == 3 and all(isinstance(t.result(), CapacityExceeded) for t in rejected)
    assert gate.snapshot()["in_flight"] == 5 and gate.snapshot()["rejected_total"] == 3

    release.set()
    results = await asyncio.gather(*tasks)
    ok = [r for r in results if not isinstance(r, CapacityExceeded)]
    assert len(ok) == 5 and all(r.parsed.v == 1 for r in ok)
    snap = gate.snapshot()
    assert snap == {"in_flight": 0, "limit": 5, "peak": 5, "admitted_total": 5, "rejected_total": 3}

    full = [r for r in caplog.records if getattr(r, "event", None) == "model_queue_full"]
    assert len(full) == 3
    assert full[0].in_flight == 5 and full[0].limit == 5 and full[0].task == "intake"
    assert full[-1].rejected_total == 3

    # 门释放后新的请求可以进入
    fakes["a"].script.append(OK)
    assert (await router.invoke("intake", [("human", "x")], Out, budget_ms=10_000)).parsed.v == 1


def test_capacity_error_maps_to_recoverable_error_fields():
    exc = CapacityExceeded("intake", 50, 50)
    fields = exc.as_error_fields()
    assert fields["recoverable"] is True and fields["retry_with_same_action"] is True
    assert fields["code"] == "model_capacity_exceeded" and fields["message"]


async def test_gate_released_on_failure(cfg):
    gate = BoundedGate(1)
    fakes = {
        "a": FakeChatModel(script=[RuntimeError("x")]),
        "b": FakeChatModel(script=[]),
        "c": FakeChatModel(script=[]),
    }
    router = ModelRouter(
        ModelRegistry(cfg, env={"K1": "x"}), model_factory=lambda r, _: fakes[r.alias], gate=gate
    )
    from app.models.router import ModelInvokeError

    with pytest.raises(ModelInvokeError):
        await router.invoke("intake", [("human", "x")], Out, budget_ms=5_000)
    assert gate.in_flight == 0


def test_gate_rejects_bad_limit():
    with pytest.raises(ValueError):
        BoundedGate(0)
