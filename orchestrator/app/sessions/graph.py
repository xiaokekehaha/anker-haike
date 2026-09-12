"""票 05 的占位图：intake → reply 两个节点，只发 progress，不调模型。

票 15：intake 节点末尾运行 CP-in（规则服务，任何模型调用之前）；R3 / R4 命中写 safety_flags 并
经条件边直接进入 escalate 节点，不再经过 reply 及后续任何会调用模型的节点。
票 20：intake 后进入 disambiguate（产品目录匹配）；多命中走三段式
prepare_card → await_input(interrupt) → apply_action（08 §3）。awaiting_input 事件由运行器在
真正中断时发出（version 取自 checkpoint），卡片事件由 await_input 发出、重跑重发、按 card_id 幂等。
后续票在此图上替换 / 扩展节点（17 intake 抽取、18 安抚流、21/24/25 消歧分支……）。
节点通过 get_stream_writer() 发自定义事件，运行器映射为契约事件。
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from app.escalation.summary import build_summary, reassurance_text, summary_card_id
from app.rules import get_rules_service
from app.sessions.cards import candidates_key, current_version, derive_card_id, get_catalog


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
    # 票 20：三段式等待。pending_card 在 prepare_card 写入、apply_action 清空；
    # last_action 为 interrupt 恢复时收到的动作（08 §4 结构）
    pending_card: dict[str, Any] | None
    last_action: dict[str, Any] | None
    prepare_card_calls: int  # 验收：prepare_card 只执行一次
    product_candidates: list[dict[str, Any]]
    product_confirmed: dict[str, Any] | None
    product_state: str  # confirmed_sku / category_only / unknown（09 §2.1）
    out_of_scope: bool
    escalation_summary: dict[str, Any] | None  # 票 16：{card_id, reason, summary}


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
    return "escalate" if state.get("escalate_reason") else "disambiguate"


# ---------------- 票 20：消歧 + 三段式等待 ----------------


async def disambiguate(state: SessionState) -> SessionState:
    """产品目录匹配（规则查表，不用 LLM）：多命中 → 出卡；单命中 → 直接确认；零命中 → unknown（追问在票 24）。"""
    writer = get_stream_writer()
    writer({"type": "progress", "stage": "disambiguate"})
    if state.get("product_confirmed"):
        return {"stage": "disambiguate"}
    cands = [c.model_dump() for c in get_catalog().lookup_product(state.get("text", ""))]
    update: SessionState = {"stage": "disambiguate", "product_candidates": cands}
    if len(cands) == 1:
        update["product_confirmed"] = cands[0]
        update["product_state"] = "confirmed_sku"
        update["out_of_scope"] = not cands[0]["in_scope"]
    elif not cands:
        update["product_state"] = "unknown"
    return update


def route_after_disambiguate(state: SessionState) -> str:
    if state.get("out_of_scope"):
        return "escalate"
    if len(state.get("product_candidates") or []) > 1 and not state.get("product_confirmed"):
        return "prepare_card"
    return "reply"


async def prepare_card(state: SessionState) -> SessionState:
    """生成并持久化 pending_card；不含 interrupt，只执行一次。"""
    cands = state["product_candidates"]
    card_id = derive_card_id(
        state["session_id"], "disambiguate", candidates_key([c["sku"] for c in cands])
    )
    return {
        "pending_card": {
            "card_id": card_id,
            "kind": "select_product",
            "payload": {"candidates": cands},
        },
        "prepare_card_calls": state.get("prepare_card_calls", 0) + 1,
    }


async def await_input(state: SessionState) -> SessionState:
    """只读 pending_card：发卡片事件后 interrupt。恢复时本节点重跑，卡片事件重发（前端按 card_id 幂等）。"""
    pc = state["pending_card"]
    writer = get_stream_writer()
    if pc["kind"] == "select_product":
        writer(
            {
                "type": "product_card",
                "card_id": pc["card_id"],
                "version": current_version(),
                "candidates": pc["payload"]["candidates"],
            }
        )
    # interrupt 载荷即 awaiting_input 事件的业务字段。version 用节点内 langgraph_step：它等于本次中断
    # 后 checkpoint 推导出的 version（与 done.version 一致）；不能在运行器里查 checkpoint——
    # AsyncPostgresSaver 的写入相对 updates 流是异步的，查早了会拿到旧值（票 20 实测）
    action = interrupt(
        {
            "kind": pc["kind"],
            "interrupt_id": pc["card_id"],
            "card_id": pc["card_id"],
            "version": current_version(),
        }
    )
    return {"last_action": action}


async def apply_action(state: SessionState) -> SessionState:
    """校验并应用动作（本票只处理 select_product）；副作用以 action_id 幂等（票 22）。"""
    action = state.get("last_action") or {}
    pc = state.get("pending_card") or {}
    results = dict(state.get("card_results") or {})
    update: SessionState = {"pending_card": None, "last_action": None}
    if action.get("kind") == "select_product":
        sku = action["payload"]["sku"]
        chosen = next(c for c in pc["payload"]["candidates"] if c["sku"] == sku)
        results[pc["card_id"]] = {"selected_sku": sku}
        update.update(
            {
                "card_results": results,
                "product_confirmed": chosen,
                "product_state": "confirmed_sku",
                "product_candidates": [],
                "out_of_scope": not chosen["in_scope"],
            }
        )
    return update


def route_after_apply(state: SessionState) -> str:
    return "escalate" if state.get("out_of_scope") else "reply"


async def escalate(state: SessionState) -> SessionState:
    """安全 / 人工升级：安抚句（固定文案，不调模型）→ 结构化摘要 escalation_summary（票 16）。

    摘要由图状态直接渲染，模型不可用也能生成；字段润色在后续票接入 ModelRouter。
    """
    writer = get_stream_writer()
    writer({"type": "progress", "stage": "escalate", "substage": "summarize"})
    reason = state.get("escalate_reason") or "R3"
    session_id = state.get("session_id", "")
    run_id = state.get("run_id", "")
    message_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{session_id}:{run_id}:reassure").hex
    text = reassurance_text(reason)
    writer({"type": "message_start", "message_id": message_id})
    writer({"type": "message", "message_id": message_id, "delta": text})
    writer({"type": "message_end", "message_id": message_id, "status": "completed"})
    summary = build_summary(
        dict(state), reason=reason, lane=os.environ.get("MODEL_LANE", "domestic")
    )
    card_id = summary_card_id(session_id, reason)
    writer(
        {
            "type": "escalation_summary",
            "card_id": card_id,
            "summary": summary.model_dump(mode="json"),
        }
    )
    return {
        "stage": "escalate",
        "substage": "summarize",
        "escalation_summary": {
            "card_id": card_id,
            "reason": reason,
            "summary": summary.model_dump(mode="json"),
        },
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
    g.add_node("escalate", escalate)
    g.add_node("disambiguate", disambiguate)
    g.add_node("prepare_card", prepare_card)
    g.add_node("await_input", await_input)
    g.add_node("apply_action", apply_action)
    g.add_edge(START, "intake")
    g.add_conditional_edges(
        "intake", route_after_intake, {"disambiguate": "disambiguate", "escalate": "escalate"}
    )
    g.add_conditional_edges(
        "disambiguate",
        route_after_disambiguate,
        {"prepare_card": "prepare_card", "reply": "reply", "escalate": "escalate"},
    )
    g.add_edge("prepare_card", "await_input")
    g.add_edge("await_input", "apply_action")
    g.add_conditional_edges(
        "apply_action", route_after_apply, {"reply": "reply", "escalate": "escalate"}
    )
    g.add_edge("reply", END)
    g.add_edge("escalate", END)
    return g.compile(checkpointer=checkpointer)
