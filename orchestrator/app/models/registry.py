"""别名 → LangChain 聊天模型实例（model-selection §3.5 实现要点）。

- 统一入口 `init_chat_model`；国内厂商走 openai 协议 + base_url。
- API key 只从环境变量读取，不出现在日志、异常与 repr 中。
- 厂商 SDK max_retries 固定为 retry.sdk_max_retries（0）；重试只在 ModelRouter（票 11）。
- effort → 参数映射：Claude 传 output_config.effort，其他厂商传 temperature。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from app.models.config import Effort, Lane, ModelsConfig, ModelSpec, ProviderSpec, TaskRoute

# 非 Claude 厂商：抽象档位 → temperature（model-selection §3.5）
EFFORT_TEMPERATURE: dict[Effort, float] = {"low": 0.0, "medium": 0.2, "high": 0.3}


class ModelNotConfigured(RuntimeError):
    """别名当前不可用：真实模型 ID 未填或厂商 key 缺失。message 不含 key 内容。"""

    def __init__(self, alias: str, reason: str):
        self.alias = alias
        self.reason = reason
        super().__init__(f"model alias {alias!r} not configured: {reason}")


@dataclass(frozen=True)
class ResolvedModel:
    alias: str
    spec: ModelSpec
    provider_name: str
    provider: ProviderSpec

    @property
    def lane(self) -> Lane:
        return self.provider.lane

    @property
    def model_used(self) -> str:
        """写入 attempts / model_trace 的可读标识：provider/真实 id。"""
        return f"{self.provider_name}/{self.spec.id}"


def provider_params(sdk: str, effort: Effort) -> dict[str, Any]:
    """按厂商映射 effort。只有 Claude 有 effort 概念；其余映射为低温度。"""
    if sdk == "anthropic":
        return {"output_config": {"effort": effort}}
    return {"temperature": EFFORT_TEMPERATURE[effort]}


class ModelRegistry:
    def __init__(self, cfg: ModelsConfig, env: dict[str, str] | None = None):
        self.cfg = cfg
        self._env = env if env is not None else os.environ

    # ---- 解析 ----
    def resolve(self, alias: str) -> ResolvedModel:
        spec = self.cfg.models[alias]
        return ResolvedModel(alias, spec, spec.provider, self.cfg.providers[spec.provider])

    def chain(self, task: str, lane: str | None = None) -> list[ResolvedModel]:
        """task 在通道下的完整降级链（不做能力过滤，过滤在票 11 的 Router 里）。"""
        return [self.resolve(a) for a in self.cfg.route(task, lane).chain]

    # ---- 可用性 ----
    def api_key(self, provider_name: str) -> str | None:
        return self._env.get(self.cfg.providers[provider_name].api_key_env) or None

    def unavailable_reason(self, alias: str) -> str | None:
        r = self.resolve(alias)
        if r.spec.id_pending:
            return "model id is TBD (fill in config/models.yaml, see ticket 42)"
        if not self.api_key(r.provider_name):
            return f"missing env {r.provider.api_key_env}"
        return None

    def is_available(self, alias: str) -> bool:
        return self.unavailable_reason(alias) is None

    def first_available(self, task: str, lane: str | None = None) -> ResolvedModel | None:
        for r in self.chain(task, lane):
            if self.is_available(r.alias):
                return r
        return None

    # ---- 构建 ----
    def build(
        self,
        alias: str,
        *,
        effort: Effort = "low",
        max_tokens: int | None = None,
        timeout_s: float | None = None,
        route: TaskRoute | None = None,
        max_retries: int | None = None,
    ) -> BaseChatModel:
        """建 LangChain 实例。`route` 给定时 effort / max_tokens 取自它（显式参数优先）。"""
        r = self.resolve(alias)
        reason = self.unavailable_reason(alias)
        if reason:
            raise ModelNotConfigured(alias, reason)
        if route is not None:
            effort = effort if effort != "low" or route.effort == "low" else route.effort
            max_tokens = max_tokens if max_tokens is not None else route.max_tokens
        kwargs: dict[str, Any] = {
            "model_provider": r.provider.sdk,
            "api_key": self.api_key(r.provider_name),
            "max_retries": self.cfg.retry.sdk_max_retries if max_retries is None else max_retries,
            "timeout": timeout_s if timeout_s is not None else r.spec.timeout_s,
        }
        if r.provider.base_url:
            kwargs["base_url"] = r.provider.base_url
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        kwargs.update(provider_params(r.provider.sdk, effort))
        if r.spec.params:
            # 票 42：厂商专属参数。openai 兼容协议只能经 extra_body 进请求体（如 DeepSeek 关思考）
            if r.provider.sdk == "openai":
                kwargs["extra_body"] = dict(r.spec.params)
            else:
                kwargs.update(r.spec.params)
        return init_chat_model(r.spec.id, **kwargs)

    def build_for_task(self, task: str, alias: str, lane: str | None = None) -> BaseChatModel:
        route = self.cfg.route(task, lane)
        return self.build(alias, effort=route.effort, max_tokens=route.max_tokens, route=route)

    # ---- 展示 ----
    def describe(self) -> dict[str, Any]:
        """启动日志用：只有别名、厂商、id 与 key 是否就绪，绝不含 key。"""
        return {
            "version": self.cfg.version,
            "default_lane": self.cfg.default_lane,
            "providers": {
                name: {
                    "sdk": p.sdk,
                    "lane": p.lane,
                    "key": "set" if self.api_key(name) else "missing",
                }
                for name, p in self.cfg.providers.items()
            },
            "pending_ids": sorted(a for a, m in self.cfg.models.items() if m.id_pending),
        }
