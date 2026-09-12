"""票 50：最简告警——四条规则、冷却、恢复、投递；模型全部失败后经 record() 钩子触发并投递到 webhook。"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.models.config import load_models_config
from app.models.fake import FakeChatModel
from app.models.registry import ModelRegistry
from app.models.router import ModelInvokeError, ModelRouter
from app.observability.alerts import (
    AlertManager,
    Thresholds,
    WebhookSink,
    build_from_settings,
    format_text,
    health_watch_loop,
    set_alert_manager,
)
from app.settings import settings
from tests.test_reply_stream import CONFIG


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class MemorySink:
    name = "memory"

    def __init__(self, fail: bool = False) -> None:
        self.alerts: list[dict] = []
        self.fail = fail

    async def send(self, alert: dict) -> bool:
        if self.fail:
            raise RuntimeError("sink down")
        self.alerts.append(alert)
        return True


def test_model_chain_failed_fires_once_per_cooldown_and_resolves():
    clock = Clock()
    m = AlertManager([], Thresholds(model_fail_streak=3, cooldown_s=300), clock=clock)
    for _ in range(2):
        m.observe_model_call("error", "intake")
    assert m.sent == [] and m.snapshot()["model_fail_streak"] == 2
    m.observe_model_call("error", "intake")
    assert [a["rule"] for a in m.sent] == ["model_chain_failed"] and m.rules["model_chain_failed"].active
    # 冷却期内继续失败只计 suppressed，不重复投递
    for _ in range(5):
        m.observe_model_call("error", "reply.stream")
    assert len(m.sent) == 1 and m.rules["model_chain_failed"].suppressed_total == 5
    # 冷却过后仍在失败 → 再发一条
    clock.now += 301
    m.observe_model_call("error", "reply.stream")
    assert len(m.sent) == 2 and m.rules["model_chain_failed"].fired_total == 2
    # 取消不算失败；成功 → 恢复通知
    m.observe_model_call("cancelled", "reply.stream")
    m.observe_model_call("ok", "intake")
    assert m.sent[-1]["resolved"] is True and not m.rules["model_chain_failed"].active
    assert m.snapshot()["active"] == [] and m.snapshot()["model_fail_streak"] == 0


def test_retrieval_empty_rate_needs_min_samples_and_resolves():
    m = AlertManager([], Thresholds(retrieval_min_samples=10, retrieval_window=20))
    for _ in range(9):
        m.observe_knowledge_search("no_match")
    assert m.sent == []  # 样本不足
    m.observe_knowledge_search("unavailable")
    assert [a["rule"] for a in m.sent] == ["retrieval_empty_rate"]
    assert m.rules["retrieval_empty_rate"].detail == {"window": 10, "empty": 10, "rate": 1.0}
    for _ in range(12):
        m.observe_knowledge_search("ok")  # 窗口滑到 8/20 = 40% → 恢复
    assert m.sent[-1]["resolved"] is True and m.sent[-1]["rule"] == "retrieval_empty_rate"


def test_queue_rejection_rate_over_window():
    clock = Clock()
    m = AlertManager([], Thresholds(queue_min_rejects=5, queue_reject_rate=0.2, queue_window_s=60), clock=clock)
    # 100 次准入 + 4 次拒绝 → 不到最小拒绝数
    m.observe_queue(rejected=True, admitted_total=100)
    for _ in range(3):
        m.observe_queue(rejected=True, admitted_total=100)
    assert m.sent == []
    m.observe_queue(rejected=True, admitted_total=100)  # 第 5 次拒绝：5/(1+? ) 首次 admitted_total 只作基线 → 5/5
    assert [a["rule"] for a in m.sent] == ["queue_rejections"]
    # 60 s 后窗口滑空，再来大量准入 + 1 次拒绝 → 率低 → 不再触发；准入事件带来恢复
    clock.now += 61
    m.observe_queue(rejected=True, admitted_total=150)  # 50 次准入 + 1 拒绝 = 2%
    assert len(m.sent) == 1 and m.rules["queue_rejections"].active  # 拒绝事件本身不触发恢复
    m.observe_queue(rejected=False)
    assert m.sent[-1]["resolved"] is True


def test_health_streak_and_watch_loop():
    m = AlertManager([], Thresholds(health_fail_streak=3))
    m.observe_health(False, {"components": {"db": "down"}})
    m.observe_health(False, {"components": {"db": "down"}})
    assert m.sent == []
    m.observe_health(False, {"components": {"db": "down"}})
    assert m.sent[-1]["rule"] == "health_check_failed" and "db" in m.sent[-1]["summary"]
    m.observe_health(True)
    assert m.sent[-1]["resolved"] is True


async def test_health_watch_loop_probes_aggregator():
    class Agg:
        def __init__(self) -> None:
            self.calls = 0

        async def snapshot(self, *, force: bool = False):
            self.calls += 1
            return {"status": "degraded", "components": {"db": {"status": "ok"}, "weknora": {"status": "down"}}}

    m = AlertManager([], Thresholds(health_fail_streak=2))
    agg = Agg()
    task = asyncio.create_task(health_watch_loop(agg, m, 0.01))
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert agg.calls >= 2 and m.sent and m.sent[0]["rule"] == "health_check_failed"
    assert m.sent[0]["detail"]["components"] == {"weknora": "down"}


async def test_webhook_sink_payload_and_delivery_failure_is_nonfatal():
    received: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        received.append(json.loads(request.content))
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    good = WebhookSink("http://hook.test/x", client=client)
    bad = MemorySink(fail=True)
    m = AlertManager([good, bad], Thresholds(model_fail_streak=1))
    m.observe_model_call("error", "intake")
    await m.drain()
    assert len(received) == 1
    body = received[0]
    assert body["msg_type"] == "text" and body["alert"]["rule"] == "model_chain_failed"
    assert "[haike] model_chain_failed 触发" in body["text"]["content"]
    assert format_text(body["alert"]).startswith("[haike] model_chain_failed 触发")
    assert m.rules["model_chain_failed"].fired_total == 1  # 一个 sink 失败不影响状态
    await client.aclose()


async def test_all_models_failing_alerts_through_record_hook(tmp_path):
    """人为制造模型全部失败：三次链耗尽后一条告警到达 webhook（远小于 5 分钟）。"""
    received: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        received.append(json.loads(request.content))
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    m = AlertManager([WebhookSink("http://hook.test/alert", client=client)], Thresholds(model_fail_streak=3))
    set_alert_manager(m)
    try:
        p = tmp_path / "models.yaml"
        p.write_text(CONFIG, encoding="utf-8")
        dead = FakeChatModel(script=[RuntimeError("boom")] * 20, name_for_trace="dead")
        router = ModelRouter(
            ModelRegistry(load_models_config(p), env={"K1": "x", "K2": "x"}),
            model_factory=lambda r, _: dead,
        )
        from pydantic import BaseModel

        class Out(BaseModel):
            x: int

        for _ in range(3):
            with pytest.raises(ModelInvokeError):
                await router.invoke("intake", [("human", "hi")], Out, budget_ms=2000, session_id="s", lane="domestic")
        await m.drain()
        assert [a["rule"] for a in m.sent] == ["model_chain_failed"]
        assert len(received) == 1 and received[0]["alert"]["detail"]["streak"] == 3
        snap = m.snapshot()
        assert snap["active"] == ["model_chain_failed"] and snap["rules"]["model_chain_failed"]["fired_total"] == 1
    finally:
        set_alert_manager(None)
        await client.aclose()


def test_build_from_settings_sinks(monkeypatch):
    monkeypatch.setattr(settings, "alert_webhook_url", "")
    monkeypatch.setattr(settings, "alert_email_to", "")
    assert build_from_settings(settings).sinks == []
    monkeypatch.setattr(settings, "alert_webhook_url", "http://hook.test/x")
    monkeypatch.setattr(settings, "alert_email_to", "a@x.com, b@x.com")
    monkeypatch.setattr(settings, "alert_smtp_host", "smtp.x.com")
    monkeypatch.setattr(settings, "alert_model_fail_streak", 5)
    m = build_from_settings(settings)
    assert [s.name for s in m.sinks] == ["webhook", "email"] and m.t.model_fail_streak == 5
    assert m.sinks[1].recipients == ["a@x.com", "b@x.com"]


async def test_health_endpoint_exposes_alerts_block(mem_runtime):
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    m = AlertManager([], Thresholds(model_fail_streak=1))
    set_alert_manager(m)
    try:
        m.observe_model_call("error", "intake")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            body = (await client.get("/health?force=1")).json()
        assert body["alerts"]["active"] == ["model_chain_failed"]
        assert body["alerts"]["rules"]["model_chain_failed"]["fired_total"] == 1
    finally:
        set_alert_manager(None)
