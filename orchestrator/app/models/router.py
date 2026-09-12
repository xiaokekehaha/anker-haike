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

限流与容量（票 12，07 §13）
- 429 同模型最多 `retry.rate_limit_max` 次，退避 1 / 2 / 4 s + [0, 0.5) s 抖动，仍受预算约束。
- 全局有界门 `concurrency.max_in_flight`（默认 50）：满时 invoke 立即抛 CapacityExceeded，不排队。
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.messages.utils import convert_to_messages
from pydantic import BaseModel, ValidationError

from app.models.config import Structured, TaskRoute
from app.models.queue import BoundedGate
from app.models.registry import ModelRegistry, ResolvedModel
from app.observability.runtime import record

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


@dataclass
class StreamEvent:
    """stream() 产出（model-selection §3.5）：start / delta / aborted / switched / end。

    API 层映射：start → message_start(message_id, replaces?)；delta → message；
    aborted → message_end(status=aborted)；end → message_end(status=completed, model_tier)。
    switched 紧随 aborted 之后、下一 start 之前，携带新 tier，供日志与 attempts。
    """

    kind: Literal["start", "delta", "aborted", "switched", "end"]
    message_id: str
    text: str = ""
    model_tier: Literal["primary", "fallback"] = "primary"
    alias: str | None = None
    model_used: str | None = None
    replaces: str | None = None
    reason: str | None = None


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
    if "ConnectionError" in name or "RemoteProtocolError" in name:
        # openai.APIConnectionError 及 langchain-openai 1.6 的 OpenAIConnectionError 包装（票 42 实测）
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


def uuid_for_replacement(message_id: str, n: int) -> str:
    """替换消息的 message_id：由原 id 与序号派生，重跑稳定。"""
    import uuid

    return uuid.uuid5(uuid.NAMESPACE_URL, f"{message_id}:replace:{n}").hex


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
        gate: BoundedGate | None = None,
    ):
        self.registry = registry
        self.gate = gate or BoundedGate(registry.cfg.concurrency.max_in_flight)
        self._factory = model_factory or (
            lambda r, route: registry.build(
                r.alias, effort=route.effort, max_tokens=route.max_tokens
            )
        )
        self._clock = clock
        self._sleep = sleep
        self._rng = rng
        self.same_model_max = registry.cfg.retry.same_model_max
        self.rate_limit_max = registry.cfg.retry.rate_limit_max
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
        """结构化调用；全局门满时立即抛 CapacityExceeded（映射为 recoverable error）。"""
        started = time.monotonic()
        result = None
        error = None
        try:
            async with self.gate.slot(task):
                result = await self._invoke(
                    task,
                    messages,
                    schema,
                    budget_ms=budget_ms,
                    session_id=session_id,
                    lane=lane,
                    method=method,
                )
                return result
        except BaseException as exc:
            error = exc
            raise
        finally:
            attempts = result.attempts if result else getattr(error, "attempts", [])
            last_model = next(
                (a.model_used for a in reversed(attempts) if a.outcome != "skipped"), None
            )
            record(
                "model_call",
                task=task,
                session_id=session_id,
                lane=lane or self.registry.cfg.default_lane,
                stream=False,
                input=messages,
                output=result.parsed if result else None,
                model_used=result.model_used if result else last_model,
                usage=result.usage if result else {},
                attempts=attempts,
                latency_ms=int((time.monotonic() - started) * 1000),
                status="ok"
                if result
                else ("cancelled" if isinstance(error, asyncio.CancelledError) else "error"),
            )

    async def _invoke(
        self,
        task: str,
        messages: Sequence[BaseMessage | tuple[str, str] | dict[str, Any]],
        schema: type[T],
        *,
        budget_ms: int,
        session_id: str | None,
        lane: str | None,
        method: Method | None,
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
                max_retries = (
                    self.rate_limit_max if outcome == "rate_limited" else self.same_model_max
                )
                if outcome not in RETRYABLE or retry_no >= max_retries:
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

    # ---- 用户可见文本流（票 13 / 14）----
    async def stream(
        self,
        task,
        messages,
        *,
        budget_ms,
        message_id,
        session_id=None,
        lane=None,
        fallback_messages=None,
    ) -> AsyncIterator[StreamEvent]:
        started = time.monotonic()
        trace = {"attempts": [], "usage": {}}
        output = ""
        model_used = None
        status = "cancelled"
        truncated = False
        source = self._stream(
            task,
            messages,
            budget_ms=budget_ms,
            message_id=message_id,
            session_id=session_id,
            lane=lane,
            fallback_messages=fallback_messages,
            trace=trace,
        )
        try:
            async for event in source:
                if event.kind == "start":
                    model_used = event.model_used
                    output = ""
                elif event.kind == "delta":
                    truncated |= len(output) + len(event.text) > 16000
                    output = (output + event.text)[:16000]
                elif event.kind == "end":
                    status = "ok"
                yield event
        except BaseException as exc:
            status = (
                "cancelled" if isinstance(exc, (asyncio.CancelledError, GeneratorExit)) else "error"
            )
            raise
        finally:
            await source.aclose()
            record(
                "model_call",
                task=task,
                session_id=session_id,
                lane=lane or self.registry.cfg.default_lane,
                stream=True,
                input=trace.get("input", messages),
                output=output,
                model_used=model_used or trace.get("model_used"),
                usage=trace["usage"],
                attempts=trace["attempts"],
                output_truncated=truncated,
                latency_ms=int((time.monotonic() - started) * 1000),
                status=status,
            )

    async def _stream(
        self,
        task: str,
        messages: Sequence[BaseMessage | tuple[str, str] | dict[str, Any]],
        *,
        budget_ms: int,
        message_id: str,
        session_id: str | None = None,
        lane: str | None = None,
        fallback_messages: Sequence[BaseMessage | tuple[str, str] | dict[str, Any]] | None = None,
        trace: dict[str, Any],
    ) -> AsyncIterator[StreamEvent]:
        """tag=user_visible 的文本流。主模型中途失败 → aborted，降级模型用 fallback_messages（简化模式变体）
        从头生成并以新 message_id + replaces 开始；链上第一家为 primary，其余为 fallback。
        未产出任何 delta 时的失败按 invoke 同款规则同模型退避重试一次；链耗尽抛 ModelInvokeError。
        """
        route = self.registry.cfg.route(task, lane)
        lane = lane or self.registry.cfg.default_lane
        base = convert_to_messages(list(messages))
        fb = convert_to_messages(list(fallback_messages)) if fallback_messages is not None else base
        attempts: list[Attempt] = trace["attempts"]
        deadline = self._clock() + budget_ms / 1000
        current_id = message_id
        async with self.gate.slot(task):
            chain = self.registry.chain(task, lane)[: self.chain_max]
            tried = 0  # 路由前跳过（未配置 / 无能力）的模型不算主模型；第一家真正发请求的为 primary（07 §6）
            for idx, resolved in enumerate(chain):
                skip = self._skip_reason(resolved, route.needs_vision)
                if skip:
                    attempts.append(
                        Attempt(
                            resolved.alias,
                            resolved.model_used,
                            resolved.lane,
                            None,
                            "skipped",
                            0,
                            skip,
                        )
                    )
                    continue
                tier: Literal["primary", "fallback"] = "primary" if tried == 0 else "fallback"
                tried += 1
                msgs = base if tier == "primary" else fb
                trace["input"] = msgs
                trace["model_used"] = resolved.model_used
                model = self._factory(resolved, route)
                config = {
                    "tags": ["user_visible"],
                    "metadata": {
                        "task": task,
                        "session_id": session_id,
                        "lane": lane,
                        "alias": resolved.alias,
                        "tier": tier,
                    },
                }
                retry_no = 0
                while True:
                    remaining = deadline - self._clock()
                    if remaining <= 0:
                        raise ModelInvokeError(task, attempts, "budget exhausted")
                    start = self._clock()
                    emitted = False
                    outcome: Outcome = "ok"
                    error: str | None = None
                    try:
                        agen = model.astream(msgs, config=config)
                        while True:
                            chunk = await asyncio.wait_for(
                                agen.__anext__(),
                                min(resolved.spec.timeout_s, deadline - self._clock()),
                            )
                            usage = getattr(chunk, "usage_metadata", None) or {}
                            for key in ("input_tokens", "output_tokens", "total_tokens"):
                                if key in usage:
                                    trace["usage"][key] = trace["usage"].get(key, 0) + int(
                                        usage[key]
                                    )
                            delta = (
                                chunk.content
                                if isinstance(chunk.content, str)
                                else "".join(
                                    p.get("text", "") for p in chunk.content if isinstance(p, dict)
                                )
                            )
                            if not delta:
                                continue
                            if not emitted:
                                emitted = True
                                yield StreamEvent(
                                    "start",
                                    current_id,
                                    model_tier=tier,
                                    alias=resolved.alias,
                                    model_used=resolved.model_used,
                                    replaces=None if current_id == message_id else message_id,
                                )
                            yield StreamEvent(
                                "delta",
                                current_id,
                                text=delta,
                                model_tier=tier,
                                alias=resolved.alias,
                            )
                    except StopAsyncIteration:
                        pass
                    except Exception as exc:  # noqa: BLE001
                        outcome = classify_exception(exc)
                        error = _short(exc)
                    ms = int((self._clock() - start) * 1000)
                    if outcome == "ok":
                        if not emitted:  # 模型返回空串：视为一次错误
                            outcome, error = "error", "empty stream"
                        else:
                            attempts.append(
                                Attempt(
                                    resolved.alias,
                                    resolved.model_used,
                                    resolved.lane,
                                    None,
                                    "ok",
                                    ms,
                                )
                            )
                            yield StreamEvent(
                                "end",
                                current_id,
                                model_tier=tier,
                                alias=resolved.alias,
                                model_used=resolved.model_used,
                            )
                            return
                    attempts.append(
                        Attempt(
                            resolved.alias,
                            resolved.model_used,
                            resolved.lane,
                            None,
                            outcome,
                            ms,
                            error,
                        )
                    )
                    if emitted:
                        # 已有可见文本：中断，换下一家从头生成并替换（07 §6）
                        yield StreamEvent(
                            "aborted",
                            current_id,
                            model_tier=tier,
                            alias=resolved.alias,
                            reason=error,
                        )
                        current_id = uuid_for_replacement(message_id, len(attempts))
                        if idx + 1 < len(chain):
                            yield StreamEvent(
                                "switched",
                                current_id,
                                model_tier="fallback",
                                replaces=message_id,
                                reason=error,
                            )
                        break
                    max_retries = (
                        self.rate_limit_max if outcome == "rate_limited" else self.same_model_max
                    )
                    if (
                        outcome not in RETRYABLE
                        or outcome == "schema_error"
                        or retry_no >= max_retries
                    ):
                        break
                    wait = backoff_seconds(outcome, retry_no, self._rng)
                    if wait + 1.0 > deadline - self._clock():
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
