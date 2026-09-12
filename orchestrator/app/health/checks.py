"""各组件健康探测。每次请求实时探测，超时即 down，保证组件停掉后 10 s 内可见。"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Literal

import httpx
import psycopg
import redis.asyncio as aioredis
import yaml

Status = Literal["ok", "down", "unconfigured"]


@dataclass
class ComponentHealth:
    status: Status
    latency_ms: int | None = None
    detail: str | None = None
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        out: dict = {"status": self.status}
        if self.latency_ms is not None:
            out["latency_ms"] = self.latency_ms
        if self.detail:
            out["detail"] = self.detail
        out.update(self.extra)
        return out


async def _timed(coro, timeout_s: float) -> tuple[Status, int, str | None]:
    start = time.perf_counter()
    try:
        await asyncio.wait_for(coro, timeout=timeout_s)
        return "ok", _ms(start), None
    except TimeoutError:
        return "down", _ms(start), f"timeout after {timeout_s}s"
    except Exception as exc:  # noqa: BLE001 - 健康探测要把任何异常收敛为 down
        return "down", _ms(start), _short(exc)


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _short(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}".strip()
    return text[:200]


async def check_db(database_url: str, timeout_s: float) -> ComponentHealth:
    async def _ping() -> None:
        async with (
            await psycopg.AsyncConnection.connect(
                database_url, connect_timeout=int(max(1, timeout_s))
            ) as conn,
            conn.cursor() as cur,
        ):
            await cur.execute("SELECT 1")
            await cur.fetchone()

    status, ms, detail = await _timed(_ping(), timeout_s)
    return ComponentHealth(status, ms, detail)


async def check_redis(redis_url: str, timeout_s: float) -> ComponentHealth:
    async def _ping() -> None:
        client = aioredis.from_url(
            redis_url, socket_connect_timeout=timeout_s, socket_timeout=timeout_s
        )
        try:
            await client.ping()
        finally:
            await client.aclose()

    status, ms, detail = await _timed(_ping(), timeout_s)
    return ComponentHealth(status, ms, detail)


async def check_weknora(base_url: str, timeout_s: float) -> ComponentHealth:
    async def _ping() -> None:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/health")
            resp.raise_for_status()

    status, ms, detail = await _timed(_ping(), timeout_s)
    return ComponentHealth(status, ms, detail)


def check_models(models_config_path: str, default_lane: str) -> dict[str, ComponentHealth]:
    """模型通道按「配置存在 + 通道内厂商 key 是否齐全」报告，不发真实请求（票 09 再加探测 CLI）。"""
    try:
        with open(models_config_path, encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return {
            default_lane: ComponentHealth("unconfigured", detail=f"{models_config_path} not found")
        }
    except yaml.YAMLError as exc:
        return {default_lane: ComponentHealth("down", detail=f"invalid yaml: {_short(exc)}")}

    providers: dict = cfg.get("providers", {}) or {}
    models: dict = cfg.get("models", {}) or {}
    lanes: dict = cfg.get("lanes", {}) or {}
    result: dict[str, ComponentHealth] = {}
    for lane_name, tasks in lanes.items():
        needed_providers: set[str] = set()
        for task_cfg in (tasks or {}).values():
            for alias in (task_cfg or {}).get("chain", []):
                provider = (models.get(alias) or {}).get("provider")
                if provider:
                    needed_providers.add(provider)
        missing = sorted(
            p
            for p in needed_providers
            if not os.environ.get((providers.get(p) or {}).get("api_key_env", ""))
        )
        configured = sorted(needed_providers - set(missing))
        status: Status = (
            "ok" if needed_providers and not missing else ("unconfigured" if missing else "down")
        )
        result[lane_name] = ComponentHealth(
            status,
            detail=None if not missing else f"missing api key for: {', '.join(missing)}",
            extra={"providers_ready": configured, "default": lane_name == default_lane},
        )
    if not result:
        result[default_lane] = ComponentHealth("down", detail="no lanes defined")
    return result
