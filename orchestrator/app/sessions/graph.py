"""会话单轮图：统一理解意图，更新问题状态，按需调用业务能力，提交结果。

每轮从 START 到 END；卡片等待保存在问题状态中，不依赖跨轮图中断。
只有明确且通过校验的命令才能消费待办，解释和回顾不会推进排障。
"""

from __future__ import annotations

import asyncio
import logging
import operator
import os
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.conversation.effects import durable_node
from app.conversation.effects import writer as get_stream_writer
from app.diagnose import (
    build_query,
    get_retrieval_config,
    rewrite_query,
    should_rewrite,
    synthesize,
)
from app.diagnose.decision import constrain_plans
from app.diagnose.grade import apply_assessment, grade_hits
from app.diagnose.query import CATEGORY_LABELS, product_term
from app.diagnose.vision import observe_images
from app.escalation.polish import polish_summary
from app.escalation.summary import build_summary, reassurance_text
from app.faultcards import fit_prompt_budget
from app.faultcards.runtime import get_fault_card_library
from app.guide import GUIDE_BUDGET_MS, apply_feedback, exhaust_plan, prepare_step
from app.images.runtime import current_image_store
from app.knowledge.adapter import KnowledgeScope
from app.knowledge.faq import get_faq_index
from app.knowledge.rerank import DashScopeReranker
from app.knowledge.runtime import ensure_index, get_knowledge_adapter
from app.knowledge.search import interleave_kbs, search_round
from app.models.runtime import get_model_router
from app.observability.runtime import record
from app.plans.runtime import get_plan_library
from app.prompts import reassurance_messages, reply_messages
from app.rules import get_rules_service
from app.sessions import clarify as clarify_mod
from app.sessions import receipt as receipt_mod
from app.sessions.cards import candidates_key, current_version, derive_card_id, get_catalog
from app.sessions.streaming import stream_to_writer

log = logging.getLogger("sessions.graph")


class SessionState(TypedDict, total=False):
    business_context: dict | None
    case_status: str | None
    human_involved: bool
    evaluation_source: str
    service_context: dict
    context_sources: dict
    policy_decision: dict | None
    proposal: dict | None
    case_id: str | None
    case_order_no: str | None
    execution: dict | None
    execution_key: str | None
    gate_result: dict | None
    prior_remedies: list[str]
    requested_remedy: str | None
    consult_intent: str | None
    last_consult_params: dict
    consult_params: dict
    consult_attempts: int
    consult_answered: bool
    l3_route: str | None
    human_request_info: bool
    human_decision_id: str | None
    task_queue: list[dict]
    emotion_trend: str
    emotion_actions: list[str]
    unresolved_turns: int
    emotion_track: list[dict]
    fault_localization: dict | None
    image_quality: dict | None
    retake_attempts: int
    completed_task_intent: str | None
    retake_skipped: bool
    input_id: str
    base_version: int
    committed_input_id: str
    committed_version: int
    input_seq: int
    history: list[dict[str, Any]]
    recall_entry_ids: list[str]
    target_issue_id: str | None
    active_issue_id: str | None
    issues: dict[str, Any]
    context_revision: int
    risk_cases: list[dict[str, Any]]
    turn_decision: dict[str, Any]
    applied_input_ids: list[str]
    pending_effects: list[dict[str, Any]]
    session_id: str
    run_id: str  # 当前 run，由运行器随输入写入，用户消息据此归入 timeline 对应位置
    at: str  # 本 run 收到消息的时间（ISO），用于 timeline user_message.at
    text: str
    stage: str
    substage: str | None
    image_ids: list[str]
    messages: list[dict[str, Any]]  # {role, text, image_ids, run_id, at}
    history_summary: dict | None
    session_preferences: dict
    current_evidence_ids: list[str]
    # card_id -> 用户对卡片的结果（selected_sku / feedback+note / confirmed_fields+skipped_reason），
    # 由后续票的 apply_action 节点写入；快照折叠 timeline 时读取（票 07）
    card_results: dict[str, dict[str, Any]]
    # 票 15：CP-in 命中记录 {rule_id, source, term, ts}，跨 run 累积；escalate_reason 为触发升级的规则编号
    safety_flags: list[dict[str, Any]]
    escalate_reason: str | None
    # 待办跨轮持久化；last_action 只表示本轮经过校验的命令。
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
    entry: str | None  # message / action，共用单轮入口。
    escalation_summary: dict[str, Any] | None  # 票 16：{card_id, reason, summary}
    # 票 39：凭证子流程状态 {status, image_ids, skipped_reason?, fields, confidence, edited, verified_facts, conflicts, next_step}
    receipt: dict[str, Any] | None
    # 票 17：intake 抽取结果；emotion.strategy 注入系统提示第二层；model_trace 累积各 task 命中模型
    emotion: dict[str, str]
    product_hints: list[str]
    symptoms: list[str]
    symptom_codes: list[str]
    diagnostic_decision: dict[str, Any]
    symptom_interview: dict[str, Any] | None
    model_trace: list[dict[str, Any]]
    # 票 28：检索结果。evidence 按 evidence_id 去重累积，供 step.evidence_ids 引用；knowledge_status 为最近一次四态
    evidence: dict[str, dict[str, Any]]
    knowledge_status: str | None
    # 票 13 / 18：本 run 已发出的可见消息 {message_id, kind: reassurance|reply, text, model_tier}
    visible_messages: list[dict[str, Any]]
    first_visible_ms: int | None
    # 票 29：图片引用 {image_id, purpose, sha256, mime, size, created_at, run_id}，跨 run 累积；字节只在 session_images
    image_refs: list[dict[str, Any]]
    processed_fault_image_ids: list[str]
    visual_product: dict[str, Any] | None
    # 票 32：诊断。retrieval_trace 用 reducer 追加（读图节点与检索写不同字段，不覆盖）；
    # plans_ranked [{plan_id, version, confidence, evidence_ids, source}]；rewrite_used 为本 run 是否已用掉补检索名额
    retrieval_trace: Annotated[list[dict[str, Any]], operator.add]
    image_observations: Annotated[list[str], operator.add]
    # 票 30：读图结果。visible_parts 累积；vision_status 为最近一次读图状态（ok / skipped / no_vision / failed）
    visible_parts: list[str]
    vision_status: str | None
    vision_echoed: bool  # 读图结果是否已在步骤卡上回显过（阶段 4，只回显一次）
    plans_ranked: list[dict[str, Any]]
    retrieval_rounds: int
    rewrite_used: bool
    evidence_quality: (
        str | None
    )  # 阶段 5：grade 的 coverage（sufficient / insufficient / none），未评分为 None
    query: str | None
    # 票 33：故障卡预加载 {key, doc_version, tokens, text} 与本 run 命中的 plan_id；diagnose_outcome ∈ evidence|standard_flow|escalate
    fault_card: dict[str, Any] | None
    fault_card_hits: list[str]
    diagnose_outcome: dict[str, Any] | None
    plan_cursor: dict[str, Any] | None
    # 票 34 / 35（09 §3.3）：steps_executed [{plan_id, step_id, card_id, title, instruction_src, feedback, note?, ts}]；
    # counters {executed, advanced, skipped, plans_exhausted}；exhausted_plans 已耗尽计划；
    # card_ready_ms 本 run 首张步骤卡就绪耗时；guide_trace 丢弃 / 改写 / 切换记录（reducer 追加）；
    # _verify 为 apply_action(step_feedback) 的本 run 判定（瞬态：done / next / escalate）
    steps_executed: list[dict[str, Any]]
    counters: dict[str, int]
    exhausted_plans: list[str]
    card_ready_ms: int | None
    guide_trace: Annotated[list[dict[str, Any]], operator.add]
    _verify: dict[str, Any] | None


def _delay() -> float:
    # 演示 / 手测用：让占位节点停留一会以观察 ping；默认 0
    return float(os.environ.get("PLACEHOLDER_NODE_DELAY_S", "0") or 0)


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
    if _new_fault_images(state):
        # Evidence may resolve the very prerequisite this decision is checking.
        return {"stage": "disambiguate", "_decision": {"outcome": "read_images"}}
    decision = clarify_mod.decide(dict(state), abandoned_card=state.get("abandoned_card"))
    update: SessionState = {"stage": "disambiguate", "abandoned_card": None, **decision.update}
    from app.actions.runtime import get_services
    if get_services() is not None and decision.reason == "symptom" and (state.get("requested_remedy") or (state.get("turn_decision") or {}).get("primary_intent") in {"refund_request", "address_update"}):
        decision.outcome = "continue"
    update["_decision"] = {
        "outcome": decision.outcome,
        "reason": decision.reason,
        **decision.detail,
    }
    return update


def route_after_reply(state: SessionState) -> str:
    return "guide" if state.get("plan_cursor") else "end"


def route_after_disambiguate(state: SessionState) -> str:
    decision = state.get("_decision") or {}
    if decision.get("outcome") == "read_images":
        return "vision"
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
            state.get("clarification"), reason, state.get("run_id", ""),
            question=out.text, input_id=state.get("input_id"),
        ),
        **({"symptom_interview": detail["symptom_interview"]} if detail.get("symptom_interview") else {}),
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
    from app.actions.runtime import get_services
    intent = (state.get("turn_decision") or {}).get("primary_intent")
    if get_services() is not None and state.get("product_state") == "confirmed_sku" and (
        intent in {"replacement_request", "refund_request", "address_update"} or state.get("requested_remedy")
    ):
        return "service_context"
    return "vision" if _new_fault_images(state) else "retrieve"


def _new_fault_images(state: SessionState) -> list[dict[str, Any]]:
    """Unconsumed evidence belonging to this issue, including earlier turns."""
    run_id = state.get("run_id", "")
    issue_id = state.get("active_issue_id")
    processed = set(state.get("processed_fault_image_ids") or [])
    # Old checkpoints have no issue_id on refs; resolve ownership from history.
    owned = {image_id for entry in state.get("history", [])
             if issue_id and entry.get("issue_id") == issue_id
             for image_id in (entry.get("payload") or {}).get("image_ids", [])}
    return [
        r
        for r in state.get("image_refs") or []
        if r.get("purpose", "fault") == "fault" and r["image_id"] not in processed
        and (r.get("issue_id") == issue_id if r.get("issue_id") else
             r.get("run_id") == run_id or r["image_id"] in owned)
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
        lane=_lane(),
        # 用户文字只用于代码层的图文冲突比对，不进视觉调用（阶段 2）
        text=state.get("text", ""),
        symptoms=[str(s) for s in state.get("symptoms") or []],
    )
    update: SessionState = {
        "stage": "diagnose",
        "substage": "vision",
        "vision_status": out.status,
        # Attempts are consumed even on failure; a new upload can retry without
        # replaying the same unavailable evidence on every subsequent text turn.
        "processed_fault_image_ids": list(dict.fromkeys([
            *state.get("processed_fault_image_ids", []), *[r["image_id"] for r in refs],
        ])),
        "image_observations": list(out.observations),
        "visible_parts": [*state.get("visible_parts", []), *out.visible_parts],
        "model_trace": [
            *state.get("model_trace", []),
            *([out.model_trace] if out.model_trace else []),
        ],
    }
    if out.status == "ok" and state.get("product_state") != "confirmed_sku":
        categories = {get_catalog().category_hint(o) for o in out.observations} - {None}
        if len(categories) == 1:
            update["visual_product"] = {"category": categories.pop(), "image_ids": out.used_image_ids}
    if out.fault_localization is not None:
        # 注意：不要在这里写 fault_card_hits —— 那个键存的是检索给出的 chunk_id，
        # 而签名映射给的是 plan_id，两种语义混在一个键里。签名先验真正的消费点在 retrieve
        # （见 `signature_plans(state['fault_localization'], card.faults)`），它直接读 fault_localization，
        # 所以这里只要把定位结果放进状态就够了。
        update.update(
            fault_localization=out.fault_localization,
            image_quality=out.fault_localization["image_quality"],
        )
        # 铭牌型号的使用权限与它的验证等级挂钩：
        # 已验证（裁剪放大后复读与全图一致）→ 可以自动锁 SKU；
        # 未验证（没能复看 / 两次不一致）→ 只当作一条产品线索，进 product_hints 参与后续正常的产品确认，
        #   绝不静默锁单 —— 一个编出来的、恰好在目录里的型号会让整条排障走错，而用户全程不知道。
        hint = out.fault_localization.get("model_hint")
        verified = out.fault_localization.get("model_hint_verified", False)
        if hint and state.get("product_state") != "confirmed_sku":
            candidates = get_catalog().lookup_product(hint)
            if len(candidates) == 1 and verified:
                chosen = candidates[0].model_dump(mode="json")
                update.update(
                    product_confirmed=chosen,
                    product_state="confirmed_sku",
                    category=chosen["category"],
                )
            elif candidates:
                log.info(
                    "model hint not auto-confirmed session=%s hint=%r candidates=%d verified=%s",
                    session_id, hint, len(candidates), verified,
                )
                # Unverified OCR must not bypass confirmation through the
                # normal text-hint lookup on the next disambiguation pass.
                update["visual_product"] = {
                    **(update.get("visual_product") or {}),
                    "model_hint": hint, "image_ids": out.used_image_ids,
                }
    if out.status == "unusable":
        # 像素层硬阈值判定不可用：一次模型都没调，直接走补拍（阶段 3）
        quality = (out.fault_localization or {}).get("image_quality", {})
        writer(
            {
                "type": "tool_call",
                "tool_id": tool_id,
                "name": "diagnose.vision",
                "status": "finished",
                "summary": f"照片质量不足（{'、'.join(quality.get('reasons', [])) or '未知'}），未调用识别模型",
            }
        )
        return update
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
        import copy

        from app.conversation.reduce import stable_id

        issues = copy.deepcopy(state["issues"])
        issue = issues[state["active_issue_id"]]
        for index, observation in enumerate(out.observations):
            issue.setdefault("facts", []).append(
                {
                    "fact_id": stable_id(state["input_id"], "vision", index),
                    "kind": "observation",
                    "value": f"图片：{observation}",
                    "quote": observation,
                    "issue_id": state["active_issue_id"],
                    "device_ref_id": issue["device_ref"]["device_ref_id"],
                    "status": "active",
                    "revision": 1,
                    "source_kind": "image_observation",
                    "source_entry_ids": [state["input_id"]],
                    "image_ids": out.used_image_ids,
                    "recorded_at": state["at"],
                }
            )
        issue["issue_revision"] += bool(out.observations)
        update.update(
            issues=issues,
            context_revision=state.get("context_revision", 0) + bool(out.observations),
        )
        if cp.escalate:
            update["escalate_reason"] = next(h.rule_id for h in cp.hits if h.action == "escalate")
            update["risk_cases"] = [
                *state.get("risk_cases", []),
                {
                    "risk_id": stable_id(state["input_id"], "vision_risk"),
                    "rule_id": "R4",
                    "status": "reported",
                    "source_input_ids": [state["input_id"]],
                    "reported_at": state["at"],
                    "issue_id": state["active_issue_id"],
                    "device_ref_id": issue["device_ref"]["device_ref_id"],
                    "restriction": "no_operations",
                    "policy_version": "2026-09-13",
                    "last_evidence_seq": state["input_seq"],
                },
            ]
            update["turn_decision"] = {
                **state["turn_decision"],
                "allowed_operations": False,
                "escalation_trigger": "R4",
            }
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
    from app.actions.runtime import get_services
    if get_services() is not None and not state.get('escalate_reason'):
        if (state.get('fault_localization') or {}).get('conflicts_with_text'):
            return 'vision_conflict'
        if (state.get('image_quality') or {}).get('usable') is False and not state.get('retake_skipped'):
            catalog = get_catalog()
            identity_texts = [state.get("text", ""), *state.get("product_hints", [])]
            if not state.get("category") and not state.get("product_confirmed") and not any(
                catalog.category_hint(text) or catalog.lookup_product(text) for text in identity_texts
            ):
                # Product identity can be supplied in text. Do not force a
                # fault-photo retake before knowing which device is involved.
                return "disambiguate"
            return 'prepare_retake'
    return "escalate" if state.get("escalate_reason") else "disambiguate"


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
    """发布持久待办；图继续提交并正常结束。"""
    from app.conversation.reduce import stable_id

    pc = dict(state["pending_card"])
    if not pc.get("input_token"):
        pc["card_id"] = stable_id(state["input_id"], state["active_issue_id"], pc["card_id"])
        pc["input_token"] = stable_id(pc["card_id"], "token")
    writer = get_stream_writer()
    writer(
        {
            "type": "pending_changed",
            "issue_id": state["active_issue_id"],
            "pending_id": pc["card_id"],
            "status": "active",
            "reason": "presented",
            "version": state["base_version"] + 1,
        }
    )
    if pc["kind"] == "select_product":
        writer(
            {
                "type": "product_card",
                "card_id": pc["card_id"],
                "version": current_version(),
                "candidates": pc["payload"]["candidates"],
            }
        )
    elif pc["kind"] == "step_feedback":
        # 票 34：步骤卡；唯一层级 step 对象（08 §5），重跑重发同一 card_id
        writer(
            {
                "type": "step_card",
                "card_id": pc["card_id"],
                "version": current_version(),
                "step": pc["payload"]["step"],
                **({"seen": pc["payload"]["seen"]} if pc["payload"].get("seen") else {}),
            }
        )
    elif pc["kind"] == "confirm_receipt":
        # 票 40：字段确认卡；confidence < 0.7 前端标黄，unreadable 为空字段可手输
        writer(
            {
                "type": "receipt_card",
                "card_id": pc["card_id"],
                "version": current_version(),
                **pc["payload"],
            }
        )
    elif pc["kind"] in {"confirm_context", "confirm_proposal", "upload_retake", "rate_satisfaction"}:
        event_type = {"confirm_context":"context_card", "confirm_proposal":"proposal_card", "upload_retake":"retake_card", "rate_satisfaction":"rating_card"}[pc["kind"]]
        writer({"type":event_type,"card_id":pc["card_id"],"version":current_version(),**pc["payload"]})
    # Waiting is business state. Every graph invocation reaches END normally.
    return {
        "pending_card": {
            **pc,
            "issue_id": state["active_issue_id"],
            "status": "active",
            "created_seq": pc.get("created_seq", state["input_seq"]),
            "input_token": pc.get("input_token") or pc["card_id"],
        }
    }


async def apply_action(state: SessionState) -> SessionState:
    """应用已通过目标、待办及载荷校验的业务命令。"""
    action = state.get("last_action") or {}
    pc = state.get("pending_card") or {}
    if pc:
        get_stream_writer()(
            {
                "type": "pending_changed",
                "issue_id": state["active_issue_id"],
                "pending_id": pc["card_id"],
                "status": "consumed",
                "reason": action.get("kind", "answer"),
                "version": state["base_version"] + 1,
            }
        )
    if action.get("kind") in {"confirm_context", "confirm_proposal", "decline_proposal", "skip_retake", "rate_satisfaction"}:
        from app.sessions.l3 import apply_l3_action
        return await apply_l3_action(state, action, pc)
    results = dict(state.get("card_results") or {})
    # 接收时间由输入账本固定；_verify 只对本次 step_feedback 有效。
    update: SessionState = {
        "pending_card": None,
        "last_action": None,
        "_verify": None,
    }
    if action.get("kind") == "skip_receipt":
        # 票 39：跳过凭证 → receipt.status=not_collected（记 skipped_reason）→ summarize；
        # 票 40：字段确认阶段跳过 → 凭证图已在，needs_manual_check
        reason = (action.get("payload") or {}).get("reason", "none")
        results[pc.get("card_id", "")] = {"skipped_reason": reason}
        receipt = (
            receipt_mod.skipped_after_upload(dict(state), reason)
            if pc.get("kind") == "confirm_receipt"
            else receipt_mod.skipped_receipt(dict(state), reason)
        )
        update.update(
            {
                "card_results": results,
                "receipt": receipt,
                "escalate_reason": receipt.get("collection_reason") or "R6",
            }
        )
    elif action.get("kind") == "confirm_receipt":
        # 票 41：字段确认后按 L1–L6 核对；规则结果进入摘要。
        payload = action.get("payload") or {}
        fields = dict(payload.get("fields") or {})
        edited = list(payload.get("edited") or [])
        receipt = receipt_mod.confirmed_receipt(dict(state), fields, edited)
        from app.conversation.business import BusinessContext
        update["business_context"] = BusinessContext.restore(state).observe(
            "receipt.confirm", fields, {}, state["input_id"]
        ).model_dump(mode="json")
        results[pc.get("card_id", "")] = {
            "confirmed_fields": receipt["fields"],
            "edited": receipt["edited"],
        }
        update.update(
            {
                "card_results": results,
                "receipt": receipt,
                "escalate_reason": receipt.get("collection_reason") or "R6",
            }
        )
    elif action.get("kind") == "step_feedback":
        update.update(_apply_step_feedback(state, action, pc, results))
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
    if state.get("l3_route"):
        return state["l3_route"]
    if state.get("escalate_reason"):
        return "escalate"
    if state.get("out_of_scope"):
        return "out_of_scope"
    verify = state.get("_verify")
    if verify:
        # 票 35：step_feedback 的判定——继续 → guide 出下一张卡；票 36：solved / DONE → close 结束语 → done(completed)
        return "guide" if verify["outcome"] == "next" else "close"
    return _after_product(state)


def _apply_step_feedback(
    state: SessionState,
    action: dict[str, Any],
    pc: dict[str, Any],
    results: dict[str, dict[str, Any]],
) -> SessionState:
    """票 35（03 §1.6、09 §3.3–§3.4）：反馈三态写 steps_executed / counters，按 next_on 推进游标，
    EXHAUSTED 时切换计划或 R2；CP-verify R1 / R1b / R1c。备注先过 CP-in（R4 → 升级）。无 LLM。"""
    payload = action.get("payload") or {}
    feedback = payload["feedback"]
    note = payload.get("note") or None
    card_id = pc.get("card_id", "")
    session_id = state.get("session_id", "")
    results[card_id] = {"feedback": feedback, **({"note": note} if note else {})}
    update: SessionState = {"stage": "verify", "substage": None, "card_results": results, "unresolved_turns": 0 if feedback == "solved" else (state.get("unresolved_turns") or 0) + 1}
    cp = get_rules_service().check_in(
        action_kind="step_feedback", action_note=note, session_id=session_id
    )
    flags = [*state.get("safety_flags", []), *cp.flags]
    if cp.escalate:
        rule = next(h.rule_id for h in cp.hits if h.action == "escalate")
        if rule == "R4":
            from app.conversation.policy import restrict_operations

            update.update(
                restrict_operations(dict(state), source_kind="feedback_note", quote=note or "")
            )
        update.update(
            {
                "safety_flags": flags,
                "escalate_reason": rule,
                "_verify": {"outcome": "escalate", "rule": rule},
            }
        )
        return update
    out = apply_feedback(
        state=dict(state), feedback=feedback, note=note, card_id=card_id, library=get_plan_library()
    )
    log.info(
        "cp_verify session=%s card=%s feedback=%s outcome=%s rule=%s counters=%s",
        session_id,
        card_id,
        feedback,
        out.outcome,
        out.escalate_reason or out.trace.get("rule"),
        out.counters,
        extra={
            "event": "cp_verify",
            "checkpoint": "cp_verify",
            "session_id": session_id,
            "card_id": card_id,
            "feedback": feedback,
            "outcome": out.outcome,
            "rule_id": out.escalate_reason,
            "counters": out.counters,
            "switched_to": out.switched_to,
            **out.trace,
        },
    )
    update.update(
        {
            "safety_flags": flags,
            "steps_executed": out.steps_executed,
            "counters": out.counters,
            "exhausted_plans": out.exhausted_plans,
            "plan_cursor": out.plan_cursor,
            "guide_trace": [
                {"event": "verify", "feedback": feedback, "outcome": out.outcome, **out.trace}
            ],
            "_verify": {
                "outcome": out.outcome,
                "rule": out.escalate_reason or out.trace.get("rule"),
                "switched_to": out.switched_to,
            },
        }
    )
    if out.outcome == "escalate":
        update["escalate_reason"] = out.escalate_reason
    return update


# ---------------- 票 25：范围外 R8 与 request_human ----------------


async def understand(state: SessionState) -> SessionState:
    from app.conversation.interpret import interpret_turn
    from app.conversation.policy import pending_risk_sources
    from app.conversation.reduce import reduce_turn

    if state.get("entry") == "message":
        get_stream_writer()({"type": "progress", "stage": "intake"})
    if state.get("entry") in {"human_decision", "case_command"}:
        from app.sessions.l3 import understand_human
        return await understand_human(state)
    await asyncio.sleep(_delay())
    recovered_risks = pending_risk_sources(dict(state), get_rules_service())
    if recovered_risks:
        state = {**state, "risk_cases": [*state.get("risk_cases", []), *recovered_risks]}
    text = (
        state.get("text", "")
        if state.get("entry") == "message"
        else ((state.get("last_action") or {}).get("payload") or {}).get("text", "")
    )
    cp = get_rules_service().check_in(text=text, session_id=state.get("session_id"))
    meaning, context = await interpret_turn(
        get_model_router(), dict(state), lane=os.environ.get("MODEL_LANE", "domestic")
    )
    from app.actions.runtime import get_services
    resumed_task = None
    if get_services() is not None and meaning.primary_intent == "resume_task":
        task = next((t for t in state.get("task_queue", []) if t["task_id"] == meaning.target_task_id and t["status"] in {"pending", "active"}), None)
        if task:
            from app.conversation.business import BusinessContext
            from app.conversation.tasks import task_business
            resumed_task = task
            state = {**state, "business_context": task_business(task, BusinessContext.restore(state)).model_dump(mode="json")}
            meaning = meaning.model_copy(update={"primary_intent": task["intent"], "secondary_intents": [], "business_reference": None, "answer_request": None})
        else:
            meaning = meaning.model_copy(update={"primary_intent": "unknown", "clarification": "请说明要优先处理哪项需求。"})
    if get_services() is not None and meaning.secondary_intents:
        from app.conversation.tasks import ordered_intents
        intents=ordered_intents(meaning.primary_intent, meaning.secondary_intents)
        meaning=meaning.model_copy(update={"primary_intent":intents[0],"secondary_intents":intents[1:]})
    if meaning.answer_request and meaning.primary_intent not in {"replacement_request", "refund_request", "address_update", "report_problem", "request_human"}:
        # A single factual question can require several reads. Those reads are
        # planned by the answer module, not queued as duplicate user tasks.
        meaning = meaning.model_copy(update={"secondary_intents": [i for i in meaning.secondary_intents if i not in {"order_query", "warranty_query", "logistics_query"}]})
    requested_business = None
    business_order_no = None
    if get_services() is not None and state.get("entry") == "message" and (
        meaning.primary_intent in {"replacement_request", "refund_request", "address_update"}
        or (state.get("requested_remedy") and (state.get("stage") == "context" or (state.get("pending_card") or {}).get("kind") in {"upload_receipt", "confirm_receipt"})
            and meaning.primary_intent in {"supplement", "unknown", "answer_pending"})
    ):
        from app.conversation.business import BusinessContext

        requested_business = BusinessContext.restore(state).accept(
            text, state["input_id"], meaning.business_reference.model_dump() if meaning.business_reference else None
        )
        from app.actions.params import IDENTIFIER
        if meaning.business_reference and meaning.business_reference.relation in {"case", "issue"} and state.get("case_order_no") and not IDENTIFIER.search(text):
            requested_business = requested_business.for_order(state["case_order_no"])
        binding = requested_business.bind("warranty.check")
        if binding.status == "ready":
            business_order_no = binding.params.get("order_no")
        if meaning.primary_intent not in {"replacement_request", "refund_request", "address_update"} and state.get("case_order_no") and business_order_no != state["case_order_no"]:
            requested_business, business_order_no = None, None
    # Context reported while discussing another order belongs to that subject,
    # not to the still-open service issue. Keep the full meaning for subject storage.
    reducer_meaning = meaning
    if get_services() is not None and state.get("entry") == "message" and requested_business is None:
        from app.conversation.business import BusinessContext
        focus = BusinessContext.restore(state).accept(text, state["input_id"], meaning.business_reference.model_dump() if meaning.business_reference else None)
        focus_order = focus.bind("warranty.check").params.get("order_no")
        if state.get("case_order_no") and focus_order != state["case_order_no"]:
            reducer_meaning = meaning.model_copy(update={"facts": [f for f in meaning.facts if f.kind != "context"]})
    update = reduce_turn(
        dict(state), reducer_meaning, precheck_risk=any(h.rule_id == "R4" for h in cp.hits),
        business_order_no=business_order_no,
        new_business_subject=requested_business is not None and requested_business.status == "missing",
    )
    if context.get("source") == "product_question":
        update["turn_decision"]["product_answered"] = True
    update["l3_route"] = None
    if update["turn_decision"].get("business_switched") and state.get("requested_remedy") and meaning.primary_intent not in {"replacement_request", "refund_request", "address_update"}:
        update["requested_remedy"] = state["requested_remedy"]
    from app.actions.runtime import get_services
    if get_services() is not None:
        from app.conversation.business import BusinessContext
        update["business_context"] = (requested_business.focused() if update["turn_decision"].get("business_switched") else BusinessContext.restore({**state, **update})).accept(
            text, state["input_id"], meaning.business_reference.model_dump() if meaning.business_reference else None
        ).model_dump(mode="json")
        from app.emotion.policy import evaluate_emotion
        emotion_update = evaluate_emotion(meaning.emotion_level, text, update.get("emotion_track") or [], state["input_id"], unresolved_turns=(update.get("unresolved_turns") or 0)+1, risk=not update["turn_decision"]["allowed_operations"])
        if state.get("entry") == "message":
            update.update(emotion_update)
            record("emotion_strategy", session_id=state["session_id"], run_id=state["run_id"], level=emotion_update["emotion"]["level"], trend=emotion_update["emotion_trend"], strategy=emotion_update["emotion"]["strategy"])
        from app.conversation.tasks import enqueue
        from app.sessions.l3 import say
        tasks, notice = enqueue(update.get("task_queue") or [],meaning.primary_intent,meaning.secondary_intents,text,state["input_id"], business=BusinessContext.restore({**state, **update}))
        if resumed_task:
            tasks = [{**task, "status": "active" if task["task_id"] == resumed_task["task_id"] else "pending"} if task["status"] in {"pending", "active"} else task for task in tasks]
            update["turn_decision"]["task_id"] = resumed_task["task_id"]
        update["task_queue"]=tasks
        if notice:
            say({**state,**update},notice)
        if state.get("entry") == "message" and "offer_human" in update.get("emotion_actions", []):
            say({**state, **update}, "很抱歉让您反复处理。您可以选择人工协助；如需补偿，我会将诉求交由人工评估。")
        context_values = dict(update.get("service_context") or {})
        context_sources = dict(update.get("context_sources") or {})
        reported = {fact.context_field: fact.value for fact in meaning.facts if fact.kind == "context" and fact.context_field and fact.quote and fact.quote in text}
        business = BusinessContext.restore({**state, **update}).remember(reported, state["input_id"], order_no=update.get("case_order_no") if update["turn_decision"].get("answer_scope") in {"case", "issue"} else None)
        update["business_context"] = business.model_dump(mode="json")
        from app.conversation.answers import conversation_view
        view = conversation_view({**state, **update})
        if not update.get("case_order_no") or view["issue_matches_focus"] or update["turn_decision"].get("answer_scope") in {"case", "issue"}:
            for key, value in reported.items():
                if context_sources.get(key) != "receipt":
                    context_values[key], context_sources[key] = value, "user"
        update.update(service_context=context_values, context_sources=context_sources)
    if context.get("source") != "validated_action":
        update["model_trace"] = [
            *state.get("model_trace", []),
            {
                "task": "intake",
                "model_used": context.get("model_used", "skipped"),
                "lane": context.get("lane", _lane()),
                "attempts": context.get("attempts", 1),
            },
        ]
    pending = update.get("pending_card") or {}
    current_input = next(
        (e for e in state.get("history", []) if e["entry_id"] == state["input_id"]), {}
    )
    source = current_input.get("payload") or {}
    if state.get("entry") == "message":
        update["messages"] = [
            *state.get("messages", []),
            {
                "role": "user",
                "text": state.get("text", ""),
                "image_ids": list(source.get("image_ids", [])),
                "images": list(source.get("images", [])),
                "run_id": state["run_id"],
                "at": state["at"],
                "input_id": state["input_id"],
            },
        ]
        update["image_refs"] = [
            *state.get("image_refs", []),
            *[dict(ref, run_id=state["run_id"], issue_id=update["active_issue_id"]) for ref in source.get("images", [])],
        ]
    receipt_ids = source.get("image_ids", []) if source.get("purpose") == "receipt" else []
    if (
        state.get("entry") == "message"
        and receipt_ids
        and pending.get("kind") in {"upload_receipt", "confirm_receipt"}
        and not update["turn_decision"].get("escalation_trigger")
        and meaning.primary_intent not in {"new_issue", "resume_issue", "correct"}
    ):
        update["receipt"] = receipt_mod.uploaded_receipt({**state, **update}, receipt_ids)
        update["turn_decision"].update(
            receipt_upload=True, reply_mode="receipt", clarification=None
        )
        update["turn_decision"]["pending_changes"].append(
            {
                "issue_id": update["active_issue_id"],
                "pending_id": pending["card_id"],
                "status": "consumed",
                "reason": "receipt_uploaded",
            }
        )
        update["pending_card"] = None
        update["escalate_reason"] = (update.get("receipt") or {}).get("collection_reason", "R6")
    update["recall_entry_ids"] = []
    if meaning.history_request:
        from app.conversation.reader import read_history_for_turn

        selection = read_history_for_turn(dict(state), meaning.history_request.model_dump())
        update["recall_entry_ids"] = selection["source_entry_ids"]
        update["turn_decision"]["history_selection"] = selection
        if selection.get("error"):
            update["turn_decision"].update(reply_mode="clarify", clarification=selection["error"])
    from app.conversation.commands import resolve_command

    reopening = None
    if get_services() is not None:
        from app.sessions.l3 import reopening_request
        reopening = await reopening_request({**state, **update}, meaning)
    if update["turn_decision"].get("symptom_answered"):
        update["turn_decision"].update(reply_mode="diagnose", clarification=None)
        command, clarification = None, None
    elif reopening and not reopening.get("clarification"):
        update["turn_decision"]["reopen_request"] = reopening
        command, clarification = None, None
    elif reopening:
        command, clarification = None, reopening["clarification"]
    else:
        command, clarification = resolve_command({**state, **update}, meaning)
    if command:
        update["last_action"] = command
        update["turn_decision"]["internal_command"] = command["kind"]
    elif clarification:
        update["turn_decision"].update(reply_mode="clarify", clarification=clarification)
    if cp.flags:
        update["safety_flags"] = [*state.get("safety_flags", []), *cp.flags]
    record(
        "conversation_turn",
        session_id=state.get("session_id"),
        run_id=state.get("run_id"),
        input_id=state.get("input_id"),
        context={k: v for k, v in context.items() if k != "messages"},
        semantic=meaning.model_dump(),
        decision=update.get("turn_decision"),
        context_revision=update.get("context_revision"),
    )
    for change in update["turn_decision"].get("pending_changes", []):
        get_stream_writer()(
            {"type": "pending_changed", "version": state["base_version"] + 1, **change}
        )
    get_stream_writer()(
        {
            "type": "issue_changed",
            "active_issue_id": update["active_issue_id"],
            "input_id": state["input_id"],
            "resolved_issue_id": update["active_issue_id"],
            "version": state["base_version"] + 1,
            "issues": [
                {"issue_id": k, "title": v.get("title"), "status": v.get("status")}
                for k, v in update["issues"].items()
            ],
        }
    )
    return update


async def dialogue(state: SessionState) -> SessionState:
    from app.conversation.reply import reply_to_turn

    result = await reply_to_turn(dict(state), get_stream_writer())
    # Conversational detours finish at the same business stage as the saved issue.
    get_stream_writer()({"type": "progress", "stage": state.get("stage") or "intake"})
    if state.get("turn_decision", {}).get("resumed_pending"):
        result.update(await await_input(state))
    return result


async def commit_issue(state: SessionState) -> SessionState:
    from app.actions.runtime import get_services
    from app.analytics.l3 import episode
    from app.conversation.reduce import persist_issue
    services = get_services()
    if services is not None:
        case = await services.cases.store.get(state["case_id"]) if state.get("case_id") else None
        if case and state.get("emotion", {}).get("level") == "complaint_risk" and not case["complaint_risk"]:
            case = await services.cases.transition(case["case_id"], case["status"], "投诉风险上升", complaint_risk=True, priority="high")
        fact = episode(dict(state), case)
        try:
            await services.cases.store.record_episode(fact)
        except Exception:
            # A metrics outage must not discard a successfully persisted business receipt.
            log.exception("L3 episode projection failed for session %s", state["session_id"])
        get_stream_writer()({"type": "progress", "stage": state.get("stage") or "intake"})
        state = {**state, "case_status": case["status"] if case else None, "human_involved": fact["human_involved"]}
    persisted = persist_issue(dict(state))
    issue = persisted["issues"].get(state["active_issue_id"], {})
    previous = issue.get("latest_summary")
    if previous and issue.get("summary_issue_revision") != issue.get("issue_revision"):
        refreshed = await summarize(
            {
                **state,
                **persisted,
                "summary_refresh": True,
                "escalate_reason": previous["summary"]["reason"]["rule_id"],
            }
        )
        persisted["issues"] = refreshed["issues"]
    return {
        **persisted,
        "case_status": state.get("case_status"),
        "human_involved": state.get("human_involved", False),
        "committed_input_id": state["input_id"],
        "committed_version": state["base_version"] + 1,
    }


def route_after_close(state: SessionState) -> str:
    from app.actions.runtime import get_services
    return "advance_tasks" if get_services() is not None else "commit_issue"


def route_entry(state: SessionState) -> str:
    from app.actions.runtime import get_services
    from app.sessions.l3 import CONSULT_INTENTS
    if state.get("entry") == "case_command":
        return "apply_case_command"
    if state.get("entry") == "human_decision":
        return "apply_human_decision"
    decision = state.get("turn_decision") or {}
    if decision.get("reopen_request"):
        return "reopen_case"
    if decision.get("receipt_upload"):
        return "receipt_extract"
    if decision.get("escalation_trigger"):
        return "escalate"
    if decision.get("business_ambiguous"):
        return "dialogue"
    if decision.get("symptom_answered") or decision.get("product_answered"):
        return "disambiguate"
    if decision.get("business_switched"):
        return "service_context"
    if (state.get('pending_card') or {}).get('kind') == 'upload_retake' and _new_fault_images(state):
        return 'vision'
    if decision.get("internal_command") or state.get("entry") == "action":
        # Accepted card commands have already been scoped and validated. They
        # must be applied before free-text business routing can advance a flow.
        return "apply_action"
    if get_services() is not None:
        intent = decision.get("primary_intent")
        if state.get("emotion", {}).get("level") == "complaint_risk" and state.get("product_state") == "confirmed_sku" and not state.get("case_id"):
            return "service_context"
        from app.conversation.answers import FACTUAL_INTENTS
        if decision.get("answer_request") and intent in FACTUAL_INTENTS:
            return "consult"
        if intent in CONSULT_INTENTS or (state.get("consult_intent") and intent in {"supplement","unknown","answer_pending"}):
            return "consult"
        if intent == "confirm_received" and state.get("case_id"):
            return "track"
        if intent in {"replacement_request","refund_request","address_update"}:
            return "service_context"
        if state.get("requested_remedy") and (state.get("stage") == "context" or (state.get("pending_card") or {}).get("kind") in {"upload_receipt", "confirm_receipt"}) and intent in {"supplement", "unknown", "answer_pending"}:
            return "service_context"
        if state.get("human_request_info") and intent in {"supplement","correct","answer_pending"}:
            return "service_context"
        if state.get("case_id") and state.get("stage") == "awaiting_human":
            return "dialogue"
        if intent == "report_problem" and decision.get("allowed_operations") and not state.get("pending_card"):
            return "disambiguate"
    if decision.get("diagnostic_request") and decision.get("allowed_operations") and not state.get("pending_card"):
        from app.diagnose.decision import owns_diagnostic_reply
        if owns_diagnostic_reply(state):
            if state.get("stage") == "done" or (state.get("exhausted_plans") and not decision.get("patches")):
                return "dialogue"
            return "disambiguate"
    if decision.get("reply_mode") in {"dialogue", "clarify"}:
        if (decision.get("primary_intent") in {"report_problem", "supplement", "unknown", "answer_pending"}
                and decision.get("allowed_operations", True) and _new_fault_images(state)):
            return "disambiguate"
        return "dialogue"
    if (state.get("emotion") or {}).get(
        "strategy", "normal"
    ) != "normal" and get_model_router() is not None:
        return "reassure"
    return "disambiguate"


OUT_OF_SCOPE_TEXT = (
    "本期智能排障仅支持 eufy 扫地机器人。您咨询的「{name}」属于{category}，不在当前支持范围内；"
    "我会整理问题记录，供您交给人工客服继续处理。"
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
    remaining_ms: int | None = None,
    allow_rerank: bool = True,
):
    """一轮：委托 app.knowledge.search.search_round（阶段 3：原 query + 可选同义变体 × 两库并发 → RRF → 可选 rerank，
    + 可选本地 FAQ）。开关全关时 = 两库各一次并发（P0-1）。返回 (results, trace_entries)。"""
    rcfg = get_retrieval_config()
    if remaining_ms is not None and remaining_ms < rcfg.rerank.min_remaining_ms:
        allow_rerank = False
    out = await search_round(
        adapter,
        query,
        scope,
        top_k,
        cfg=rcfg,
        round_no=round_no,
        session_id=session_id,
        run_id=run_id,
        faq_index=get_faq_index() if rcfg.faq.enabled else None,
        reranker=_reranker(rcfg) if rcfg.rerank.enabled else None,
        allow_rerank=allow_rerank,
    )
    for t in out.trace:
        if "event" not in t:
            record("knowledge_search", **t)
    return out.results, out.trace


async def _grade_second_round(
    hits, assessment, rcfg, state, lane, trace, session_id, run_id, graded_out
):
    """第二轮新增命中的评分：grade.second_round 开且预算够时再评一次（第 2 次 grade 调用），否则标 unsure。"""
    fresh = [h for h in hits if h.grade is None]
    if not fresh or not rcfg.grade.enabled or assessment is None or assessment.status != "graded":
        return hits, assessment
    router = get_model_router()
    remaining = _remaining_ms(state)
    if not rcfg.grade.second_round or router is None or remaining < rcfg.grade.min_remaining_ms:
        for h in fresh:
            h.grade = "unsure"
        return hits, assessment
    second = await grade_hits(
        router,
        hits=fresh,
        user_text=state.get("text", ""),
        symptoms=[str(s) for s in state.get("symptoms") or []],
        product=product_term(dict(state)) or None,
        cfg=rcfg.grade,
        budget_ms=min(rcfg.grade.budget_ms, max(500, remaining - 2000)),
        session_id=session_id,
        lane=lane,
    )
    if second.status == "graded":
        kept_fresh = apply_assessment(fresh, second, keep_min=0)
        dropped = {h.evidence_id for h in fresh} - {h.evidence_id for h in kept_fresh}
        graded_out.extend(h for h in hits if h.evidence_id in dropped)
        hits = [h for h in hits if h.evidence_id not in dropped]
        assessment.verdicts.update(second.verdicts)
        assessment.filtered_ids += second.filtered_ids
        if second.coverage == "sufficient" or (
            second.coverage == "insufficient" and assessment.coverage == "none"
        ):
            assessment.coverage = second.coverage
    trace.append(second.as_trace(round=2, kb="*", session_id=session_id, run_id=run_id))
    return hits, assessment


async def _expand_parents(adapter, hits, rcfg) -> list[str] | None:
    """适配器支持时（真实 WeKnora 适配器或录制包装器透传）做 small-to-big；不支持返回 None。"""
    real = getattr(adapter, "inner", adapter)
    expand = getattr(real, "expand_parents", None)
    if expand is None:
        return None
    refresh = getattr(real, "refresh_chunks", None)
    if refresh is not None and getattr(real, "chunks_loaded_at", 0) is None:
        await refresh()
    return expand(
        hits, max_items=rcfg.parent_expand.max_items, max_chars=rcfg.parent_expand.max_chars
    )


_reranker_cache: dict[str, DashScopeReranker] = {}


def _reranker(rcfg) -> DashScopeReranker:
    key = f"{rcfg.rerank.model}:{rcfg.rerank.timeout_ms}"
    if key not in _reranker_cache:
        _reranker_cache[key] = DashScopeReranker(
            model=rcfg.rerank.model, timeout_s=rcfg.rerank.timeout_ms / 1000
        )
    return _reranker_cache[key]


async def _second_round(
    adapter,
    query: str,
    scope: KnowledgeScope,
    top_k: int,
    *,
    budget_ms: int,
    reason: str,
    session_id: str,
    run_id: str,
):
    """补检索整轮硬超时（P0-2，08 §8「补检索整轮 ≤ 3 s」）。超时返回 (None, [timeout trace])，调用方沿用首轮结果。"""
    try:
        results2, trace2 = await asyncio.wait_for(
            _search_round(
                adapter,
                query,
                scope,
                top_k,
                round_no=2,
                session_id=session_id,
                run_id=run_id,
                allow_rerank=False,
            ),
            timeout=budget_ms / 1000,
        )
    except TimeoutError:
        log.warning(
            "second round timeout session=%s budget_ms=%d reason=%s", session_id, budget_ms, reason
        )
        return None, [
            {
                "round": 2,
                "kb": "*",
                "event": "second_round_timeout",
                "reason": reason,
                "budget_ms": budget_ms,
                "query": query,
                "session_id": session_id,
                "run_id": run_id,
            }
        ]
    for t2 in trace2:
        t2["reason"] = reason
    return results2, trace2


def _merge_rounds(hits, results, results2):
    """P0-3：两轮命中按 evidence_id 合并去重（首轮优先，第二轮新命中追加）；每库状态取两轮中较好者。"""
    seen = {h.evidence_id for h in hits}
    merged = list(hits)
    for r in results2.values():
        for h in r.hits:
            if h.evidence_id not in seen:
                seen.add(h.evidence_id)
                merged.append(h)
    rank = {"ok": 0, "replay": 0, "no_match": 1, "unavailable": 2}
    status = {
        kb: min(
            (results[kb].status, results2.get(kb, results[kb]).status),
            key=lambda x: rank.get(x, 3),
        )
        for kb in results
    }
    truncated = any(r.truncated for r in (*results.values(), *results2.values()))
    return merged, status, truncated


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
    # 票 33：产品确认后预加载故障卡（≤ 800 token 常驻），按症状 / 查询命中的条目作为 fault_card 证据
    fc_lib = get_fault_card_library()
    card = fc_lib.for_scope(sku=scope.sku, category=scope.category) if fc_lib else None
    fault_card_state = None
    fc_evidence: list[dict[str, Any]] = []
    if card is not None:
        fc_hits = card.match([query, *[str(s) for s in state.get("symptoms") or []]], symptom_codes=state.get("symptom_codes") or [])
        from app.diagnose.localization import signature_plans
        signature_ids=signature_plans(state.get('fault_localization'), card.faults)
        fc_hits=[*[f for f in card.faults if f.plan_id in signature_ids], *[f for f in fc_hits if f.plan_id not in signature_ids]]
        allowed_ids = {
            p.plan_id for p in constrain_plans(state, get_plan_library().allowed_for(
                category=scope.category, sku=scope.sku,
                symptom_codes=state.get("symptom_codes") or [],
            ))
        }
        fc_hits = [f for f in fc_hits if f.plan_id in allowed_ids]
        fault_card_state = {
            "key": card.key,
            "doc_version": card.doc_version,
            "tokens": card.tokens(),
            "text": card.render(fc_hits),
        }
        fc_evidence = card.evidence_items(fc_hits)
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
        for it in fc_evidence:
            evidence[it["evidence_id"]] = it
        plans = await _synthesize_step(
            state, {e["evidence_id"]: e for e in fc_evidence}, lane, rcfg
        )
        plans.update(
            _diagnose_outcome(
                plans.get("plans_ranked") or [],
                knowledge_status="unavailable",
                fault_card_hits=[e["chunk_id"] for e in fc_evidence],
            exhausted_plans=state.get("exhausted_plans") or [],
            )
        )
        return {
            "stage": "diagnose",
            "substage": "retrieve",
            "knowledge_status": "unavailable",
            "evidence": evidence,
            "current_evidence_ids": [e["evidence_id"] for e in fc_evidence],
            "fault_card": fault_card_state,
            "fault_card_hits": [e["chunk_id"] for e in fc_evidence],
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
        adapter,
        query,
        scope,
        top_k,
        round_no=1,
        session_id=session_id,
        run_id=run_id,
        remaining_ms=_remaining_ms(state),
    )
    # 票 30 的 vision 节点已在本 run 先行读图（R4 已在其后直接升级）；这里只消费观察项
    observations = (
        list(state.get("image_observations") or []) if state.get("vision_status") == "ok" else []
    )
    rounds = 1
    rewrite_used = bool(state.get("rewrite_used"))
    hits = interleave_kbs(results)  # 阶段 3：跨库按库内名次交错（各库分值量纲不同）
    per_kb_status = {kb: r.status for kb, r in results.items()}
    allowed_counts = {kb: r.allowed_count for kb, r in results.items()}
    truncated_any = any(r.truncated for r in results.values())
    remaining = _remaining_ms(state)
    router = get_model_router()
    # ---- 阶段 5 S2：一次相关性评分（评分不是证据，只剔除 irrelevant、给 coverage）----
    assessment = None
    graded_out: list = []
    if (
        rcfg.grade.enabled
        and hits
        and router is not None
        and remaining >= rcfg.grade.min_remaining_ms
    ):
        assessment = await grade_hits(
            router,
            hits=hits,
            user_text=state.get("text", ""),
            symptoms=[str(s) for s in state.get("symptoms") or []],
            product=product_term(dict(state)) or None,
            cfg=rcfg.grade,
            budget_ms=min(
                rcfg.grade.budget_ms,
                max(500, remaining - rcfg.retrieval.min_remaining_for_second_round_ms),
            ),
            session_id=session_id,
            lane=lane,
            strategy=(state.get("emotion") or {}).get("strategy", "normal"),
        )
        before = list(hits)
        hits = apply_assessment(hits, assessment, keep_min=rcfg.grade.keep_min)
        graded_out = [
            h for h in before if h not in hits
        ]  # 被剔除的仍作为「检索到的来源」发 evidence 事件
        trace.append(assessment.as_trace(round=1, kb="*", session_id=session_id, run_id=run_id))
        remaining = _remaining_ms(state)
    elif rcfg.grade.enabled and hits:
        trace.append(
            {
                "round": 1,
                "kb": "*",
                "event": "grade_result",
                "status": "skipped",
                "reason": "router_unavailable" if router is None else f"budget:{remaining}ms",
                "session_id": session_id,
                "run_id": run_id,
            }
        )
    # graded 且没有一条 relevant → 视同无相关证据（S3：允许一次补检索），但 knowledge_status 仍按实际检索结果
    no_relevant = (
        assessment is not None and assessment.status == "graded" and not assessment.relevant_ids
    )
    has_relevant_hits = bool(hits) and not no_relevant
    # 改写决策表（09 §4.1）看的是「实际请求的库全部 no_match」；graded 全不相关时把 ok 视作 no_match 参与决策，
    # 只影响是否补检索，不改写给前端的 knowledge_status
    decision_status = {
        kb: ("no_match" if (st == "ok" and no_relevant) else st) for kb, st in per_kb_status.items()
    }
    # ---- 至多一次补检索：图片新增观察优先（票 30 接入），否则无命中改写（默认关闭）----
    if (
        observations
        and not rewrite_used
        and remaining >= rcfg.retrieval.min_remaining_for_second_round_ms
    ):
        # 图片新增信息优先占用唯一补检索名额（03 §1.4.1 规则 4）：query + 观察项，同 scope 再检索一轮
        rewrite_used = True
        q2 = " ".join([query, *observations])
        results2, trace2 = await _second_round(
            adapter,
            q2,
            scope,
            top_k,
            budget_ms=rcfg.retrieval.second_round_budget_ms,
            reason="image_observations",
            session_id=session_id,
            run_id=run_id,
        )
        trace += trace2
        if results2 is not None:
            hits, per_kb_status, truncated_any = _merge_rounds(hits, results, results2)
            hits, assessment = await _grade_second_round(
                hits, assessment, rcfg, state, lane, trace, session_id, run_id, graded_out
            )
        rounds = 2
    decision = should_rewrite(
        cfg=rcfg.query_rewrite,
        per_kb_status=decision_status,
        allowed_counts=allowed_counts,
        has_hits=has_relevant_hits
        or bool(fc_evidence),  # 故障卡直接命中也不触发改写（票 33）；graded 全不相关视同无命中
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
            category_label=CATEGORY_LABELS.get(scope.category, scope.category),
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
            results2, trace2 = await _second_round(
                adapter,
                rw.query,
                scope,
                top_k,
                budget_ms=min(
                    rcfg.retrieval.second_round_budget_ms,
                    max(500, remaining - rcfg.retrieval.min_remaining_for_second_round_ms),
                ),
                reason="query_rewrite",
                session_id=session_id,
                run_id=run_id,
            )
            rounds = 2
            trace += trace2
            if results2 is not None:
                hits, per_kb_status, truncated_any = _merge_rounds(hits, results, results2)
                hits, assessment = await _grade_second_round(
                    hits, assessment, rcfg, state, lane, trace, session_id, run_id, graded_out
                )
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
        items = [h.as_evidence_item() for h in (*hits, *graded_out)]  # 评分剔除的仍是检索到的来源
        for it in items:
            evidence[it["evidence_id"]] = it
        if items:
            summary = (
                f"命中 {len(items)} 条来源"
                + ("（部分截断）" if truncated_any else "")
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
    # 阶段 4：父块扩展（只改 synthesize 输入，SSE evidence 已按子块 snippet 发出）
    if hits and rcfg.parent_expand.enabled:
        expanded = await _expand_parents(adapter, hits, rcfg)
        if expanded is not None:
            trace.append(
                {
                    "round": rounds,
                    "kb": "kb_manual",
                    "event": "parent_expanded",
                    "ids": expanded,
                    "session_id": session_id,
                    "run_id": run_id,
                }
            )
    round_evidence = {h.evidence_id: h.as_internal_item() for h in hits} if hits else {}
    for it in fc_evidence:
        round_evidence.setdefault(it["evidence_id"], it)
        evidence.setdefault(it["evidence_id"], it)
    plans = await _synthesize_step(state, round_evidence, lane, rcfg)
    trace += plans.pop("retrieval_trace", [])
    plans.update(
        _diagnose_outcome(
            plans.get("plans_ranked") or [],
            knowledge_status=status,
            fault_card_hits=[e["chunk_id"] for e in fc_evidence],
            exhausted_plans=state.get("exhausted_plans") or [],
        )
    )
    return {
        "stage": "diagnose",
        "substage": "retrieve",
        "knowledge_status": status,
        "evidence": evidence,
        "current_evidence_ids": list(round_evidence),
        "query": query,
        "retrieval_trace": trace,
        "retrieval_rounds": rounds,
        "rewrite_used": rewrite_used,
        "evidence_quality": (
            assessment.coverage
            if assessment is not None and assessment.status == "graded"
            else None
        ),
        "fault_card": fault_card_state,
        "fault_card_hits": [e["chunk_id"] for e in fc_evidence],
        **plans,
    }


async def _synthesize_step(
    state: SessionState, round_evidence: dict[str, dict[str, Any]], lane: str, rcfg
) -> dict[str, Any]:
    scope = knowledge_scope_of(state)
    allowed = get_plan_library().allowed_for(
        category=scope.category, sku=scope.sku,
        symptom_codes=state.get("symptom_codes") or [],
    )
    allowed = constrain_plans(state, allowed)
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


def _diagnose_outcome(
    plans_ranked: list[dict[str, Any]], *, knowledge_status: str, fault_card_hits: list[str],
    exhausted_plans: list[str] = (),
) -> dict[str, Any]:
    """票 33 / 09 §4：有假设 → 进 guide；来源 synthesize（有证据）或 standard_flow（预写计划默认顺序）；无适用计划 → R5。"""
    if not plans_ranked:
        return {
            "diagnose_outcome": {
                "mode": "escalate",
                "reason": "R5",
                "knowledge_status": knowledge_status,
            },
            "escalate_reason": "R5",
            "plan_cursor": None,
        }
    available = [p for p in plans_ranked if p["plan_id"] not in exhausted_plans]
    if not available:
        return {"diagnose_outcome": {"mode": "escalate", "reason": "R2"}, "escalate_reason": "R2", "plan_cursor": None}
    first = available[0]
    mode = (
        "standard_flow"
        if first.get("source") == "standard_flow"
        else ("fault_card" if fault_card_hits and knowledge_status != "ok" else "evidence")
    )
    note = {
        "evidence": None,
        "fault_card": "依据产品故障卡",
        "standard_flow": "按标准排障流程"
        if knowledge_status == "no_match"
        else "知识库暂不可用，按标准排障流程",
    }[mode]
    plan = get_plan_library().get(first["plan_id"])
    return {
        "diagnose_outcome": {
            "mode": mode,
            "note": note,
            "knowledge_status": knowledge_status,
            "plan_id": first["plan_id"],
        },
        "plan_cursor": {
            "plan_id": plan.plan_id,
            "version": plan.version,
            "step_id": plan.first_step().step_id,
            "source": first.get("source"),
        },
    }


def route_after_retrieve(state: SessionState) -> str:
    if state.get("escalate_reason"):
        return "escalate"
    # Only guide may publish operations, after evidence and pre-step policy checks.
    return "guide" if state.get("plan_cursor") else "reply"


async def guide(state: SessionState) -> SessionState:
    if "prefer_proposal_over_more_steps" in state.get("emotion_actions", []) and (state.get("counters") or {}).get("executed",0) >= 2:
        return {"escalate_reason":"R2","pending_card":None}
    """排障引导（票 34，03 §1.5）：取 plan_cursor 步骤 → 去重 / 证据校验 / CP-pre-step → 已审核原文发布
    → pending_card(kind=step_feedback)；随后 await_input 发 step_card。当前计划剩余步骤全被丢弃 → 切换计划或 R2。"""
    writer = get_stream_writer()
    writer({"type": "progress", "stage": "guide"})
    session_id = state.get("session_id", "")
    remaining = _remaining_ms(state)
    budget = min(GUIDE_BUDGET_MS, remaining - 2000) if remaining >= 3000 else 0
    work = dict(state)
    trace: list[dict[str, Any]] = []
    update: SessionState = {"stage": "guide", "substage": None, "_verify": None}
    for _ in range(len(state.get("plans_ranked") or []) + 2):
        prep = await prepare_step(
            state=work,
            library=get_plan_library(),
            rules=get_rules_service(),
            router=get_model_router(),
            lane=_lane(),
            session_id=session_id,
            budget_ms=budget,
        )
        trace += [{"event": "step_dropped", **d} for d in prep.dropped]
        if prep.outcome == "ready":
            from app.conversation.reduce import stable_id
            published_card_id = stable_id(state["input_id"], state["active_issue_id"], prep.card_id)
            elapsed = _elapsed_ms(state)
            log.info(
                "step_card ready session=%s card=%s plan=%s step=%s rewritten=%s card_ready_ms=%s",
                session_id,
                published_card_id,
                prep.step["plan_id"],
                prep.step["step_id"],
                prep.rewritten,
                elapsed,
                extra={
                    "event": "card_ready",
                    "session_id": session_id,
                    "card_id": published_card_id,
                    "card_ready_ms": elapsed,
                },
            )
            # 隐式确认（阶段 4）：本轮读图有结果且还没回显过时，在首张步骤卡上附一句「我看到了什么」。
            # 只回显一次 —— 每张步骤卡都重复一遍会变成噪音。
            from app.diagnose.localization import echo_findings

            seen = (
                echo_findings(state.get("fault_localization"))
                if state.get("vision_status") == "ok" and not state.get("vision_echoed")
                else None
            )
            payload = {"step": prep.step, **({"seen": seen} if seen else {})}
            update.update(
                {
                    "pending_card": {
                        "card_id": published_card_id,
                        "input_token": stable_id(published_card_id, "token"),
                        "kind": "step_feedback",
                        "payload": payload,
                    },
                    **({"vision_echoed": True} if seen else {}),
                    "plan_cursor": prep.plan_cursor,
                    "card_ready_ms": elapsed,
                    "counters": work.get("counters") or {},
                    "exhausted_plans": list(work.get("exhausted_plans") or []),
                    "guide_trace": [
                        *trace,
                        {
                            "event": "step_ready",
                            "card_id": published_card_id,
                            "rewritten": prep.rewritten,
                        },
                    ],
                }
            )
            if prep.evidence:
                writer({"type": "evidence", "items": list(prep.evidence.values())})
                update["evidence"] = {**state.get("evidence", {}), **prep.evidence}
                update["current_evidence_ids"] = list(dict.fromkeys([*state.get("current_evidence_ids", []), *prep.evidence]))
            if prep.model_trace:
                update["model_trace"] = [*state.get("model_trace", []), prep.model_trace]
            return update
        # exhausted：本计划没有可下发的步骤 → 09 §3.4 切换或 R2
        cursor = work.get("plan_cursor") or {}
        out = exhaust_plan(work, cursor.get("plan_id", ""), library=get_plan_library())
        trace.append({"event": "plan_exhausted", "plan_id": cursor.get("plan_id"), **out.trace})
        work.update(
            {
                "plan_cursor": out.plan_cursor,
                "counters": out.counters,
                "exhausted_plans": out.exhausted_plans,
            }
        )
        if out.outcome == "escalate":
            update.update(
                {
                    "escalate_reason": out.escalate_reason,
                    "plan_cursor": None,
                    "counters": out.counters,
                    "exhausted_plans": out.exhausted_plans,
                    "guide_trace": trace,
                }
            )
            return update
    update.update({"escalate_reason": "R2", "plan_cursor": None, "guide_trace": trace})
    return update


def route_after_guide(state: SessionState) -> str:
    return "escalate" if state.get("escalate_reason") else "await_input"


# ---------------- 票 36：A1 完成——结束语与 done(completed) ----------------


def closing_text(state: SessionState) -> str:
    """结束语固定模板（09 §3.4、02 §4.1）：不调模型，回放 / 断网也能出；带上解决问题的步骤标题与产品名。"""
    steps = list(state.get("steps_executed") or [])
    solved = next((s for s in reversed(steps) if s.get("feedback") == "solved"), None)
    product = (state.get("product_confirmed") or {}).get("name")
    who = f"您的 {product}" if product else "设备"
    parts = ["太好了，问题已经解决！"]
    if solved and solved.get("title"):
        parts.append(f"这次是「{solved['title']}」起了作用，")
    else:
        parts.append("按步骤处理后，")
    parts.append(f"{who}现在可以正常使用了。")
    parts.append("建议按说明书定期做同样的保养。之后如果再遇到问题，随时回来找我。")
    return "".join(parts)


async def close(state: SessionState) -> SessionState:
    """票 36：verify 判定 solved / next_on=DONE → 结束语以 message 事件流式下发 → stage=done → done(completed)。

    无模型调用（与 CP-verify 一样确定性、零外部依赖）；结束语进 visible_messages(kind=closing)，
    结构化日志 a1_complete 带规则（solved / next_on:DONE）与计数器。
    """
    writer = get_stream_writer()
    writer({"type": "progress", "stage": "done"})
    session_id = state.get("session_id", "")
    run_id = state.get("run_id", "")
    message_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{session_id}:{run_id}:close").hex
    text = closing_text(state)
    writer({"type": "message_start", "message_id": message_id})
    writer({"type": "message", "message_id": message_id, "delta": text})
    writer({"type": "message_end", "message_id": message_id, "status": "completed"})
    verify = state.get("_verify") or {}
    counters = state.get("counters") or {}
    log.info(
        "a1_complete session=%s rule=%s steps=%d counters=%s",
        session_id,
        verify.get("rule"),
        len(state.get("steps_executed") or []),
        counters,
        extra={
            "event": "a1_complete",
            "checkpoint": "cp_verify",
            "session_id": session_id,
            "rule_id": verify.get("rule"),
            "counters": counters,
            "steps_executed": len(state.get("steps_executed") or []),
        },
    )
    msgs = list(state.get("visible_messages") or [])
    msgs.append({"message_id": message_id, "kind": "closing", "text": text, "model_tier": None})
    return {
        "stage": "done",
        "substage": None,
        "plan_cursor": None,
        "visible_messages": msgs,
        "guide_trace": [{"event": "close", "rule": verify.get("rule")}],
    }


def _elapsed_ms(state: SessionState) -> int:
    """本 run 已耗时（card_ready_ms 口径，04 §2）：消息 / 动作到达时间 → 现在。"""
    from app.sessions.runner import DEFAULT_DEADLINE_MS

    return max(0, DEFAULT_DEADLINE_MS - _remaining_ms(state))


async def escalate(state: SessionState) -> SessionState:
    """escalate 子流程入口（09 §5.1，票 39）：安全 / 人工 / R7 / R8 直接摘要；常规升级先收凭证。

    本节点只做分流与阶段推进；发凭证请求在 prepare_receipt → await_input，摘要在 summarize。
    """
    writer = get_stream_writer()
    update: SessionState = {"stage": "escalate"}
    if receipt_mod.needs_collection(dict(state)) and not receipt_mod.has_uploaded(dict(state)):
        writer({"type": "progress", "stage": "escalate", "substage": "collect_receipt"})
        update["substage"] = "collect_receipt"
        update["receipt"] = state.get("receipt") or receipt_mod.empty_receipt()
    return update


def route_escalate(state: SessionState) -> str:
    if receipt_mod.diagnostic_only(state):
        return "summarize"
    from app.actions.runtime import get_services
    if get_services() is not None and state.get("product_state") == "confirmed_sku" and state.get("escalate_reason") in {"R1","R1b","R1c","R2","R6"}:
        return "service_context"
    s = dict(state)
    if receipt_mod.has_uploaded(s):
        return "receipt_extract"
    if receipt_mod.needs_collection(s):
        return "prepare_receipt"
    return "summarize"


async def prepare_receipt(state: SessionState) -> SessionState:
    """凭证收集位置的 pending_card（kind=upload_receipt，无卡片事件）；不含 interrupt，只执行一次。"""
    card_id = receipt_mod.receipt_card_id(
        state.get("session_id", ""), state.get("escalate_reason") or "R3"
    )
    receipt = {
        **(state.get("receipt") or receipt_mod.empty_receipt()),
        "collection_reason": state.get("escalate_reason"),
    }
    return {
        "pending_card": {"card_id": card_id, "kind": "upload_receipt", "payload": {}},
        "receipt": receipt,
    }


async def receipt_extract(state: SessionState) -> SessionState:
    """票 40：warranty.receipt_ocr（internal，视觉）→ fields / confidence / unreadable → 写 pending_card(confirm_receipt)。

    识别失败或无视觉模型：字段为空、全部 unreadable，卡片仍发出供手输或跳过。tool_call(warranty.receipt_ocr) 记录过程。
    """
    writer = get_stream_writer()
    writer({"type": "progress", "stage": "escalate", "substage": "extract"})
    session_id, run_id = state.get("session_id", ""), state.get("run_id", "")
    receipt = dict(state.get("receipt") or {})
    image_ids = list(receipt.get("image_ids") or [])
    tool_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{session_id}:{run_id}:warranty.receipt_ocr").hex
    writer(
        {
            "type": "tool_call",
            "tool_id": tool_id,
            "name": "warranty.receipt_ocr",
            "status": "started",
            "summary": f"识别 {len(image_ids)} 张购买凭证",
        }
    )
    ocr = await receipt_mod.extract_receipt(
        get_model_router(),
        current_image_store(),
        session_id=session_id,
        image_ids=image_ids,
        refs=list(state.get("image_refs") or []),
        lane=_lane(),
        summary=_state_summary(state),
    )
    readable = [k for k in receipt_mod.FIELDS if ocr.fields.get(k)]
    writer(
        {
            "type": "tool_call",
            "tool_id": tool_id,
            "name": "warranty.receipt_ocr",
            "status": "finished" if ocr.status == "ok" else "failed",
            "summary": (
                f"识别出 {len(readable)} 个字段"
                + (f"，{len(ocr.unreadable)} 个看不清" if ocr.unreadable else "")
                if ocr.status == "ok"
                else "凭证识别不可用，请手动填写或跳过"
            ),
        }
    )
    new_receipt = receipt_mod.extracted_receipt(dict(state), ocr)
    return {
        "stage": "escalate",
        "substage": "confirm_fields",
        "receipt": new_receipt,
        "model_trace": [
            *state.get("model_trace", []),
            *([ocr.model_trace] if ocr.model_trace else []),
        ],
        "pending_card": {
            "card_id": receipt_mod.confirm_card_id(session_id, image_ids),
            "kind": "confirm_receipt",
            "payload": receipt_mod.card_payload(new_receipt),
        },
    }


async def summarize(state: SessionState) -> SessionState:
    """安全 / 人工升级：安抚句（固定文案，不调模型）→ 结构化摘要 escalation_summary（票 16）。

    摘要由图状态直接渲染，模型不可用也能生成；问题字段可选调用 escalate.summary，失败仍直渲染。
    """
    writer = get_stream_writer()
    writer({"type": "progress", "stage": "escalate", "substage": "summarize"})
    reason = state.get("escalate_reason") or "R3"
    session_id = state.get("session_id", "")
    run_id = state.get("run_id", "")
    message_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{session_id}:{run_id}:reassure").hex
    text = reassurance_text(reason)
    if not state.get("summary_refresh"):
        writer({"type": "message_start", "message_id": message_id})
        writer({"type": "message", "message_id": message_id, "delta": text})
        writer({"type": "message_end", "message_id": message_id, "status": "completed"})
    summary = build_summary(
        dict(state), reason=reason, lane=os.environ.get("MODEL_LANE", "domestic")
    )
    summary = await polish_summary(
        summary,
        get_model_router(),
        session_id=session_id,
        lane=os.environ.get("MODEL_LANE", "domestic"),
        budget_ms=max(0, _remaining_ms(state) - 2000),
    )
    import copy

    from app.conversation.reduce import stable_id

    issue_id = state["active_issue_id"]
    issues = copy.deepcopy(state["issues"])
    issue = issues[issue_id]
    previous = issue.get("latest_summary") or {}
    revision = previous.get("revision", 0) + 1
    summary_id = stable_id(issue_id, "summary")
    card_id = stable_id(summary_id, revision)
    event = {
        "type": "escalation_summary",
        "card_id": card_id,
        "summary": summary.model_dump(mode="json"),
        "summary_id": summary_id,
        "revision": revision,
        "issue_id": issue_id,
        "updated_at": state["at"],
        "source_through_seq": state["input_seq"],
        "previous_card_id": previous.get("card_id"),
        "handoff_status": "prepared",
    }
    writer(event)
    writer(
        {
            "type": "summary_updated",
            **{
                k: event[k]
                for k in (
                    "issue_id",
                    "summary_id",
                    "revision",
                    "card_id",
                    "previous_card_id",
                    "source_through_seq",
                    "updated_at",
                )
            },
        }
    )
    issue["summary_issue_revision"] = issue.get("issue_revision")
    issue["latest_summary"] = {k: v for k, v in event.items() if k != "type"}
    issue["handoff"] = {
        "handoff_id": stable_id(issue_id, "handoff"),
        "status": "prepared",
        "prepared_at": state["at"],
        "reason_refs": [state["input_id"]],
    }
    return {
        "stage": "escalate",
        "substage": "summarize",
        "issues": issues,
        "escalation_summary": dict(event, reason=reason),
    }


async def reply(state: SessionState) -> SessionState:
    """用户可见回复（票 13）：reply.stream 按检索片段作答；主模型中断 → aborted / replaces / fallback（票 14）。

    路由不可用（HAIKE_LLM=off 或未配置）时保持票 05 的占位行为：只发 progress，不出消息。
    """
    writer = get_stream_writer()
    writer({"type": "progress", "stage": "diagnose"})
    await asyncio.sleep(_delay())
    if any(task.get("status") in {"active", "pending"} for task in state.get("task_queue", [])):
        # The scheduler has already explained the task order. A second free-form
        # answer to the original multi-request message could invent actions for
        # suspended tasks. Let guide publish only the selected diagnostic step.
        return {"stage": "diagnose"}
    from app.diagnose.decision import owns_diagnostic_reply
    if owns_diagnostic_reply(state):
        from app.conversation.reply import reply_to_turn
        await reply_to_turn(dict(state), writer)
        return {"stage": "diagnose"}
    router = get_model_router()
    if router is None or not state.get("product_state") in ("confirmed_sku", "category_only"):
        return {"stage": "diagnose"}
    strategy = (state.get("emotion") or {}).get("strategy", "normal")
    outcome = state.get("diagnose_outcome") or {}
    evidence_items = [
        (state.get("evidence") or {})[eid]
        for eid in state.get("current_evidence_ids", [])
        if eid in (state.get("evidence") or {})
    ]
    # 票 33：故障卡常驻上下文；总输入 ≤ 8k token，超出先裁证据
    card_text = (state.get("fault_card") or {}).get("text")
    kept, _ = fit_prompt_budget([e.get("snippet", "") for e in evidence_items], budget=6000)
    primary, fallback = reply_messages(
        state.get("text", ""),
        strategy=strategy,
        summary={**_state_summary(state), "flow_note": outcome.get("note")},
        evidence=evidence_items[: len(kept)],
        knowledge_status=state.get("knowledge_status"),
        fault_card=card_text,
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
    from app.sessions import l3
    g = StateGraph(SessionState)
    l3_routes = {
        "service_context": ["await_input", "prepare_receipt", "propose"],
        "propose": ["commit_issue", "await_human", "summarize", "await_input"],
        "authorize": ["execute", "await_human", "commit_issue", "service_context"],
        "execute": ["commit_issue", "await_human", "track", "await_input"],
        "track": ["advance_tasks"],
        "await_human": ["commit_issue"],
        "consult": ["commit_issue", "summarize", "advance_tasks"],
        "apply_human_decision": ["await_input", "authorize", "propose", "commit_issue"],
        "apply_case_command": ["commit_issue"],
        "reopen_case": ["service_context", "escalate"],
    }
    for name, targets in l3_routes.items():
        g.add_node(name, durable_node(getattr(l3, name)))
        g.add_conditional_edges(name, l3.route, {target: target for target in targets})
    g.add_node("understand", durable_node(understand))
    g.add_node("dialogue", durable_node(dialogue))
    g.add_node("commit_issue", durable_node(commit_issue))
    g.add_edge(START, "understand")
    g.add_edge("dialogue", "commit_issue")
    g.add_node("reply", durable_node(reply))
    g.add_node("escalate", durable_node(escalate))
    g.add_node("summarize", durable_node(summarize))
    g.add_node("prepare_receipt", durable_node(prepare_receipt))
    g.add_node("receipt_extract", durable_node(receipt_extract))
    g.add_conditional_edges(
        "escalate",
        route_escalate,
        {
            "service_context": "service_context",
            "summarize": "summarize",
            "prepare_receipt": "prepare_receipt",
            "receipt_extract": "receipt_extract",
        },
    )
    g.add_edge("prepare_receipt", "await_input")
    g.add_edge("receipt_extract", "await_input")  # 票 40：确认字段卡片
    g.add_edge("summarize", "commit_issue")
    g.add_node("disambiguate", durable_node(disambiguate))
    g.add_node("prepare_card", durable_node(prepare_card))
    g.add_node("await_input", durable_node(await_input))
    g.add_node("apply_action", durable_node(apply_action))
    g.add_node("retrieve", durable_node(retrieve))
    g.add_node("vision", durable_node(vision))
    g.add_node("prepare_retake", durable_node(l3.prepare_retake))
    g.add_conditional_edges("prepare_retake",l3.route,{"await_input":"await_input", "summarize":"summarize"})
    g.add_node("vision_conflict",durable_node(l3.vision_conflict))
    g.add_edge("vision_conflict","commit_issue")
    g.add_conditional_edges(
        "vision", route_after_vision, {"disambiguate": "disambiguate", "escalate": "escalate", "prepare_retake":"prepare_retake", "vision_conflict":"vision_conflict"}
    )
    g.add_node("reassure", durable_node(reassure))
    g.add_node("clarify", durable_node(clarify))
    g.add_node("out_of_scope", durable_node(out_of_scope))
    g.add_node("guide", durable_node(guide))
    g.add_node("close", durable_node(close))
    g.add_node("advance_tasks",durable_node(l3.advance_tasks))
    g.add_conditional_edges("advance_tasks",l3.route,{target:target for target in ("consult","service_context","disambiguate","await_input","commit_issue")})
    g.add_conditional_edges("close",route_after_close, {"advance_tasks":"advance_tasks","commit_issue":"commit_issue"})
    g.add_conditional_edges(
        "understand",
        route_entry,
        {
            **{name:name for name in ("consult","service_context","track","apply_human_decision","apply_case_command","reopen_case","vision")},
            "disambiguate": "disambiguate",
            "reassure": "reassure",
            "escalate": "escalate",
            "apply_action": "apply_action",
            "dialogue": "dialogue",
            "receipt_extract": "receipt_extract",
        },
    )
    g.add_edge("out_of_scope", "escalate")
    g.add_edge("reassure", "disambiguate")
    g.add_conditional_edges(
        "disambiguate",
        route_after_disambiguate,
        {
            "prepare_card": "prepare_card",
            "service_context": "service_context",
            "reply": "reply",
            "retrieve": "retrieve",
            "vision": "vision",
            "escalate": "escalate",
            "clarify": "clarify",
            "out_of_scope": "out_of_scope",
        },
    )
    g.add_edge("clarify", "commit_issue")
    g.add_edge("prepare_card", "await_input")
    g.add_edge("await_input", "commit_issue")
    g.add_conditional_edges(
        "apply_action",
        route_after_apply,
        {
            **{target:target for target in ("service_context","authorize","propose","await_human","commit_issue")},
            "reply": "reply",
            "retrieve": "retrieve",
            "vision": "vision",
            "escalate": "escalate",
            "out_of_scope": "out_of_scope",
            "guide": "guide",
            "close": "close",
        },
    )
    g.add_conditional_edges(
        "retrieve", route_after_retrieve, {"reply": "reply", "guide": "guide", "escalate": "escalate"}
    )
    g.add_conditional_edges("reply", route_after_reply, {"guide": "guide", "end": "commit_issue"})
    g.add_conditional_edges(
        "guide", route_after_guide, {"await_input": "await_input", "escalate": "escalate"}
    )
    g.add_edge("commit_issue", END)
    return g.compile(checkpointer=checkpointer)
