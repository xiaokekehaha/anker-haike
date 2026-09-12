"""ModelRouter.invoke：结构化调用（票 10）+ 降级链与预算（票 11）。

策略（票 10）
- 按模型 `structured` 能力选：native → json_schema；json_object → JSON 模式 + schema 提示；none → 工具调用。
- 所有分支统一 Pydantic 校验；每次调用 tag=internal，metadata 含 task / session_id / lane / alias / method。

降级（票 11，model-selection §3.6 / 08 §8）
- 超时 / 429 / 5xx：同模型重试一次（退避 1 s + 抖动，429 走 1 / 2 / 4 s 指数），再失败换下一家。
- schema 校验失败：同模型带错误提示重试一次，再失败换下一家。
- 拒答（stop_reason=refusal / content_filter / 厂商安全拦截）：不重试，直接换下一家。
- 能力不匹配（需视觉而模型无视觉）与别名未配置：路由前跳过，记 skipped，不计入重试。
- 预算：单次超时 = min(模型 timeout_s, 剩余预算)；剩余不足以退避或再调一次时立即停止并返回最后错误。
- ModelRouter 是唯一重试层：厂商 SDK max_retries=0（registry 构建时固定）。
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.messages.utils import convert_to_messages
from pydantic import BaseModel, ValidationError

from app.models.config import Structured, TaskRoute
from app.models.registry import ModelRegistry, ResolvedModel

T = TypeVar("T", bound=BaseModel)
Method = Literal["json_schema", "json_object", "tools"]
Outcome = Literal[
    "ok", "schema_error", "timeout", "rate_limited", "server_error", "refusal", "error", "skipped"
]
RETRYABLE: frozenset[str] = frozenset({"timeout", "rate_limited", "server_error", "schema_error"})

METHOD_BY_CAPABILITY: dict[Structured, Method] = {
    "native": "json_schema",
    "json_object": "json_object",
    "none": "tools",
}
RATE_LIMIT_BACKOFF_S: tuple[float, ...] = (1.0, 2.0, 4.0)
DEFAULT_BACKOFF_S = 1.0
JITTER_S = 0.5

ModelFactory = Callable[[ResolvedModel, TaskRoute], BaseChatModel]


class SchemaError(ValueError):
    """模型输出不符合 schema；message 会作为下一次请求的错误提示。"""


class RefusalError(RuntimeError):
    """模型拒答或被厂商安全策略拦截；不重试。"""


@dataclass
class Attempt:
    alias: str
    model_used: str
    lane: str
    method: Method | None
    outcome: Outcome
    latency_ms: int
    error: str | None = None


@dataclass
class ModelResult[T: BaseModel]:
    parsed: T
    model_used: str
    alias: str
    lane: str
    method: Method
    latency_ms: int
    usage: dict[str, int] = field(default_factory=dict)
    attempts: list[Attempt] = field(default_factory=list)


class ModelInvokeError(RuntimeError):
    def __init__(self, task: str, attempts: list[Attempt], reason: str | None = None):
        self.task = task
        self.attempts = attempts
        last = next((a.error for a in reversed(attempts) if a.outcome != "skipped"), None)
        self.reason = reason or last or "no model available"
        super().__init__(f"task {task!r} failed after {len(attempts)} attempt(s): {self.reason}")


# ---- 分类 ----------------------------------------------------------------


def classify_exception(exc: BaseException) -> Outcome:
    """把厂商 SDK / 传输异常归为 timeout / rate_limited / server_error / refusal / error。"""
    if isinstance(exc, TimeoutError | asyncio.TimeoutError):
        return "timeout"
    name = type(exc).__name__
    status = getattr(exc, "status_code", None)
    if status is None:
        code = getattr(exc, "code", None)
        status = code if isinstance(code, int) else None
    text = str(exc).lower()
    if status == 429 or "RateLimit" in name or "ResourceExhausted" in name:
        return "rate_limited"
    if "Timeout" in name or "DeadlineExceeded" in name:
        return "timeout"
    if (
        status is not None
        and status >= 500
        or name in {"InternalServerError", "ServiceUnavailable"}
    ):
        return "server_error"
    if "APIConnectionError" in name:
        return "server_error"
    if isinstance(exc, RefusalError) or any(
        k in text for k in ("content_filter", "data_inspection_failed", "refusal", "safety")
    ):
        return "refusal"
    return "error"


def detect_refusal(msg: BaseMessage | None) -> str | None:
    meta = getattr(msg, "response_metadata", None) or {}
    stop = meta.get("stop_reason") or meta.get("finish_reason")
    if stop in {"refusal", "content_filter"}:
        return f"model refused (stop_reason={stop})"
    return None


def backoff_seconds(outcome: str, retry_no: int, rng: Callable[[], float] = random.random) -> float:
    """第 retry_no 次（从 0 起）重试前的等待：429 走 1 / 2 / 4 s，其余 1 s，均加 [0, 0.5) s 抖动。"""
    if outcome == "rate_limited":
        base = RATE_LIMIT_BACKOFF_S[min(retry_no, len(RATE_LIMIT_BACKOFF_S) - 1)]
    else:
        base = DEFAULT_BACKOFF_S
    return base + rng() * JITTER_S


def messages_have_images(messages: Sequence[BaseMessage]) -> bool:
    for m in messages:
        if isinstance(m.content, list):
            for part in m.content:
                if isinstance(part, dict) and part.get("type") in {"image", "image_url"}:
                    return True
    return False


# ---- 解析 ----------------------------------------------------------------


def _schema_hint(schema: type[BaseModel]) -> str:
    js = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    return (
        "你必须只输出一个 JSON 对象，不要 Markdown 代码块，不要解释。"
        f"JSON 必须符合以下 JSON Schema：\n{js}"
    )


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.DOTALL)


def _extract_json(text: str) -> Any:
    text = _FENCE.sub("", text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise SchemaError(f"not valid JSON: {exc.msg}") from exc


def _validation_text(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or '<root>'}: {e['msg']}" for e in exc.errors()
    )


def _usage(msg: BaseMessage | None) -> dict[str, int]:
    meta = getattr(msg, "usage_metadata", None) or {}
    return {k: int(v) for k, v in meta.items() if isinstance(v, int | float)}


def _short(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:300]


# ---- Router --------------------------------------------------------------


class ModelRouter:
    def __init__(
        self,
        registry: ModelRegistry,
        *,
        model_factory: ModelFactory | None = None,
        clock: Callable[[], float] = time.perf_counter,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: Callable[[], float] = random.random,
    ):
        self.registry = registry
        self._factory = model_factory or (
            lambda r, route: registry.build(
                r.alias, effort=route.effort, max_tokens=route.max_tokens
            )
        )
        self._clock = clock
        self._sleep = sleep
        self._rng = rng
        self.same_model_max = registry.cfg.retry.same_model_max
        self.chain_max = registry.cfg.retry.chain_max

    async def invoke(
        self,
        task: str,
        messages: Sequence[BaseMessage | tuple[str, str] | dict[str, Any]],
        schema: type[T],
        *,
        budget_ms: int,
        session_id: str | None = None,
        lane: str | None = None,
        method: Method | None = None,
    ) -> ModelResult[T]:
        route = self.registry.cfg.route(task, lane)
        lane = lane or self.registry.cfg.default_lane
        base_messages = convert_to_messages(list(messages))
        need_vision = route.needs_vision or messages_have_images(base_messages)
        attempts: list[Attempt] = []
        deadline = self._clock() + budget_ms / 1000

        def remaining_s() -> float:
            return deadline - self._clock()

        for resolved in self.registry.chain(task, lane)[: self.chain_max]:
            skip = self._skip_reason(resolved, need_vision)
            if skip:
                attempts.append(
                    Attempt(
                        resolved.alias, resolved.model_used, resolved.lane, None, "skipped", 0, skip
                    )
                )
                continue
            chosen: Method = method or METHOD_BY_CAPABILITY[resolved.spec.structured]
            model = self._factory(resolved, route)
            runnable, msgs = self._prepare(model, chosen, schema, base_messages)
            config = {
                "tags": ["internal"],
                "metadata": {
                    "task": task,
                    "session_id": session_id,
                    "lane": lane,
                    "alias": resolved.alias,
                    "method": chosen,
                },
            }
            retry_no = 0
            while True:
                if remaining_s() <= 0:
                    raise ModelInvokeError(task, attempts, "budget exhausted")
                timeout_s = min(resolved.spec.timeout_s, remaining_s())
                start = self._clock()
                outcome, error, result = await self._call(
                    runnable, msgs, config, timeout_s, chosen, schema
                )
                ms = int((self._clock() - start) * 1000)
                attempts.append(
                    Attempt(
                        resolved.alias,
                        resolved.model_used,
                        resolved.lane,
                        chosen,
                        outcome,
                        ms,
                        error,
                    )
                )
                if outcome == "ok":
                    parsed, raw_msg = result
                    return ModelResult(
                        parsed=parsed,
                        model_used=resolved.model_used,
                        alias=resolved.alias,
                        lane=resolved.lane,
                        method=chosen,
                        latency_ms=ms,
                        usage=_usage(raw_msg),
                        attempts=attempts,
                    )
                if outcome not in RETRYABLE or retry_no >= self.same_model_max:
                    break  # 拒答 / 其他错误 / 同模型重试用尽 → 下一家
                if outcome == "schema_error":
                    msgs = [
                        *msgs,
                        HumanMessage(
                            content=f"上一次输出未通过校验：{error}。请修正后只输出符合 schema 的 JSON 对象。"
                        ),
                    ]
                else:
                    wait = backoff_seconds(outcome, retry_no, self._rng)
                    # 退避后至少还要留 1 s 给再一次调用，否则不再尝试任何模型
                    if wait + 1.0 > remaining_s():
                        raise ModelInvokeError(task, attempts, "budget exhausted")
                    await self._sleep(wait)
                retry_no += 1
        raise ModelInvokeError(task, attempts)

    # ---- 单次调用 ----
    async def _call(
        self,
        runnable: Any,
        msgs: list[BaseMessage],
        config: dict,
        timeout_s: float,
        method: Method,
        schema: type[T],
    ) -> tuple[Outcome, str | None, tuple[T, BaseMessage | None] | None]:
        try:
            raw = await asyncio.wait_for(runnable.ainvoke(msgs, config=config), timeout_s)
            parsed, raw_msg = self._parse(method, schema, raw)
        except SchemaError as exc:
            return "schema_error", str(exc), None
        except RefusalError as exc:
            return "refusal", str(exc), None
        except Exception as exc:  # noqa: BLE001 - 全部归类，由调用方决定重试
            return classify_exception(exc), _short(exc), None
        return "ok", None, (parsed, raw_msg)

    def _skip_reason(self, resolved: ResolvedModel, need_vision: bool) -> str | None:
        if need_vision and not resolved.spec.vision:
            return "no vision capability"
        return self.registry.unavailable_reason(resolved.alias)

    # ---- 三种策略 ----
    @staticmethod
    def _prepare(
        model: BaseChatModel, method: Method, schema: type[BaseModel], messages: list[BaseMessage]
    ) -> tuple[Any, list[BaseMessage]]:
        if method == "json_schema":
            return model.with_structured_output(
                schema, method="json_schema", include_raw=True
            ), messages
        if method == "json_object":
            hint = SystemMessage(content=_schema_hint(schema))
            # JSON 模式要求提示词里出现 "json"，schema 提示放在最前
            return model.bind(response_format={"type": "json_object"}), [hint, *messages]
        return model.bind_tools([schema], tool_choice=schema.__name__), messages

    @staticmethod
    def _parse(method: Method, schema: type[T], raw: Any) -> tuple[T, BaseMessage | None]:
        raw_msg: BaseMessage | None = raw.get("raw") if isinstance(raw, dict) else raw
        refused = detect_refusal(raw_msg)
        if refused:
            raise RefusalError(refused)
        try:
            if method == "json_schema":
                if raw.get("parsing_error") is not None:
                    err = raw["parsing_error"]
                    text = _validation_text(err) if isinstance(err, ValidationError) else str(err)
                    raise SchemaError(text)
                parsed = raw["parsed"]
                if not isinstance(parsed, schema):
                    parsed = schema.model_validate(parsed)
                return parsed, raw_msg
            msg: AIMessage = raw
            if method == "tools":
                if not msg.tool_calls:
                    raise SchemaError("model returned no tool call")
                return schema.model_validate(msg.tool_calls[0]["args"]), msg
            content = msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
            return schema.model_validate(_extract_json(content)), msg
        except ValidationError as exc:
            raise SchemaError(_validation_text(exc)) from exc
