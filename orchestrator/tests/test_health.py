import pytest
from httpx import ASGITransport, AsyncClient

from app.health import checks
from app.health import router as health_router
from app.main import app


@pytest.fixture(autouse=True)
def _fresh_cache():
    health_router.aggregator._cache = None
    yield
    health_router.aggregator._cache = None


def _patch_all(monkeypatch, fn):
    for name in ("check_db", "check_redis", "check_weknora"):
        monkeypatch.setattr(health_router, name, fn)


async def _down(*_a, **_k):
    return checks.ComponentHealth("down", 1, "connection refused")


async def _ok(*_a, **_k):
    return checks.ComponentHealth("ok", 1)


async def test_all_down_reports_each_component(monkeypatch):
    _patch_all(monkeypatch, _down)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    for name in ("db", "redis", "weknora"):
        assert body["components"][name]["status"] == "down"
    assert "models" in body["components"]


async def test_ok_components_but_missing_model_keys_is_degraded_200(monkeypatch):
    _patch_all(monkeypatch, _ok)
    monkeypatch.setattr(
        health_router,
        "check_models",
        lambda *_a: {
            "domestic": checks.ComponentHealth("unconfigured", detail="missing api key for: zhipu")
        },
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "degraded"
    assert resp.json()["components"]["db"]["status"] == "ok"


async def test_cache_then_force_refresh(monkeypatch):
    calls = {"n": 0}

    async def counting(*_a, **_k):
        calls["n"] += 1
        return checks.ComponentHealth("ok", 1)

    _patch_all(monkeypatch, counting)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        await client.get("/health")
        await client.get("/health")
        assert calls["n"] == 3  # 三个组件各探测一次，第二次命中缓存
        await client.get("/health?force=true")
        assert calls["n"] == 6


async def test_live_probe_has_no_dependencies():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_models_lane_reports_missing_keys(tmp_path, monkeypatch):
    cfg = tmp_path / "models.yaml"
    cfg.write_text(
        """
providers:
  deepseek: {sdk: openai, api_key_env: TEST_DEEPSEEK_KEY}
  zhipu:    {sdk: openai, api_key_env: TEST_ZHIPU_KEY}
models:
  deepseek: {provider: deepseek, id: x}
  glm:      {provider: zhipu, id: y}
lanes:
  domestic:
    intake: {chain: [deepseek, glm]}
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("TEST_ZHIPU_KEY", raising=False)
    monkeypatch.setenv("TEST_DEEPSEEK_KEY", "k")
    lane = checks.check_models(str(cfg), "domestic")["domestic"]
    assert lane.status == "unconfigured"
    assert "zhipu" in (lane.detail or "")
    assert lane.extra["providers_ready"] == ["deepseek"]

    monkeypatch.setenv("TEST_ZHIPU_KEY", "k2")
    assert checks.check_models(str(cfg), "domestic")["domestic"].status == "ok"


def test_models_missing_file_is_unconfigured():
    result = checks.check_models("/nonexistent/models.yaml", "domestic")
    assert result["domestic"].status == "unconfigured"
