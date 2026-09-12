"""票 05 的占位图：intake → reply 两个节点，只发 progress，不调模型。

票 15：intake 节点末尾运行 CP-in（规则服务，任何模型调用之前）；R3 / R4 命中写 safety_flags 并
经条件边直接进入 escalate 节点，不再经过 reply 及后续任何会调用模型的节点。
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

from app.rules import get_rules_service


class SessionState(TypedDict, total=False):
    session_id: str
    run_id: str  # 当前 run，由运行器随输入写入，用户消息据此归入 timeline 对应位置
    at: str  # 本 run 收到消息的时间（ISO），用于 timeline user_message.at
    text: str
    stage: str
    substage: str | None
    image_ids: list[str]
    messages: list[dict[str, Any]]  # {role, text, image_ids, run_id, at}
    # card_id -> 用户对卡片的结果（selected_sku / feedback+note / confirmed_fields+skipped_reason），
    # 由后续票的 apply_action 节点写入；快照折叠 timeline 时读取（票 07）
    card_results: dict[str, dict[str, Any]]
    # 票 15：CP-in 命中记录 {rule_id, source, term, ts}，跨 run 累积；escalate_reason 为触发升级的规则编号
    safety_flags: list[dict[str, Any]]
    escalate_reason: str | None


def _delay() -> float:
    # 演示 / 手测用：让占位节点停留一会以观察 ping；默认 0
    return float(os.environ.get("PLACEHOLDER_NODE_DELAY_S", "0") or 0)


async def intake(state: SessionState) -> SessionState:
    writer = get_stream_writer()
    writer({"type": "progress", "stage": "intake"})
    if state.get("text") == "__raise__":  # 测试钩子：异常路径
        raise RuntimeError("placeholder node failure")
    await asyncio.sleep(_delay())
    user_msg = {
        "role": "user",
        "text": state.get("text", ""),
        "image_ids": list(state.get("image_ids") or []),
        "run_id": state.get("run_id", ""),
        "at": state.get("at", ""),
    }
    # CP-in：任何模型调用之前（票 15，09 §1）
    cp = get_rules_service().check_in(text=state.get("text"), session_id=state.get("session_id"))
    update: SessionState = {
        "stage": "intake",
        "messages": [*state.get("messages", []), user_msg],
        "safety_flags": [*state.get("safety_flags", []), *cp.flags],
    }
    if cp.escalate:
        update["escalate_reason"] = next(h.rule_id for h in cp.hits if h.action == "escalate")
    return update


def route_after_intake(state: SessionState) -> str:
    return "escalate" if state.get("escalate_reason") else "reply"


async def escalate(state: SessionState) -> SessionState:
    """安全 / 人工升级占位：只推进阶段；摘要卡在票 16。"""
    writer = get_stream_writer()
    writer({"type": "progress", "stage": "escalate", "substage": "summarize"})
    return {"stage": "escalate", "substage": "summarize"}


async def reply(state: SessionState) -> SessionState:
    writer = get_stream_writer()
    writer({"type": "progress", "stage": "diagnose"})
    await asyncio.sleep(_delay())
    return {"stage": "diagnose"}


def build_graph(checkpointer: BaseCheckpointSaver | None) -> CompiledStateGraph:
    g = StateGraph(SessionState)
    g.add_node("intake", intake)
    g.add_node("reply", reply)
    g.add_node("escalate", escalate)
    g.add_edge(START, "intake")
    g.add_conditional_edges(
        "intake", route_after_intake, {"reply": "reply", "escalate": "escalate"}
    )
    g.add_edge("reply", END)
    g.add_edge("escalate", END)
    return g.compile(checkpointer=checkpointer)
