"""票 05 的占位图：intake → reply 两个节点，只发 progress，不调模型。

后续票在此图上替换 / 扩展节点（17 intake 抽取、18 安抚流、20 三段式等待……）。
节点通过 get_stream_writer() 发自定义事件，运行器映射为契约事件。
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph


class SessionState(TypedDict, total=False):
    session_id: str
    text: str
    stage: str
    image_ids: list[str]
    messages: list[dict[str, Any]]


def _delay() -> float:
    # 演示 / 手测用：让占位节点停留一会以观察 ping；默认 0
    return float(os.environ.get("PLACEHOLDER_NODE_DELAY_S", "0") or 0)


async def intake(state: SessionState) -> SessionState:
    writer = get_stream_writer()
    writer({"type": "progress", "stage": "intake"})
    if state.get("text") == "__raise__":  # 测试钩子：异常路径
        raise RuntimeError("placeholder node failure")
    await asyncio.sleep(_delay())
    return {
        "stage": "intake",
        "messages": [*state.get("messages", []), {"role": "user", "text": state.get("text", "")}],
    }


async def reply(state: SessionState) -> SessionState:
    writer = get_stream_writer()
    writer({"type": "progress", "stage": "diagnose"})
    await asyncio.sleep(_delay())
    return {"stage": "diagnose"}


def build_graph(checkpointer: BaseCheckpointSaver | None) -> CompiledStateGraph:
    g = StateGraph(SessionState)
    g.add_node("intake", intake)
    g.add_node("reply", reply)
    g.add_edge(START, "intake")
    g.add_edge("intake", "reply")
    g.add_edge("reply", END)
    return g.compile(checkpointer=checkpointer)
