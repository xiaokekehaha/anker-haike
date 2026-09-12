"""可脚本化的假聊天模型：单测与故障注入用（票 10 / 11），不发网络请求。

script 里每一项对应一次调用：
- str            → 纯文本回复（json_object 策略解析它）
- dict           → 一次工具调用的参数（tools 策略）/ native 策略的结构化结果
- AIMessage      → 原样返回（可带 response_metadata 模拟拒答）
- Exception 实例 → 该次调用抛出（超时、429、5xx……）
- list           → 流式：元素为 str token 依次产出，元素为 Exception 则在该处中断（票 14 断流注入）
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel, Field, PrivateAttr, ValidationError


class ScriptExhausted(RuntimeError):
    pass


class FakeChatModel(BaseChatModel):
    script: list[Any] = Field(default_factory=list)
    calls: list[dict[str, Any]] = Field(default_factory=list)
    name_for_trace: str = "fake"

    @property
    def _llm_type(self) -> str:
        return "fake-scripted"

    # ---- 记录与出脚本 ----
    def _next(self, messages: list[BaseMessage], run_manager, kwargs: dict[str, Any]) -> ChatResult:
        self.calls.append(
            {
                "messages": list(messages),
                "kwargs": dict(kwargs),
                "tags": list(getattr(run_manager, "inheritable_tags", []) or [])
                + list(getattr(run_manager, "tags", []) or []),
                "metadata": {
                    **(getattr(run_manager, "inheritable_metadata", {}) or {}),
                    **(getattr(run_manager, "metadata", {}) or {}),
                },
            }
        )
        if not self.script:
            raise ScriptExhausted(f"{self.name_for_trace}: no scripted response left")
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, list):  # 非流式调用拿到流脚本：拼成整段
            msg = AIMessage(content="".join(x for x in item if isinstance(x, str)))
            return ChatResult(generations=[ChatGeneration(message=msg)])
        if isinstance(item, AIMessage):
            return ChatResult(generations=[ChatGeneration(message=item)])
        if isinstance(item, dict):
            tool_name = (
                kwargs.get("tool_choice") if isinstance(kwargs.get("tool_choice"), str) else None
            ) or "tool"
            msg = AIMessage(
                content="",
                tool_calls=[{"name": tool_name, "args": item, "id": f"call-{len(self.calls)}"}],
            )
        else:
            msg = AIMessage(content=str(item))
        msg.usage_metadata = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._next(messages, run_manager, kwargs)

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._next(messages, run_manager, kwargs)

    _stream_config: dict | None = PrivateAttr(default=None)

    async def astream(self, input, config=None, **kwargs):  # type: ignore[override]
        # BaseChatModel.astream 不把 run_manager 传给 _astream，这里从 config 记录 tags / metadata
        self._stream_config = dict(config or {})
        async for chunk in super().astream(input, config=config, **kwargs):
            yield chunk

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        cfg = self._stream_config or {}
        self.calls.append(
            {
                "messages": list(messages),
                "kwargs": dict(kwargs),
                "stream": True,
                "tags": list(cfg.get("tags") or []),
                "metadata": dict(cfg.get("metadata") or {}),
            }
        )
        if not self.script:
            raise ScriptExhausted(f"{self.name_for_trace}: no scripted response left")
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        tokens = item if isinstance(item, list) else [str(item)]
        for tok in tokens:
            if isinstance(tok, BaseException):
                raise tok
            yield ChatGenerationChunk(message=AIMessageChunk(content=tok))

    # ---- 三种策略的入口 ----
    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # type: ignore[override]
        return self.bind(tools=list(tools), tool_choice=tool_choice, **kwargs)

    def with_structured_output(self, schema, *, include_raw: bool = False, **kwargs):  # type: ignore[override]
        """模拟原生 json_schema：把脚本项（dict 或 JSON 文本）按 schema 解析。"""
        bound = self.bind(structured_method=kwargs.get("method", "json_schema"))

        def _parse(raw: AIMessage) -> dict[str, Any]:
            parsed, err = None, None
            try:
                data = (
                    raw.tool_calls[0]["args"] if raw.tool_calls else json.loads(raw.content or "")
                )
                parsed = (
                    schema.model_validate(data)
                    if isinstance(schema, type) and issubclass(schema, BaseModel)
                    else data
                )
            except (ValidationError, ValueError) as exc:
                err = exc
            if not include_raw:
                if err:
                    raise err
                return parsed
            return {"raw": raw, "parsed": parsed, "parsing_error": err}

        return bound | RunnableLambda(_parse)
