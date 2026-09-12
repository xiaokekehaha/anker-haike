from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter, Query, Response

from app.health.checks import check_db, check_models, check_redis, check_weknora
from app.replay import runtime as replay_runtime
from app.settings import settings

router = APIRouter(tags=["health"])

CACHE_TTL_S = 3.0


class HealthAggregator:
    """聚合探测，带 3 s 缓存：前端 10 s 轮询与 Compose 探针不会把依赖打爆，
    同时组件停掉后状态变化仍在 10 s 内可见。"""

    def __init__(self) -> None:
        self._cache: dict[str, Any] | None = None
        self._cached_at = 0.0
        self._lock = asyncio.Lock()

    async def snapshot(self, *, force: bool = False) -> dict[str, Any]:
        if not force and self._fresh():
            return self._cache  # type: ignore[return-value]
        async with self._lock:
            if not force and self._fresh():
                return self._cache  # type: ignore[return-value]
            self._cache = await self._probe()
            self._cached_at = time.monotonic()
            return self._cache

    def _fresh(self) -> bool:
        return self._cache is not None and time.monotonic() - self._cached_at < CACHE_TTL_S

    async def _probe(self) -> dict[str, Any]:
        t = settings.health_timeout_s
        db, rds, wk = await asyncio.gather(
            check_db(settings.database_url, t),
            check_redis(settings.redis_url, t),
            check_weknora(settings.weknora_base_url, t),
        )
        models = check_models(settings.models_config_path, settings.model_lane)
        default_lane = models.get(settings.model_lane)
        # 整体状态：db 与 weknora 必须 ok，默认通道模型配置必须 ok；redis 只报告（WeKnora 依赖）
        critical_ok = (
            db.status == "ok"
            and wk.status == "ok"
            and default_lane is not None
            and default_lane.status == "ok"
        )
        body = {
            "status": "ok" if critical_ok else "degraded",
            "lane": settings.model_lane,
            "cache_ttl_s": CACHE_TTL_S,
            "components": {
                "db": db.as_dict(),
                "redis": rds.as_dict(),
                "weknora": wk.as_dict(),
                "models": {lane: h.as_dict() for lane, h in models.items()},
            },
        }
        # 票 43：回放模式只在 REPLAY_CASE_ID 设置时出现；前端据此显示「演示回放」徽标
        replay = replay_runtime.describe()
        if replay is not None:
            body["replay"] = replay
        return body


aggregator = HealthAggregator()


@router.get("/health")
async def health(
    response: Response,
    force: bool = Query(default=False, description="跳过缓存，强制重新探测"),
) -> dict[str, Any]:
    """聚合健康：db / redis / weknora 实时探测，models 按通道报告配置状态。db 不可用返回 503。"""
    body = await aggregator.snapshot(force=force)
    if body["components"]["db"]["status"] != "ok":
        response.status_code = 503
    return body


@router.get("/health/live")
async def live() -> dict[str, str]:
    """存活探针，供 Compose healthcheck 使用，不依赖外部组件。"""
    return {"status": "ok"}
