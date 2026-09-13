"""验证连通性列表的真实边界：不自动调用、不降级、不泄露厂商原始异常。"""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage

from app.main import create_app
from app.models import probe as probe_module
from app.models.config import load_models_config
from app.models.probe import ModelProbes, ProbeBusy, failure_detail
from app.models.registry import ModelRegistry
from tests.test_models_config import MINIMAL


@pytest.fixture
def service(tmp_path):
    config = tmp_path / "models.yaml"
    config.write_text(MINIMAL)
    registry = ModelRegistry(load_models_config(config), env={"T_DS": "test-secret"})
    return ModelProbes(registry)


@pytest.fixture
async def client(service):
    app = create_app()
    app.state.model_probes = service
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    await service.close()


async def test_list_and_unconfigured_probe_never_call_models(client, service, monkeypatch):
    build = Mock(side_effect=AssertionError("must not call a model"))
    monkeypatch.setattr(service.registry, "build", build)
    response = await client.get("/models/status")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    rows = {row["alias"]: row for row in response.json()["models"]}
    assert set(rows) == {"deepseek", "sonnet"}  # 不对 embedding/rerank 冒充聊天检测
    assert rows["deepseek"]["status"] == "unchecked"
    assert rows["sonnet"]["status"] == "unconfigured"
    assert all(row["current_lane"] for row in rows.values())  # 含跨通道备用模型
    result = await client.post("/models/sonnet/probe")
    assert result.json()["detail"] == "缺少密钥"
    assert "test-secret" not in response.text + result.text
    assert build.call_count == 0


async def test_success_direct_alias_zero_retries_and_cached_get(client, service, monkeypatch):
    model = Mock(ainvoke=AsyncMock(return_value=AIMessage(content="收到")))
    build = Mock(return_value=model)
    monkeypatch.setattr(service.registry, "build", build)
    service.registry.cfg.retry.sdk_max_retries = 3  # 探测必须覆盖此配置
    result = (await client.post("/models/deepseek/probe")).json()
    assert result["status"] == "connected"
    assert result["checked_at"] and result["expires_at"]
    assert result["latency_ms"] >= 0
    build.assert_called_once_with(
        "deepseek", effort="low", max_tokens=16, timeout_s=20, max_retries=0
    )
    model.ainvoke.assert_awaited_once_with(probe_module.PROBE_PROMPT)
    rows = (await client.get("/models/status")).json()["models"]
    assert next(row for row in rows if row["alias"] == "deepseek") == result
    assert build.call_count == 1


async def test_failure_does_not_fallback_and_never_exposes_raw_error(client, service, monkeypatch):
    service.registry._env["T_AN"] = "another-secret"
    model = Mock(ainvoke=AsyncMock(side_effect=RuntimeError("key=test-secret https://private")))
    build = Mock(return_value=model)
    monkeypatch.setattr(service.registry, "build", build)
    response = await client.post("/models/deepseek/probe")
    assert response.json()["status"] == "failed"
    assert response.json()["detail"] == "调用失败，请检查模型配置后重试"
    assert "test-secret" not in response.text and "https://private" not in response.text
    assert [call.args[0] for call in build.call_args_list] == ["deepseek"]
    assert model.ainvoke.await_count == 1


@pytest.mark.parametrize("content", ["", [{"type": "reasoning", "reasoning": "internal"}]])
async def test_empty_or_reasoning_only_response_is_not_connected(service, monkeypatch, content):
    monkeypatch.setattr(
        service.registry,
        "build",
        Mock(return_value=Mock(ainvoke=AsyncMock(return_value=AIMessage(content=content)))),
    )
    assert (await service.probe("deepseek")).status == "failed"


async def test_expired_results_become_unchecked_without_another_request(service, monkeypatch):
    model = Mock(ainvoke=AsyncMock(return_value=AIMessage(content="收到")))
    monkeypatch.setattr(service.registry, "build", Mock(return_value=model))
    result = await service.probe("deepseek")
    completed_at, cached = service._results["deepseek"]
    service._results["deepseek"] = (completed_at - 301, cached)
    row = next(row for row in service.snapshot().models if row.alias == "deepseek")
    assert row.status == "unchecked" and "过期" in row.detail
    assert row.checked_at == result.checked_at
    assert model.ainvoke.await_count == 1


async def test_duplicate_requests_share_call_and_disconnect_does_not_cancel_it(
    service, monkeypatch
):
    entered, release = asyncio.Event(), asyncio.Event()

    async def invoke(*_args):
        entered.set()
        await release.wait()
        return AIMessage(content="收到")

    model = Mock(ainvoke=AsyncMock(side_effect=invoke))
    monkeypatch.setattr(service.registry, "build", Mock(return_value=model))
    first = asyncio.create_task(service.probe("deepseek"))
    await entered.wait()
    assert service.snapshot().models[0].status == "checking"
    second = asyncio.create_task(service.probe("deepseek"))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    assert (await second).status == "connected"
    assert model.ainvoke.await_count == 1


async def test_concurrency_is_bounded(service, monkeypatch):
    service.registry._env["T_AN"] = "test-an"
    service.registry.cfg.models["extra"] = service.registry.cfg.models["deepseek"].model_copy()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def invoke(*_args):
        entered.set()
        await release.wait()
        return AIMessage(content="收到")

    monkeypatch.setattr(
        service.registry, "build", Mock(return_value=Mock(ainvoke=AsyncMock(side_effect=invoke)))
    )
    first = asyncio.create_task(service.probe("deepseek"))
    await entered.wait()
    entered.clear()
    second = asyncio.create_task(service.probe("sonnet"))
    await entered.wait()
    with pytest.raises(ProbeBusy):
        await service.probe("extra")
    release.set()
    await asyncio.gather(first, second)
    assert not service._running


async def test_outer_timeout_cancels_hung_sdk(service, monkeypatch):
    cancelled = asyncio.Event()

    async def invoke(*_args):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(probe_module, "PROBE_TIMEOUT_S", 0.01)
    monkeypatch.setattr(
        service.registry, "build", Mock(return_value=Mock(ainvoke=AsyncMock(side_effect=invoke)))
    )
    result = await service.probe("deepseek")
    assert result.status == "failed" and result.detail == "请求超时"
    assert cancelled.is_set()


async def test_unknown_nonchat_and_disabled_models(client, service):
    for alias in ("missing", "embed", "rerank"):
        assert (await client.post(f"/models/{alias}/probe")).status_code == 404
    service.disabled_reason = "演示回放模式不发起真实模型检测"
    assert not (await client.get("/models/status")).json()["probe_enabled"]
    assert (await client.post("/models/deepseek/probe")).status_code == 409


@pytest.mark.parametrize(
    ("code", "detail"),
    [
        (401, "密钥无效或已过期"),
        (403, "没有访问该模型的权限"),
        (404, "模型不存在或当前账号不可访问"),
        (429, "请求限流或额度不足，请稍后重试"),
        (400, "模型不接受当前请求参数"),
        (503, "模型服务暂时异常"),
    ],
)
def test_safe_error_categories(code, detail):
    error = RuntimeError("secret")
    error.status_code = code
    assert failure_detail(error) == detail


def test_other_lane_is_based_on_route_membership(service):
    service.registry.cfg.default_lane = "overseas"
    rows = {row.alias: row for row in service.snapshot().models}
    assert rows["sonnet"].current_lane and not rows["deepseek"].current_lane
