"""票 05 的占位图：intake → reply 两个节点，只发 progress，不调模型。

票 15：intake 节点末尾运行 CP-in（规则服务，任何模型调用之前）；R3 / R4 命中写 safety_flags 并
经条件边直接进入 escalate 节点，不再经过 reply 及后续任何会调用模型的节点。
票 20：intake 后进入 disambiguate（产品目录匹配）；多命中走三段式
prepare_card → await_input(interrupt) → apply_action（08 §3）。awaiting_input 事件由运行器在
真正中断时发出（version 取自 checkpoint），卡片事件由 await_input 发出、重跑重发、按 card_id 幂等。
票 24：disambiguate 按「继续 / 澄清 / 升级」三种结果判定（app/sessions/clarify.py）：product_state 三分、
澄清追问节点 clarify（run 以 done(completed) 结束，不发步骤、不检索）、两次澄清后仍不明 → escalate(R7)；
用户对产品卡片不选而发自由文本 → intake 清掉失效 pending_card 并计一次澄清。
票 25：选中 / 提到范围外产品 → out_of_scope 节点（说明本期仅支持扫地机）→ escalate(R8)；request_human 全局动作：
有 interrupt 时经 apply_action、否则从 START 经 route_entry 直达 human_request，都以 R3 升级。
票 30：本 run 带故障图时 vision 节点先读图（tool_call diagnose.vision，观察项过 CP-in，R4 直接升级）再检索。
后续票在此图上替换 / 扩展节点（37 rediagnose……）。
节点通过 get_stream_writer() 发自定义事件，运行器映射为契约事件。
"""

from __future__ import annotations

import asyncio
import operator
import os
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from app.diagnose import (
    build_query,
    get_retrieval_config,
    rewrite_query,
    should_rewrite,
    synthesize,
)
from app.diagnose.query import product_term
from app.diagnose.vision import observe_images
from app.escalation.summary import build_summary, reassurance_text, summary_card_id
from app.images.runtime import current_image_store
from app.intake import extract_intake
from app.knowledge.adapter import KnowledgeScope
from app.knowledge.runtime import ensure_index, get_knowledge_adapter
from app.models.runtime import get_model_router
from app.plans.runtime import get_plan_library
from app.prompts import reassurance_messages, reply_messages
from app.rules import get_rules_service
from app.sessions import clarify as clarify_mod
from app.sessions.cards import candidates_key, current_version, derive_card_id, get_catalog
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
    entry: (
        str | None
    )  # 本 run 的入口：message（用户文本）/ action（无 interrupt 时的全局动作，票 25）
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
    # 票 29：图片引用 {image_id, purpose, sha256, mime, size, created_at, run_id}，跨 run 累积；字节只在 session_images
    image_refs: list[dict[str, Any]]
    # 票 32：诊断。retrieval_trace / image_observations 用 reducer 追加，读图（票 30）与检索并行写不同字段不覆盖；
    # plans_ranked [{plan_id, version, confidence, evidence_ids, source}]；rewrite_used 为本 run 是否已用掉补检索名额
    retrieval_trace: Annotated[list[dict[str, Any]], operator.add]
    image_observations: Annotated[list[str], operator.add]
    # 票 30：读图结果。visible_parts 累积；vision_status 为最近一次读图状态（ok / skipped / no_vision / failed）
    visible_parts: list[str]
    vision_status: str | None
    plans_ranked: list[dict[str, Any]]
    retrieval_rounds: int
    rewrite_used: bool
    query: str | None


def _delay() -> float:
    # 演示 / 手测用：让占位节点停留一会以观察 ping；默认 0
    return float(os.environ.get("PLACEHOLDER_NODE_DELAY_S", "0") or 0)


async def intake(state: SessionState) -> SessionState:
    writer = get_stream_writer()
    writer({"type": "progress", "stage": "intake"})
    if state.get("text") == "__raise__":  # 测试钩子：异常路径
        raise RuntimeError("placeholder node failure")
    await asyncio.sleep(_delay())
    image_ids = list(state.get("image_ids") or [])
    new_refs: list[dict[str, Any]] = []
    if image_ids and (img_store := current_image_store()) is not None:
        for ref in await img_store.refs(state.get("session_id", ""), image_ids):
            new_refs.append({**ref.public(), "run_id": state.get("run_id", "")})
    user_msg = {
        "role": "user",
        "text": state.get("text", ""),
        "image_ids": image_ids,
        "images": [
            {
                "image_id": r["image_id"],
                "purpose": r["purpose"],
                "sha256": r["sha256"],
                "mime": r["mime"],
                "size": r["size"],
            }
            for r in new_refs
        ],
        "run_id": state.get("run_id", ""),
        "at": state.get("at", ""),
    }
    # CP-in：任何模型调用之前（票 15，09 §1）
    cp = get_rules_service().check_in(text=state.get("text"), session_id=state.get("session_id"))
    update: SessionState = {
        "stage": "intake",
        "messages": [*state.get("messages", []), user_msg],
        "safety_flags": [*state.get("safety_flags", []), *cp.flags],
        "image_refs": [*state.get("image_refs", []), *new_refs],
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
        return "out_of_scope"
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
    """产品已确认或品类已知 → 本 run 带故障图先读图（票 30）→ 检索（票 28）；unknown 只允许追问（票 24），不检索。"""
    if state.get("product_state") not in ("confirmed_sku", "category_only"):
        return "reply"
    return "vision" if _new_fault_images(state) else "retrieve"


def _new_fault_images(state: SessionState) -> list[dict[str, Any]]:
    run_id = state.get("run_id", "")
    return [
        r
        for r in state.get("image_refs") or []
        if r.get("run_id") == run_id and r.get("purpose", "fault") == "fault"
    ]


async def vision(state: SessionState) -> SessionState:
    """读图观察（票 30，03 §1.4 步骤 1）：diagnose.vision（internal）→ observations 过 CP-in（R4 直接升级）→
    tool_call(diagnose.vision) started / finished / failed；视觉链不可用或失败时流程不中断，observations 为空。"""
    writer = get_stream_writer()
    writer({"type": "progress", "stage": "diagnose", "substage": "vision"})
    session_id, run_id = state.get("session_id", ""), state.get("run_id", "")
    refs = _new_fault_images(state)
    tool_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{session_id}:{run_id}:diagnose.vision").hex
    writer(
        {
            "type": "tool_call",
            "tool_id": tool_id,
            "name": "diagnose.vision",
            "status": "started",
            "summary": f"识别 {len(refs)} 张故障照片",
        }
    )
    out = await observe_images(
        get_model_router(),
        current_image_store(),
        session_id=session_id,
        refs=refs,
        text=state.get("text", ""),
        lane=_lane(),
        strategy=(state.get("emotion") or {}).get("strategy", "normal"),
        summary=_state_summary(state),
    )
    update: SessionState = {
        "stage": "diagnose",
        "substage": "vision",
        "vision_status": out.status,
        "image_observations": list(out.observations),
        "visible_parts": [*state.get("visible_parts", []), *out.visible_parts],
        "model_trace": [
            *state.get("model_trace", []),
            *([out.model_trace] if out.model_trace else []),
        ],
    }
    if out.status == "ok":
        summary = "；".join(out.observations) or "未识别出明显异常"
        if out.dropped_image_ids:
            summary += f"（仅识别最新 {len(out.used_image_ids)} 张）"
        writer(
            {
                "type": "tool_call",
                "tool_id": tool_id,
                "name": "diagnose.vision",
                "status": "finished",
                "summary": summary[:200],
            }
        )
        # 观察项再过一次 CP-in（09 §1）：smoke / deformed battery 等触发 R4，不再发起任何模型调用
        cp = get_rules_service().check_in(observations=out.observations, session_id=session_id)
        update["safety_flags"] = [*state.get("safety_flags", []), *cp.flags]
        update["observations"] = [
            *(state.get("observations") or []),
            *(f"图片：{o}" for o in out.observations),
        ]
        if cp.escalate:
            update["escalate_reason"] = next(h.rule_id for h in cp.hits if h.action == "escalate")
        return update
    writer(
        {
            "type": "tool_call",
            "tool_id": tool_id,
            "name": "diagnose.vision",
            "status": "failed",
            "summary": {
                "no_vision": "当前无可用的图片识别模型，按文字描述继续",
                "skipped": "图片识别未启用，按文字描述继续",
            }.get(out.status, "图片识别失败，按文字描述继续"),
        }
    )
    if out.user_hint:
        # 07 §6：备用模型不支持图片 → 请用户文字描述（固定文案）
        message_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{session_id}:{run_id}:vision_hint").hex
        writer({"type": "message_start", "message_id": message_id})
        writer({"type": "message", "message_id": message_id, "delta": out.user_hint})
        writer({"type": "message_end", "message_id": message_id, "status": "completed"})
        update["visible_messages"] = [
            *(state.get("visible_messages") or []),
            {
                "message_id": message_id,
                "kind": "vision_hint",
                "text": out.user_hint,
                "model_tier": None,
            },
        ]
    return update


def route_after_vision(state: SessionState) -> str:
    return "escalate" if state.get("escalate_reason") else "retrieve"


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
    if action.get("kind") == "request_human":
        # 票 25：awaiting_input 中点「请求人工」——卡片作废、不记结果，按 R3 升级
        update.update(_human_request_update(state, action))
    elif action.get("kind") == "select_product":
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
    if state.get("escalate_reason"):
        return "escalate"
    if state.get("out_of_scope"):
        return "out_of_scope"
    return _after_product(state)


# ---------------- 票 25：范围外 R8 与 request_human ----------------


def route_entry(state: SessionState) -> str:
    """START 分流：无 interrupt 时到达的全局动作直达 human_request，其余走 intake。"""
    if state.get("entry") == "action" and (state.get("last_action") or {}).get("kind") == (
        "request_human"
    ):
        return "human_request"
    return "intake"


def _human_request_update(state: SessionState, action: dict[str, Any]) -> SessionState:
    return {
        "escalate_reason": "R3",
        "safety_flags": [
            *state.get("safety_flags", []),
            {
                "rule_id": "R3",
                "source": "action",
                "term": "request_human",
                "ts": state.get("at", ""),
                "action_id": action.get("action_id"),
            },
        ],
        "pending_card": None,
        "last_action": None,
    }


async def human_request(state: SessionState) -> SessionState:
    """request_human 全局动作（08 §4 步骤 4）：忽略 version / pending，直接以 R3 升级。"""
    return _human_request_update(state, state.get("last_action") or {})


OUT_OF_SCOPE_TEXT = (
    "本期智能排障仅支持 eufy 扫地机器人。您咨询的「{name}」属于{category}，不在当前支持范围内；"
    "我已把情况整理好转给人工客服，稍后会有专人协助您。"
)


async def out_of_scope(state: SessionState) -> SessionState:
    """范围外产品子流程（02 §3、09 §2.1）：说明本期仅支持扫地机，随后 escalate(R8)。"""
    writer = get_stream_writer()
    writer({"type": "progress", "stage": "out_of_scope"})
    catalog = get_catalog()
    product = dict(state.get("product_confirmed") or {})
    category = product.get("category") or state.get("category") or ""
    spec = catalog.categories.get(category)
    category_name = spec.name if spec else (category or "其他品类")
    update: SessionState = {"stage": "out_of_scope", "escalate_reason": "R8"}
    if not product:
        # 只提到范围外品类、没有具体型号：摘要里的产品写品类（02 §5 product_confirmed.sku 可选）
        product = {
            "name": f"{category_name}（型号未确认）",
            "category": category,
            "in_scope": False,
        }
        update["product_confirmed"] = product
    text = OUT_OF_SCOPE_TEXT.format(
        name=product.get("name") or product.get("sku"), category=category_name
    )
    message_id = uuid.uuid5(
        uuid.NAMESPACE_URL, f"{state.get('session_id')}:{state.get('run_id')}:out_of_scope"
    ).hex
    writer({"type": "message_start", "message_id": message_id})
    writer({"type": "message", "message_id": message_id, "delta": text})
    writer({"type": "message_end", "message_id": message_id, "status": "completed"})
    update["visible_messages"] = [
        *(state.get("visible_messages") or []),
        {"message_id": message_id, "kind": "out_of_scope", "text": text, "model_tier": None},
    ]
    return update


# ---------------- 票 28：检索 → tool_call / evidence 事件 ----------------


def knowledge_scope_of(state: SessionState) -> KnowledgeScope:
    product = state.get("product_confirmed") or {}
    ps = state.get("product_state") or "unknown"
    category = product.get("category") or state.get("category") or "robot_vacuum"
    return KnowledgeScope(ps, category, product.get("sku") if ps == "confirmed_sku" else None)  # type: ignore[arg-type]


def retrieval_query(state: SessionState) -> str:
    """规范化查询（03 §1.4.1）：已确认产品 / 品类 + 有效症状；症状为空退回原文；unknown 返回空串。"""
    return build_query(dict(state))


def _remaining_ms(state: SessionState) -> int:
    """run 剩余预算：消息到达时间 + 文本轮 deadline（08 §8）。"""
    from app.sessions.runner import DEFAULT_DEADLINE_MS

    at = state.get("at")
    try:
        started = datetime.fromisoformat(at) if at else datetime.now(UTC)
    except ValueError:
        started = datetime.now(UTC)
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    elapsed = (datetime.now(UTC) - started).total_seconds() * 1000
    return int(DEFAULT_DEADLINE_MS - elapsed)


async def _search_round(
    adapter,
    query: str,
    scope: KnowledgeScope,
    top_k: int,
    *,
    round_no: int,
    session_id: str,
    run_id: str,
):
    """一轮：对两个库各一次请求（允许集合为空时适配器本地 no_match，不发请求）。返回 (results, trace_entries)。"""
    results = {}
    traces = []
    for kb in ("kb_manual", "kb_tickets"):
        r = await adapter.hybrid_search(kb, query, top_k, scope)
        results[kb] = r
        traces.append(
            {
                "round": round_no,
                "kb": kb,
                "query": query,
                "scope": {
                    "product_state": scope.product_state,
                    "category": scope.category,
                    "sku": scope.sku,
                },
                "status": r.status,
                "allowed_count": r.allowed_count,
                "hit_ids": [h.evidence_id for h in r.hits],
                "scores": [round(h.score, 4) for h in r.hits],
                "truncated": r.truncated,
                "latency_ms": r.latency_ms,
                "session_id": session_id,
                "run_id": run_id,
            }
        )
    return results, traces


async def retrieve(state: SessionState) -> SessionState:
    """diagnose 流水线（票 28 / 32）：规范化 query → 首轮检索（两库）→ 可选一次补检索（图片新增或无命中改写，共享名额）
    → synthesize 假设汇总。事件：tool_call started/finished/failed + evidence；query 只进 retrieval_trace（内部）。
    """
    writer = get_stream_writer()
    writer({"type": "progress", "stage": "diagnose", "substage": "retrieve"})
    session_id, run_id = state.get("session_id", ""), state.get("run_id", "")
    lane = _lane()
    rcfg = get_retrieval_config()
    scope = knowledge_scope_of(state)
    query = retrieval_query(state)
    evidence = dict(state.get("evidence") or {})
    tool_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{session_id}:{run_id}:knowledge.search").hex
    if not query:
        # 无可查内容（unknown 或既无症状也无原文）：不检索、不凭空生成；澄清由 disambiguate/clarify 负责
        return {
            "stage": "diagnose",
            "substage": "retrieve",
            "knowledge_status": "no_query",
            "query": None,
            "retrieval_trace": [
                {
                    "round": 0,
                    "status": "no_query",
                    "reason": "empty query",
                    "session_id": session_id,
                    "run_id": run_id,
                }
            ],
        }
    writer(
        {
            "type": "tool_call",
            "tool_id": tool_id,
            "name": "knowledge.search",
            "status": "started",
            "summary": "检索知识库",
        }
    )
    adapter = get_knowledge_adapter()
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
        plans = await _synthesize_step(state, evidence, lane, rcfg)
        return {
            "stage": "diagnose",
            "substage": "retrieve",
            "knowledge_status": "unavailable",
            "query": query,
            "retrieval_trace": [
                {
                    "round": 1,
                    "status": "unavailable",
                    "reason": "adapter disabled",
                    "query": query,
                    "session_id": session_id,
                    "run_id": run_id,
                }
            ],
            **plans,
        }
    await ensure_index(adapter)
    top_k = rcfg.retrieval.top_k
    results, trace = await _search_round(
        adapter, query, scope, top_k, round_no=1, session_id=session_id, run_id=run_id
    )
    rounds = 1
    rewrite_used = bool(state.get("rewrite_used"))
    hits = [h for r in results.values() for h in r.hits]
    per_kb_status = {kb: r.status for kb, r in results.items()}
    allowed_counts = {kb: r.allowed_count for kb, r in results.items()}
    # ---- 至多一次补检索：图片新增观察优先（票 30 接入），否则无命中改写（默认关闭）----
    remaining = _remaining_ms(state)
    router = get_model_router()
    decision = should_rewrite(
        cfg=rcfg.query_rewrite,
        per_kb_status=per_kb_status,
        allowed_counts=allowed_counts,
        has_hits=bool(hits),
        remaining_ms=remaining,
        quota_used=rewrite_used,
        product_state=state.get("product_state"),
        router_available=router is not None,
        in_clarify=bool(state.get("clarification")),
    )
    trace.append(
        {
            "round": 1,
            "kb": "*",
            "event": "rewrite_decision",
            "triggered": decision.triggered,
            "reason": decision.reason,
            "remaining_ms": remaining,
            "session_id": session_id,
            "run_id": run_id,
        }
    )
    if decision.triggered and router is not None:
        rewrite_used = True
        rw = await rewrite_query(
            router,
            original=query,
            user_text=state.get("text", ""),
            product=product_term(dict(state)),
            symptoms=[str(s) for s in state.get("symptoms") or []],
            cfg=rcfg.query_rewrite,
            session_id=session_id,
            lane=lane,
            budget_ms=min(
                rcfg.query_rewrite.budget_ms,
                max(500, remaining - rcfg.retrieval.min_remaining_for_second_round_ms),
            ),
        )
        trace.append(
            {
                "round": 2,
                "kb": "*",
                "event": "rewrite_result",
                "accepted": rw.query is not None,
                "rejected_reason": rw.rejected_reason,
                "query_before": query,
                "query_after": rw.query,
                "model_used": rw.model_used,
                "latency_ms": rw.latency_ms,
                "session_id": session_id,
                "run_id": run_id,
            }
        )
        remaining = _remaining_ms(state)
        if rw.query and remaining >= rcfg.retrieval.min_remaining_for_second_round_ms:
            results2, trace2 = await _search_round(
                adapter, rw.query, scope, top_k, round_no=2, session_id=session_id, run_id=run_id
            )
            rounds = 2
            trace += trace2
            hits2 = [h for r in results2.values() for h in r.hits]
            if hits2:
                hits, results = hits2, results2
                per_kb_status = {kb: r.status for kb, r in results.items()}
        elif rw.query:
            trace.append(
                {
                    "round": 2,
                    "kb": "*",
                    "event": "second_round_skipped",
                    "reason": f"budget:{remaining}ms",
                    "session_id": session_id,
                    "run_id": run_id,
                }
            )
    statuses = list(per_kb_status.values())
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
        if items:
            summary = (
                f"命中 {len(items)} 条来源"
                + ("（部分截断）" if any(r.truncated for r in results.values()) else "")
                + ("（已补检索）" if rounds == 2 else "")
            )
        else:
            summary = "未找到匹配知识，按标准排障流程"
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
    plans = await _synthesize_step(
        state, {h.evidence_id: h.as_evidence_item() for h in hits} if hits else {}, lane, rcfg
    )
    return {
        "stage": "diagnose",
        "substage": "retrieve",
        "knowledge_status": status,
        "evidence": evidence,
        "query": query,
        "retrieval_trace": trace,
        "retrieval_rounds": rounds,
        "rewrite_used": rewrite_used,
        **plans,
    }


async def _synthesize_step(
    state: SessionState, round_evidence: dict[str, dict[str, Any]], lane: str, rcfg
) -> dict[str, Any]:
    scope = knowledge_scope_of(state)
    allowed = get_plan_library().allowed_for(category=scope.category, sku=scope.sku)
    out = await synthesize(
        get_model_router(),
        state=dict(state),
        allowed=allowed,
        evidence=list(round_evidence.values()),
        observations=list(state.get("image_observations") or []),
        budget_ms=min(rcfg.synthesize.budget_ms, max(1000, _remaining_ms(state) - 2000)),
        max_hypotheses=rcfg.synthesize.max_hypotheses,
        session_id=state.get("session_id"),
        lane=lane,
    )
    update: dict[str, Any] = {"plans_ranked": out["plans_ranked"]}
    if out["model_trace"]:
        update["model_trace"] = [*state.get("model_trace", []), out["model_trace"]]
    if out["dropped"] or out["degraded"]:
        update["retrieval_trace"] = [
            {
                "event": "synthesize",
                "dropped": out["dropped"],
                "degraded": out["degraded"],
                "session_id": state.get("session_id"),
                "run_id": state.get("run_id"),
            }
        ]
    return update


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
    g.add_node("vision", vision)
    g.add_conditional_edges(
        "vision", route_after_vision, {"retrieve": "retrieve", "escalate": "escalate"}
    )
    g.add_node("reassure", reassure)
    g.add_node("clarify", clarify)
    g.add_node("out_of_scope", out_of_scope)
    g.add_node("human_request", human_request)
    g.add_conditional_edges(
        START, route_entry, {"intake": "intake", "human_request": "human_request"}
    )
    g.add_edge("human_request", "escalate")
    g.add_edge("out_of_scope", "escalate")
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
            "vision": "vision",
            "escalate": "escalate",
            "clarify": "clarify",
            "out_of_scope": "out_of_scope",
        },
    )
    g.add_edge("clarify", END)
    g.add_edge("prepare_card", "await_input")
    g.add_edge("await_input", "apply_action")
    g.add_conditional_edges(
        "apply_action",
        route_after_apply,
        {
            "reply": "reply",
            "retrieve": "retrieve",
            "vision": "vision",
            "escalate": "escalate",
            "out_of_scope": "out_of_scope",
        },
    )
    g.add_edge("retrieve", "reply")
    g.add_edge("reply", END)
    g.add_edge("escalate", END)
    return g.compile(checkpointer=checkpointer)
