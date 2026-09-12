"""票 05 的占位图：intake → reply 两个节点，只发 progress，不调模型。

票 15：intake 节点末尾运行 CP-in（规则服务，任何模型调用之前）；R3 / R4 命中写 safety_flags 并
经条件边直接进入 escalate 节点，不再经过 reply 及后续任何会调用模型的节点。
票 20：intake 后进入 disambiguate（产品目录匹配）；多命中走三段式
prepare_card → await_input(interrupt) → apply_action（08 §3）。awaiting_input 事件由运行器在
真正中断时发出（version 取自 checkpoint），卡片事件由 await_input 发出、重跑重发、按 card_id 幂等。
票 24：disambiguate 按「继续 / 澄清 / 升级」三种结果判定（app/sessions/clarify.py）：product_state 三分、
澄清追问节点 clarify（run 以 done(completed) 结束，不发步骤、不检索）、两次澄清后仍不明 → escalate(R7)；
用户对产品卡片不选而发自由文本 → intake 清掉失效 pending_card 并计一次澄清。
后续票在此图上替换 / 扩展节点（25 范围外 R8、37 rediagnose……）。
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
from app.intake import extract_intake
from app.knowledge.adapter import KnowledgeScope
from app.knowledge.runtime import ensure_index, get_knowledge_adapter
from app.models.runtime import get_model_router
from app.prompts import reassurance_messages, reply_messages
from app.rules import get_rules_service
from app.sessions import clarify as clarify_mod
from app.sessions.cards import candidates_key, current_version, derive_card_id
from app.sessions.streaming import stream_to_writer


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
    category: str | None  # category_only 时的已确认品类；confirmed_sku 时与产品一致
    out_of_scope: bool
    # 票 24：澄清计数 {reason: product|symptom|conflict, attempts, asked_run_id}，checkpoint 内部状态，
    # 跨 run 保留；信息补齐后置 None。abandoned_card 为本 run 开始时被自由文本作废的产品卡片（intake 写、disambiguate 读）
    clarification: dict[str, Any] | None
    abandoned_card: dict[str, Any] | None
    observations: list[str]  # 摘要用观察记录（R7 澄清经过等）
    _decision: dict[str, Any] | None  # disambiguate → 路由 / clarify 的本 run 判定结果（瞬态）
    escalation_summary: dict[str, Any] | None  # 票 16：{card_id, reason, summary}
    # 票 17：intake 抽取结果；emotion.strategy 注入系统提示第二层；model_trace 累积各 task 命中模型
    emotion: dict[str, str]
    product_hints: list[str]
    symptoms: list[str]
    model_trace: list[dict[str, Any]]
    # 票 28：检索结果。evidence 按 evidence_id 去重累积，供 step.evidence_ids 引用；knowledge_status 为最近一次四态
    evidence: dict[str, dict[str, Any]]
    knowledge_status: str | None
    # 票 13 / 18：本 run 已发出的可见消息 {message_id, kind: reassurance|reply, text, model_tier}
    visible_messages: list[dict[str, Any]]
    first_visible_ms: int | None


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
    # 票 24：新消息到达时若仍有待选产品卡片，说明用户未选中而改为自由文本；LangGraph 已丢弃该 interrupt，
    # 这里把失效 pending_card 从权威状态清除，交 disambiguate 计一次澄清（09 §1.1）
    stale = state.get("pending_card")
    update["pending_card"] = None
    update["abandoned_card"] = stale if stale and stale.get("kind") == "select_product" else None
    if cp.escalate:
        update["escalate_reason"] = next(h.rule_id for h in cp.hits if h.action == "escalate")
        return update  # R3 / R4 命中：不再发起任何模型调用
    # 票 17：一次 internal 调用抽取情绪 + 产品线索 + 症状 + wants_human；失败降级为 calm / 空
    outcome = await extract_intake(
        get_model_router(),
        state.get("text", ""),
        session_id=state.get("session_id"),
        lane=os.environ.get("MODEL_LANE", "domestic"),
        has_image=bool(state.get("image_ids")),
        prev_emotion=state.get("emotion"),
        state_summary={
            "stage": state.get("stage"),
            "product": (state.get("product_confirmed") or {}).get("name"),
            "product_state": state.get("product_state"),
        },
    )
    update.update(
        {
            "emotion": outcome.emotion,
            "product_hints": outcome.product_hints,
            "symptoms": outcome.symptoms,
            "model_trace": [
                *state.get("model_trace", []),
                *([outcome.model_trace] if outcome.model_trace else []),
            ],
        }
    )
    if outcome.wants_human:  # 等价于 R3 命中（03 §1.2）
        update["safety_flags"] = [
            *update["safety_flags"],
            {"rule_id": "R3", "source": "intake", "term": "wants_human", "ts": state.get("at", "")},
        ]
        update["escalate_reason"] = "R3"
    return update


def route_after_intake(state: SessionState) -> str:
    if state.get("escalate_reason"):
        return "escalate"
    # 票 18：焦急 / 愤怒 → 安抚句先于任何卡片与 diagnose 到达；平稳路径不加节点（保持票 05 的 version 断言）
    if (state.get("emotion") or {}).get(
        "strategy", "normal"
    ) != "normal" and get_model_router() is not None:
        return "reassure"
    return "disambiguate"


def _state_summary(state: SessionState) -> dict[str, Any]:
    return {
        "stage": state.get("stage"),
        "product": (state.get("product_confirmed") or {}).get("name"),
        "product_state": state.get("product_state"),
        "symptoms": state.get("symptoms"),
        "knowledge_status": state.get("knowledge_status"),
    }


def _lane() -> str:
    return os.environ.get("MODEL_LANE", "domestic")


async def reassure(state: SessionState) -> SessionState:
    """安抚句流式先出（票 18，05 §6）：reply.stream，tag=user_visible，一到两句，不给步骤。"""
    writer = get_stream_writer()
    router = get_model_router()
    strategy = (state.get("emotion") or {}).get("strategy", "reassure_first")
    primary, fallback = reassurance_messages(
        state.get("text", ""), strategy=strategy, summary=_state_summary(state)
    )
    message_id = uuid.uuid5(
        uuid.NAMESPACE_URL, f"{state.get('session_id')}:{state.get('run_id')}:reassure"
    ).hex
    out = await stream_to_writer(
        writer,
        router,
        "reply.stream",
        primary,
        message_id=message_id,
        budget_ms=8000,
        session_id=state.get("session_id"),
        lane=_lane(),
        fallback_messages=fallback,
    )
    msgs = list(state.get("visible_messages") or [])
    if out.completed:
        msgs.append(
            {
                "message_id": out.message_id,
                "kind": "reassurance",
                "text": out.text,
                "model_tier": out.model_tier,
            }
        )
    return {
        "visible_messages": msgs,
        "first_visible_ms": state.get("first_visible_ms") or out.first_visible_ms,
    }


# ---------------- 票 20：消歧 + 三段式等待 ----------------


async def disambiguate(state: SessionState) -> SessionState:
    """产品目录匹配（规则查表，不用 LLM）+ 三种处理结果（票 24，09 §1.1）：

    继续：多命中 → 出卡；单命中 / 卡片已选 → confirmed_sku；零命中但品类词明确且有通用计划 → category_only。
    澄清：品类未定 / 已确认产品与本轮品类冲突 / 没有任何故障描述 → clarify 节点问一个具体问题。
    升级：连续两次澄清并收到回答后仍不明 → escalate(R7)。
    """
    writer = get_stream_writer()
    writer({"type": "progress", "stage": "disambiguate"})
    decision = clarify_mod.decide(dict(state), abandoned_card=state.get("abandoned_card"))
    update: SessionState = {"stage": "disambiguate", "abandoned_card": None, **decision.update}
    update["_decision"] = {
        "outcome": decision.outcome,
        "reason": decision.reason,
        **decision.detail,
    }
    return update


def route_after_disambiguate(state: SessionState) -> str:
    decision = state.get("_decision") or {}
    if decision.get("outcome") == "escalate" or state.get("escalate_reason"):
        return "escalate"
    if decision.get("outcome") == "clarify":
        return "clarify"
    if state.get("out_of_scope"):
        return "escalate"
    if len(state.get("product_candidates") or []) > 1 and not state.get("product_confirmed"):
        return "prepare_card"
    return _after_product(state)


async def clarify(state: SessionState) -> SessionState:
    """澄清追问（票 24）：一句具体问题，文案由 disambiguate.clarify 任务生成、失败用固定文案；
    不发步骤、不检索。attempts 在此 +1（真正发问才计数）。run 随后以 done(completed) 结束。"""
    writer = get_stream_writer()
    decision = state.get("_decision") or {}
    reason = decision.get("reason") or "product"
    detail = {k: v for k, v in decision.items() if k not in ("outcome", "reason")}
    out = await clarify_mod.make_question(
        get_model_router(),
        reason,
        state.get("text", ""),
        strategy=(state.get("emotion") or {}).get("strategy", "normal"),
        summary=_state_summary(state),
        detail=detail,
        session_id=state.get("session_id"),
        lane=_lane(),
    )
    message_id = uuid.uuid5(
        uuid.NAMESPACE_URL, f"{state.get('session_id')}:{state.get('run_id')}:clarify"
    ).hex
    writer({"type": "message_start", "message_id": message_id})
    writer({"type": "message", "message_id": message_id, "delta": out.text})
    writer({"type": "message_end", "message_id": message_id, "status": "completed"})
    msgs = [
        *(state.get("visible_messages") or []),
        {"message_id": message_id, "kind": "clarify", "text": out.text, "model_tier": None},
    ]
    return {
        "clarification": clarify_mod.count_attempt(
            state.get("clarification"), reason, state.get("run_id", "")
        ),
        "visible_messages": msgs,
        "model_trace": [
            *state.get("model_trace", []),
            *([out.model_trace] if out.model_trace else []),
        ],
        "_decision": None,
    }


def _after_product(state: SessionState) -> str:
    """产品已确认或品类已知 → 先检索（票 28）；unknown 只允许追问（票 24），不检索。"""
    return (
        "retrieve" if state.get("product_state") in ("confirmed_sku", "category_only") else "reply"
    )


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
        # 票 24：产品卡片也是一次「请用户确认产品」的澄清；用户不选而改发文本时计入 R7 次数
        "clarification": clarify_mod.count_attempt(
            state.get("clarification"), "product", state.get("run_id", "")
        ),
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
                "category": chosen.get("category"),
                "out_of_scope": not chosen["in_scope"],
                "clarification": None,  # 票 24：产品已确认，澄清计数清零
            }
        )
    return update


def route_after_apply(state: SessionState) -> str:
    return "escalate" if state.get("out_of_scope") else _after_product(state)


# ---------------- 票 28：检索 → tool_call / evidence 事件 ----------------


def knowledge_scope_of(state: SessionState) -> KnowledgeScope:
    product = state.get("product_confirmed") or {}
    ps = state.get("product_state") or "unknown"
    category = product.get("category") or state.get("category") or "robot_vacuum"
    return KnowledgeScope(ps, category, product.get("sku") if ps == "confirmed_sku" else None)  # type: ignore[arg-type]


def retrieval_query(state: SessionState) -> str:
    symptoms = state.get("symptoms") or []
    return "；".join(symptoms) if symptoms else state.get("text", "")


async def retrieve(state: SessionState) -> SessionState:
    """文本 query 检索 kb_manual + kb_tickets：tool_call(started→finished/failed) + evidence（票 28）。

    unavailable → tool_call failed，流程继续（09 §4：按标准排障流程，不用常识补假设）。
    evidence_id 取自 WeKnora chunk id，同会话内稳定，累积进状态供 step.evidence_ids 引用。
    """
    writer = get_stream_writer()
    writer({"type": "progress", "stage": "diagnose", "substage": "retrieve"})
    session_id, run_id = state.get("session_id", ""), state.get("run_id", "")
    tool_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{session_id}:{run_id}:knowledge.search").hex
    query = retrieval_query(state)
    scope = knowledge_scope_of(state)
    writer(
        {
            "type": "tool_call",
            "tool_id": tool_id,
            "name": "knowledge.search",
            "status": "started",
            "summary": f"检索知识库：{query[:40]}",
        }
    )
    adapter = get_knowledge_adapter()
    evidence = dict(state.get("evidence") or {})
    if adapter is None:
        writer(
            {
                "type": "tool_call",
                "tool_id": tool_id,
                "name": "knowledge.search",
                "status": "failed",
                "summary": "知识库暂不可用，按标准排障流程",
            }
        )
        return {"stage": "diagnose", "substage": "retrieve", "knowledge_status": "unavailable"}
    await ensure_index(adapter)
    results = [
        await adapter.hybrid_search(kb, query, 5, scope) for kb in ("kb_manual", "kb_tickets")
    ]
    statuses = [r.status for r in results]
    hits = [h for r in results for h in r.hits]
    if all(s == "unavailable" for s in statuses):
        status = "unavailable"
    elif hits:
        status = "ok"
    else:
        status = "no_match"
    if status == "unavailable":
        writer(
            {
                "type": "tool_call",
                "tool_id": tool_id,
                "name": "knowledge.search",
                "status": "failed",
                "summary": "知识库暂不可用，按标准排障流程",
            }
        )
    else:
        items = [h.as_evidence_item() for h in hits]
        for it in items:
            evidence[it["evidence_id"]] = it
        summary = (
            f"命中 {len(items)} 条来源"
            + ("（部分截断）" if any(r.truncated for r in results) else "")
            if items
            else "未找到匹配知识，按标准排障流程"
        )
        writer(
            {
                "type": "tool_call",
                "tool_id": tool_id,
                "name": "knowledge.search",
                "status": "finished",
                "summary": summary,
            }
        )
        if items:
            writer({"type": "evidence", "items": items})
    return {
        "stage": "diagnose",
        "substage": "retrieve",
        "knowledge_status": status,
        "evidence": evidence,
    }


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
    """用户可见回复（票 13）：reply.stream 按检索片段作答；主模型中断 → aborted / replaces / fallback（票 14）。

    路由不可用（HAIKE_LLM=off 或未配置）时保持票 05 的占位行为：只发 progress，不出消息。
    """
    writer = get_stream_writer()
    writer({"type": "progress", "stage": "diagnose"})
    await asyncio.sleep(_delay())
    router = get_model_router()
    if router is None or not state.get("product_state") in ("confirmed_sku", "category_only"):
        return {"stage": "diagnose"}
    strategy = (state.get("emotion") or {}).get("strategy", "normal")
    primary, fallback = reply_messages(
        state.get("text", ""),
        strategy=strategy,
        summary=_state_summary(state),
        evidence=list((state.get("evidence") or {}).values()),
        knowledge_status=state.get("knowledge_status"),
    )
    message_id = uuid.uuid5(
        uuid.NAMESPACE_URL, f"{state.get('session_id')}:{state.get('run_id')}:reply"
    ).hex
    out = await stream_to_writer(
        writer,
        router,
        "reply.stream",
        primary,
        message_id=message_id,
        budget_ms=15000,
        session_id=state.get("session_id"),
        lane=_lane(),
        fallback_messages=fallback,
    )
    msgs = list(state.get("visible_messages") or [])
    if out.completed:
        msgs.append(
            {
                "message_id": out.message_id,
                "kind": "reply",
                "text": out.text,
                "model_tier": out.model_tier,
            }
        )
    return {
        "stage": "diagnose",
        "visible_messages": msgs,
        "first_visible_ms": state.get("first_visible_ms") or out.first_visible_ms,
    }


def build_graph(checkpointer: BaseCheckpointSaver | None) -> CompiledStateGraph:
    g = StateGraph(SessionState)
    g.add_node("intake", intake)
    g.add_node("reply", reply)
    g.add_node("escalate", escalate)
    g.add_node("disambiguate", disambiguate)
    g.add_node("prepare_card", prepare_card)
    g.add_node("await_input", await_input)
    g.add_node("apply_action", apply_action)
    g.add_node("retrieve", retrieve)
    g.add_node("reassure", reassure)
    g.add_node("clarify", clarify)
    g.add_edge(START, "intake")
    g.add_conditional_edges(
        "intake",
        route_after_intake,
        {"disambiguate": "disambiguate", "reassure": "reassure", "escalate": "escalate"},
    )
    g.add_edge("reassure", "disambiguate")
    g.add_conditional_edges(
        "disambiguate",
        route_after_disambiguate,
        {
            "prepare_card": "prepare_card",
            "reply": "reply",
            "retrieve": "retrieve",
            "escalate": "escalate",
            "clarify": "clarify",
        },
    )
    g.add_edge("clarify", END)
    g.add_edge("prepare_card", "await_input")
    g.add_edge("await_input", "apply_action")
    g.add_conditional_edges(
        "apply_action",
        route_after_apply,
        {"reply": "reply", "retrieve": "retrieve", "escalate": "escalate"},
    )
    g.add_edge("retrieve", "reply")
    g.add_edge("reply", END)
    g.add_edge("escalate", END)
    return g.compile(checkpointer=checkpointer)
