"""按模型直连的手动探测。配置不等于连通；不经过业务降级链。"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel

from app.models.config import Effort
from app.models.registry import ModelRegistry

PROBE_PROMPT = "只回复两个字：收到"
CACHE_TTL_S = 300
PROBE_TIMEOUT_S = 20
MAX_CONCURRENT_PROBES = 2


class ModelStatus(BaseModel):
    alias: str
    model_id: str
    provider: str
    current_lane: bool
    configured: bool
    status: Literal["unconfigured", "unchecked", "checking", "connected", "failed"]
    detail: str | None = None
    latency_ms: int | None = None
    checked_at: datetime | None = None
    expires_at: datetime | None = None


class ModelStatuses(BaseModel):
    lane: str
    models: list[ModelStatus]
    probe_enabled: bool
    disabled_reason: str | None


class ProbeBusy(Exception):
    pass


def failure_detail(exc: Exception) -> str:
    """只输出固定原因，不回传厂商异常（可能包含 key、URL 或请求体）。"""
    name = type(exc).__name__
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if isinstance(exc, TimeoutError) or "Timeout" in name or "DeadlineExceeded" in name:
        return "请求超时"
    if code == 401 or name == "AuthenticationError":
        return "密钥无效或已过期"
    if code == 403 or name in {"PermissionDenied", "PermissionDeniedError"}:
        return "没有访问该模型的权限"
    if code == 404 or name == "NotFoundError":
        return "模型不存在或当前账号不可访问"
    if code == 429 or name in {"RateLimitError", "ResourceExhausted"}:
        return "请求限流或额度不足，请稍后重试"
    if code == 400 or name == "BadRequestError":
        return "模型不接受当前请求参数"
    if isinstance(code, int) and code >= 500:
        return "模型服务暂时异常"
    if "Connection" in name or isinstance(exc, ConnectionError):
        return "无法连接模型服务"
    return "调用失败，请检查模型配置后重试"


async def invoke_probe(
    registry: ModelRegistry, alias: str, timeout_s: float, *, effort: Effort = "low"
):
    # SDK 和外层均有时限；强制关闭重试，不允许 ModelRouter 自动换模型。
    async with asyncio.timeout(timeout_s):
        model = registry.build(
            alias, effort=effort, max_tokens=16, timeout_s=timeout_s, max_retries=0
        )
        return await model.ainvoke(PROBE_PROMPT)


class ModelProbes:
    def __init__(self, registry: ModelRegistry, *, disabled_reason: str | None = None):
        self.registry = registry
        self.disabled_reason = disabled_reason
        self._results: dict[str, tuple[float, ModelStatus]] = {}
        self._running: dict[str, asyncio.Task[ModelStatus]] = {}

    def _row(self, alias: str) -> ModelStatus:
        cfg = self.registry.cfg
        spec = cfg.models.get(alias)
        if spec is None or spec.kind != "chat":
            raise KeyError(alias)
        current = any(alias in route.chain for route in cfg.lanes[cfg.default_lane].values())
        reason = None
        if spec.id_pending:
            reason = "尚未配置模型 ID"
        elif not self.registry.api_key(spec.provider):
            reason = "缺少密钥"
        row = ModelStatus(
            alias=alias,
            model_id=spec.id,
            provider=spec.provider,
            current_lane=current,
            configured=reason is None,
            status="unconfigured" if reason else "unchecked",
            detail=reason,
        )
        if reason:
            self._results.pop(alias, None)
            return row
        if alias in self._running:
            return row.model_copy(update={"status": "checking"})
        cached = self._results.get(alias)
        if cached:
            completed_at, result = cached
            if time.monotonic() - completed_at < CACHE_TTL_S:
                return result.model_copy()
            row.detail = "上次检测已过期，请重新检测"
            row.checked_at = result.checked_at
            row.expires_at = result.expires_at
        return row

    def snapshot(self) -> ModelStatuses:
        rows = [self._row(a) for a in self.registry.cfg.aliases_of_kind("chat")]
        rows.sort(
            key=lambda row: (not row.current_lane, not row.configured, row.provider, row.alias)
        )
        return ModelStatuses(
            lane=self.registry.cfg.default_lane,
            models=rows,
            probe_enabled=self.disabled_reason is None,
            disabled_reason=self.disabled_reason,
        )

    async def probe(self, alias: str) -> ModelStatus:
        row = self._row(alias)
        if not row.configured:
            return row
        if self.disabled_reason:
            raise PermissionError(self.disabled_reason)
        running = self._running.get(alias)
        if running is None:
            if len(self._running) >= MAX_CONCURRENT_PROBES:
                raise ProbeBusy
            running = asyncio.create_task(self._probe(row))
            self._running[alias] = running
            running.add_done_callback(lambda _: self._running.pop(alias, None))
        # 重复点击共享同一次探测；关闭弹窗/HTTP 断开不取消其他访问者的探测。
        return await asyncio.shield(running)

    async def _probe(self, row: ModelStatus) -> ModelStatus:
        started = time.monotonic()
        timeout_s = min(PROBE_TIMEOUT_S, self.registry.cfg.models[row.alias].timeout_s)
        status = "connected"
        detail = None
        try:
            response = await invoke_probe(self.registry, row.alias, timeout_s)
            content = response.content
            has_text = (
                bool(content.strip())
                if isinstance(content, str)
                else any(
                    (isinstance(part, str) and part.strip())
                    or (
                        isinstance(part, dict)
                        and part.get("type") == "text"
                        and isinstance(part.get("text"), str)
                        and part["text"].strip()
                    )
                    for part in content
                )
            )
            if not has_text:
                status, detail = "failed", "模型未返回文本，请重试"
        except Exception as exc:  # noqa: BLE001 - 统一脱敏厂商错误
            status, detail = "failed", failure_detail(exc)
        checked_at = datetime.now(UTC)
        result = row.model_copy(
            update={
                "status": status,
                "detail": detail,
                "latency_ms": round((time.monotonic() - started) * 1000),
                "checked_at": checked_at,
                "expires_at": checked_at + timedelta(seconds=CACHE_TTL_S),
            }
        )
        self._results[row.alias] = (time.monotonic(), result)
        return result

    async def close(self) -> None:
        tasks = list(self._running.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
