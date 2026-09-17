"""L3 graph nodes: deterministic policy, explicit consent, durable execution and cases."""

import hashlib
import json
from datetime import date

from haike_contracts.common import REMEDY_LADDER

from app.actions.gate import AuthorizationGate
from app.actions.runtime import require_services
from app.actions.store import ExecutionBusy
from app.backends.protocol import BackendError
from app.cases.service import case_event
from app.conversation.business import BusinessContext
from app.conversation.effects import writer
from app.conversation.reduce import stable_id
from app.policy.engine import PolicyEngine
from app.policy.fault_class import derive_fault_class
from app.policy.models import PolicyInput

CONTEXT_FIELDS = ("region_purchase", "region_use", "channel", "platform")
CONSULT_INTENTS = {"logistics_query", "warranty_query", "order_query"}
REMEDY_TITLES = {
    "parts": "寄送更换配件",
    "repair": "申请维修",
    "replace": "申请换货",
    "refund": "申请退款审核",
    "paid_repair": "申请付费维修",
}


def say(state, text):
    mid = stable_id(state["input_id"], "l3", text)
    emit = writer()
    emit(
        {
            "type": "message_start",
            "message_id": mid,
            "issue_id": state.get("active_issue_id"),
            "reply_to_input_id": state["input_id"],
        }
    )
    emit({"type": "message", "message_id": mid, "delta": text})
    emit({"type": "message_end", "message_id": mid, "status": "completed"})


def pending(state, kind, payload):
    return {"kind": kind, "card_id": stable_id(state["input_id"], kind), "payload": payload}


def policy_input(state):
    context = state.get("service_context") or {}
    receipt = state.get("receipt") or {}
    facts = receipt.get("verified_facts") or {}
    raw_date = facts.get("purchase_date") or (receipt.get("fields") or {}).get("purchase_date")
    try:
        purchase = date.fromisoformat(raw_date) if raw_date else None
    except (ValueError, TypeError):
        purchase = None
    return PolicyInput(
        sku=(state.get("product_confirmed") or {}).get("sku"),
        category=state.get("category") or (state.get("product_confirmed") or {}).get("category"),
        **{k: context.get(k) for k in CONTEXT_FIELDS},
        purchase_date=purchase,
        receipt_status=receipt.get("status", "not_collected"),
        dealer_authorized={"true": True, "false": False}.get(facts.get("authorized")),
        fault_class=derive_fault_class(state),
        prior_remedies=state.get("prior_remedies") or [],
        today=date.fromisoformat(state["at"][:10]),
    )


def evaluate(state):
    return PolicyEngine(require_services().policy_loader.load()).decide(policy_input(state))


def emit_case(state, row, reason="案件状态更新"):
    writer()(
        case_event(
            row, issue_id=state["active_issue_id"], version=state["base_version"] + 1, reason=reason
        )
    )


async def service_context(state):
    services = require_services()
    writer()({"type": "progress", "stage": "context"})
    product_update = {}
    context = dict(state.get("service_context") or {})
    sources = dict(state.get("context_sources") or {})
    receipt = dict(state.get("receipt") or {})
    business = BusinessContext.restore(state)
    workflow = business.for_order(state["case_order_no"]) if state.get("case_order_no") else business
    business.subjects.update(workflow.subjects)
    binding = workflow.bind("warranty.check")
    params = binding.params
    subject = workflow.subjects.get(workflow.active_subject_id)
    for key, fact in (subject.facts.items() if subject else []):
        if key in CONTEXT_FIELDS and sources.get(key) != "receipt":
            context[key], sources[key] = fact.value, "receipt" if fact.source == "backend" else "user"
    if binding.status != "ready" and (receipt.get("fields") or {}).get("order_no"):
        receipt = {}
    order_no = params.get("order_no")
    if order_no and order_no != (receipt.get("fields") or {}).get("order_no"):
        receipt = {"fields": {"order_no": order_no}}
    if order_no:
        try:
            order = await services.backend.get_order(order_no)
            business = business.observe(
                "warranty.check", params, order.model_dump(mode="json"), state["input_id"]
            )
            if state.get("product_state") != "confirmed_sku":
                from app.sessions.cards import get_catalog

                product = get_catalog().get(order.sku)
                if product and product.in_scope:
                    product_update = {
                        "product_confirmed": product.to_candidate().model_dump(mode="json"),
                        "product_state": "confirmed_sku",
                        "category": product.category,
                    }
            if order.sku == (
                product_update.get("product_confirmed") or state.get("product_confirmed") or {}
            ).get("sku"):
                # The demo adapter verifies order facts; context card cannot alter them.
                facts = {
                    k: str(v) for k, v in order.model_dump(mode="json").items() if v is not None
                }
                receipt.update(
                    status="order_verified",
                    fields={**receipt.get("fields", {}), "order_no": order_no},
                    verified_facts=facts,
                )
            else:
                receipt.update(status="order_product_mismatch", verified_facts={})
        except BackendError as error:
            say(state, error.user_message)
    case = await services.cases.open(
        state["session_id"],
        state["active_issue_id"],
        product_update.get("product_confirmed") or state.get("product_confirmed") or {},
        (state.get("emotion") or {}).get("level") == "complaint_risk",
    )
    if not case.get("sku") and product_update.get("product_confirmed"):
        case = await services.cases.identify_product(case["case_id"], product_update["product_confirmed"])
    if order_no and receipt.get("status") == "order_verified":
        case = await services.cases.bind_order(case["case_id"], order_no)
    verified = receipt.get("verified_facts") or {}
    for key in CONTEXT_FIELDS:
        if verified.get(key):
            context[key], sources[key] = verified[key], "receipt"
    update = {
        "business_context": business.model_dump(mode="json"),
        **product_update,
        "case_id": case["case_id"],
        "case_order_no": (case.get("external_refs") or {}).get("order_no"),
        "service_context": context,
        "context_sources": sources,
        "receipt": receipt,
        "stage": "context",
        "escalate_reason": None,
    }
    emit_case(state, case)
    if binding.status == "ambiguous":
        say(state, "涉及多个订单，请明确要办理哪个订单号。")
        update.update(l3_route="commit_issue", pending_card=None)
        return update
    if not receipt or (
        receipt.get("status") in {None, "not_collected"}
        and not receipt.get("skipped_reason")
        and not order_no
    ):
        update.update(escalate_reason="R6", l3_route="prepare_receipt")
        return update
    missing = [key for key in ("region_purchase", "region_use", "channel") if not context.get(key)]
    if missing:
        labels = {"region_purchase": "购买地", "region_use": "使用地", "channel": "购买渠道"}
        vocabulary = services.policy_loader.load()["regions"]
        choices = {"region_purchase": vocabulary["regions"], "region_use": vocabulary["regions"], "channel": vocabulary["channels"]}
        say(state, "为核对适用政策，请补充" + "、".join(labels[key] for key in missing) + "。")
        update.update(
            pending_card=pending(
                state,
                "confirm_context",
                {"fields": missing, "prefilled": context, "sources": sources, "choices": choices},
            ),
            l3_route="await_input",
        )
    else:
        update["l3_route"] = "propose"
    return update


async def propose(state):
    services = require_services()
    decision = evaluate(state)
    writer()({"type": "progress", "stage": "propose"})
    excluded = set((state.get("proposal") or {}).get("excluded", []))
    options = []
    # 官方处置阶梯的顺序就是优先级：先寄配件，最后才谈退款。
    # 滚刷、滤网、耳塞套这类件换一个就好，之前只能提整机换货，成本与交付周期都差一个量级。
    for remedy in sorted(
        decision.remedies,
        key=lambda r: (
            REMEDY_LADDER.index(r.remedy) if r.remedy in REMEDY_LADDER else len(REMEDY_LADDER),
            not r.eligible,
        ),
    ):
        # Human review needs candidates and unmet conditions even when no policy
        # remedy is eligible. These candidates are not offered to the user until
        # approved, and can never pass the automatic policy gate.
        if (remedy.eligible or decision.needs_human) and remedy.remedy not in excluded and not any(o["option_id"] == remedy.remedy for o in options):
            options.append(
                {
                    "option_id": remedy.remedy,
                    "remedy": remedy.remedy,
                    "title": REMEDY_TITLES[remedy.remedy],
                    "cost_bearer": remedy.cost_bearer,
                    "conditions": [c.model_dump() for c in remedy.conditions],
                    "clauses": [c.model_dump() for c in remedy.clauses],
                    "auto_allowed": remedy.auto_allowed and remedy.eligible and not decision.needs_human,
                    "source": "policy",
                    "dispatch_estimate": services.executor.registry.dispatch_estimate("replacement.create") if remedy.remedy == "replace" else None,
                }
            )
    proposal = {
        "options": options,
        "status": "offered",
        "excluded": list(excluded),
        "chosen_option_id": None,
        "user_confirmed": False,
    }
    case = await services.cases.store.get(state["case_id"])
    if case["status"] not in {
        "open",
        "diagnosing",
        "proposing",
        "rejected",
        "reopened",
        "awaiting_confirmation",
        "tracking",
        "executing_failed",
    }:
        say(state, "案件正在等待处理，进度会在案件状态中更新。")
        return {"l3_route": "commit_issue"}
    case = await services.cases.transition(
        state["case_id"],
        "proposing",
        "政策方案已计算",
        policy_decision=decision.model_dump(mode="json"),
        proposal=proposal,
    )
    update = {
        "policy_decision": decision.model_dump(mode="json"),
        "proposal": proposal,
        "stage": "propose",
        "human_request_info": False,
        "escalate_reason": None,
    }
    if state.get("requested_remedy") in {"refund", "address_update"}:
        label = "退款" if state["requested_remedy"] == "refund" else "修改地址"
        say(
            state,
            f"已关联订单 {((state.get('receipt') or {}).get('fields') or {}).get('order_no', '')}。{label}需人工核实办理，当前未执行该操作。",
        )
        update["l3_route"] = "await_human"
    elif decision.needs_human:
        # Keep an explicit request as consent to the requested remedy, not arbitrary alternatives.
        if state.get("requested_remedy") == "replace":
            proposal.update(chosen_option_id="replace", user_confirmed=True)
        reasons = [c["text"] for hit in decision.exclusions_hit for c in hit.get("clauses", [])]
        say(
            state,
            "当前情况需要人工审核，暂不能自动办理。"
            + "；".join(reasons or decision.needs_human_reasons),
        )
        update["l3_route"] = "await_human"
    elif not options:
        say(state, "按当前售后政策，没有可直接办理的方案，我会整理资料交由人工核实。")
        case = await services.cases.transition(
            state["case_id"], "escalated_summary", "没有可办理方案，已整理人工接续摘要"
        )
        update.update(l3_route="summarize", escalate_reason="R6")
    else:
        case = await services.cases.transition(
            state["case_id"], "awaiting_confirmation", "等待用户选择方案", proposal=proposal
        )
        update.update(
            pending_card=pending(
                state,
                "confirm_proposal",
                {
                    "options": options,
                    "decision_summary": "依据演示政策计算，待真实 SOP 替换",
                    "policy_version": decision.policy_version,
                },
            ),
            l3_route="await_input",
        )
    for option in options:
        if not decision.needs_human:
            case = await services.cases.record_commitment(
                state["case_id"], option["title"] + "；费用承担：" + option["cost_bearer"], "clause"
            )
            if estimate := option.get("dispatch_estimate"):
                case = await services.cases.record_commitment(
                    state["case_id"],
                    f"预计创建服务单后 {estimate['working_days']} 个工作日发出，以办理回执为准",
                    "action_config", source_ref=f"{estimate['action']}@{estimate['actions_version']}",
                )
    emit_case(state, case)
    return update


async def authorize(state):
    services = require_services()
    case = await services.cases.store.get(state["case_id"])
    proposal = state.get("proposal") or {}
    option = next(
        (
            o
            for o in proposal.get("options", [])
            if o["option_id"] == proposal.get("chosen_option_id")
        ),
        {},
    )
    if not option or option.get("remedy") != "replace":
        say(state, "该方案需要人工办理，已提交审核。")
        return {"l3_route": "await_human"}
    decision = evaluate(state)
    key = f"{state['case_id']}:replacement.create:{option['option_id']}"
    old = await services.executor.store.get(key)
    case_order = (case.get("external_refs") or {}).get("order_no")
    receipt_order = ((state.get("receipt") or {}).get("fields") or {}).get("order_no")
    if old and old["status"] == "succeeded" and case_order in {None, receipt_order}:
        return {
            "l3_route": "execute",
            "execution_key": key,
            "gate_result": old["gate_result"],
            "policy_decision": decision.model_dump(mode="json"),
        }
    # A retry is the same application. Changed evidence/policy must produce a
    # fresh proposal, rather than reusing consent or a past human exception.
    retry_basis_unchanged = (case.get("policy_decision") or {}).get("trace_id") == decision.trace_id
    if case["status"] == "executing_failed" and not retry_basis_unchanged:
        say(state, "办理依据已发生变化，请重新核实并确认方案后办理。")
        return {"l3_route": "service_context", "human_decision_id": None}
    approved_id = state.get("human_decision_id")
    approved = next(
        (
            d
            for d in case["decisions"]
            if d["decision_id"] == approved_id
            and d["decision"] == "approve"
            and d.get("consumed_input_id") is not None
            and (case["status"] == "approved" or (case["status"] == "executing_failed" and retry_basis_unchanged))
            and (d.get("edited_proposal") or {}).get("option_id", d.get("option_id"))
            == option.get("option_id")
        ),
        None,
    )
    gate = AuthorizationGate().check(
        decision=decision,
        option=option,
        receipt=state.get("receipt") or {},
        product_state=state.get("product_state", "unknown"),
        risk_cases=state.get("risk_cases") or [],
        allowed_operations=(state.get("turn_decision") or {}).get("allowed_operations", False),
        user_confirmed=proposal.get("user_confirmed", False),
        case_status=case["status"],
        execution_status=old["status"] if old else None,
        human_approved=bool(approved),
        case_order_no=case_order,
    )
    await services.cases.transition(
        state["case_id"],
        case["status"],
        "授权门已检查",
        gate_result=gate.model_dump(),
        chosen_option_id=option["option_id"],
        proposal=proposal,
    )
    return {
        "gate_result": gate.model_dump(),
        "policy_decision": decision.model_dump(mode="json"),
        "execution_key": key,
        "l3_route": "execute" if gate.passed else "await_human",
    }


async def execute(state):
    from haike_contracts.common import GateResult

    services = require_services()
    writer()({"type": "progress", "stage": "execute"})
    case = await services.cases.store.get(state["case_id"])
    if (case.get("external_refs") or {}).get("order_no") not in {
        None, ((state.get("receipt") or {}).get("fields") or {}).get("order_no")
    }:
        say(state, "当前订单与案件不一致，已停止办理，请核实对应订单。")
        return {"l3_route": "await_human"}
    if case["status"] != "tracking":
        case = await services.cases.transition(
            state["case_id"], "executing", "已授权，正在创建服务单"
        )
    emit_case(state, case)
    receipt = state.get("receipt") or {}
    params = {
        "order_no": (receipt.get("fields") or {}).get("order_no"),
        "sku": state["product_confirmed"]["sku"],
        "reason_code": state["policy_decision"]["fault_class"],
        "evidence_ids": state.get("current_evidence_ids") or [],
    }
    try:
        result = await services.executor.run(
            "replacement.create",
            params,
            idempotency_key=state["execution_key"],
            session_id=state["session_id"],
            run_id=state["run_id"],
            case_id=state["case_id"],
            issue_id=state["active_issue_id"],
            gate_result=GateResult.model_validate(state["gate_result"]),
            policy_version=state["policy_decision"]["policy_version"],
            writer=writer(),
        )
    except ExecutionBusy:
        say(state, "相同申请仍在处理，请稍后查询案件状态。")
        return {"l3_route": "commit_issue"}
    writer()(
        {
            "type": "execution_card",
            "card_id": result.execution_id,
            "version": state["base_version"] + 1,
            "execution_id": result.execution_id,
            "action_kind": "replacement.create",
            "status": result.status,
            "receipt": result.receipt.model_dump(mode="json"),
            "idempotency_key": state["execution_key"],
        }
    )
    execution = {
        "execution_id": result.execution_id,
        "status": result.status,
        "receipt": result.receipt.model_dump(mode="json"),
        "idempotency_key": state["execution_key"],
        "action_kind": "replacement.create",
    }
    if result.status != "succeeded":
        say(state, result.receipt.next_step)
        if result.recoverable:
            case = await services.cases.transition(state["case_id"], "executing_failed", "业务系统暂时不可用，可重试原申请")
            emit_case(state, case)
            proposal = dict(state["proposal"])
            selected = next(o for o in proposal["options"] if o["option_id"] == proposal["chosen_option_id"])
            proposal.update(status="offered", chosen_option_id=None, user_confirmed=False)
            say(state, "本次办理暂未完成。您可以重试原申请，或转人工协助；重试不会重复创建服务单。")
            return {
                "execution": execution, "case_status": case["status"], "proposal": proposal,
                "stage": "propose",
                "pending_card": pending(state, "confirm_proposal", {
                    "options": [selected], "retry": True,
                    "decision_summary": "业务系统暂时不可用，请重试原申请或选择人工协助。",
                    "policy_version": state["policy_decision"]["policy_version"],
                }),
                "l3_route": "await_input",
            }
        return {"execution": execution, "l3_route": "await_human"}
    case = await services.cases.attach_execution(state["case_id"], execution["receipt"])
    case = await services.cases.record_commitment(
        state["case_id"], execution["receipt"]["next_step"], "receipt"
    )
    emit_case(state, case)
    return {
        "business_context": BusinessContext.restore(state)
        .observe("replacement.create", params, execution["receipt"], state["input_id"])
        .model_dump(mode="json"),
        "execution": execution,
        "stage": "track",
        "prior_remedies": list(dict.fromkeys([*state.get("prior_remedies", []), "replace"])),
        "l3_route": "track",
    }


async def track(state):
    services = require_services()
    case = await services.cases.store.get(state["case_id"])
    external_status = None
    number = case.get("external_refs", {}).get("service_order_no")
    if number:
        try:
            order = await services.backend.get_service_order(number)
            external_status = order.status
            say(state, f"服务单 {number} 当前状态：{order.status}。来源：售后系统（模拟）。")
        except BackendError as error:
            say(state, error.user_message)
    if (state.get("turn_decision") or {}).get("primary_intent") == "confirm_received":
        if external_status in {"shipped", "completed", "delivered"}:
            case = await services.cases.close(
                state["case_id"], user_confirmed=True, external_status=external_status
            )
            emit_case(state, case)
        else:
            say(state, "系统暂未确认发货或完成，案件继续跟踪，待状态核实后结案。")
    return {
        "stage": "done" if case["status"] == "closed" else "track",
        "pending_card": pending(state, "rate_satisfaction", {"case_id": state["case_id"]}),
        "l3_route": "advance_tasks",
        "completed_task_intent": "replacement_request",
    }


async def await_human(state):
    services = require_services()
    row = await services.cases.transition(
        state["case_id"],
        "awaiting_approval",
        "需要人工审核",
        policy_decision=state.get("policy_decision"),
        proposal=state.get("proposal"),
        gate_result=state.get("gate_result"),
        complaint_risk=(state.get("emotion") or {}).get("level") == "complaint_risk",
        priority="high"
        if (state.get("emotion") or {}).get("level") == "complaint_risk"
        else "normal",
    )
    emit_case(state, row)
    say(state, "已提交人工审核。审核决定会回到本会话，您可以继续补充信息。")
    return {"stage": "awaiting_human", "pending_card": None, "l3_route": "commit_issue"}


async def consult(state):
    from app.conversation.answers import (
        AnswerRequest,
        conversation_view,
        render_answer,
        request_of,
        required_reads,
    )

    services = require_services()
    decision = state.get("turn_decision") or {}
    intent = decision.get("primary_intent")
    if intent not in CONSULT_INTENTS:
        intent = state.get("consult_intent") or intent
    request = request_of(state)
    scope = decision.get("answer_scope", "focus")
    if request is None:
        fields = {
            "logistics_query": ["order_no", "tracking_no", "service_order_no", "logistics_status", "updated_at"],
            "order_query": ["order_no", "sku", "purchase_date", "channel", "platform"],
            "warranty_query": ["purchase_date", "warranty_end"],
        }.get(intent, ["order_no"])
        request = AnswerRequest(fields=fields, quote=state.get("text", ""))
    business = BusinessContext.restore(state)
    workflow = business.for_order(state["case_order_no"]) if scope in {"case", "issue"} and state.get("case_order_no") else business
    business.subjects.update(workflow.subjects)
    view = conversation_view(state, scope)
    reads = required_reads(request, view)
    if intent == "logistics_query" and not decision.get("answer_request"):
        reads = ["logistics.query"]
    if view["status"] == "ambiguous":
        reads = reads or ["warranty.check"]
    for kind in reads:
        binding = workflow.bind(kind)
        if binding.status != "ready":
            attempts = (state.get("consult_attempts") or 0) + 1
            say(state, "涉及多个订单，请明确要查询哪个订单号。" if binding.status == "ambiguous" else "请提供订单号或物流单号，我会直接查询。" if kind == "logistics.query" else "查询这项订单信息还需要订单号。")
            return {
                "consult_intent": intent, "consult_attempts": attempts,
                "stage": state.get("stage", "consult") if state.get("pending_card") else "consult",
                "l3_route": "commit_issue" if attempts < 3 else "summarize",
                "escalate_reason": None if attempts < 3 else "R7",
            }
        params = binding.params
        writer()({"type": "progress", "stage": "consult"})
        key = f"{state['session_id']}:{state['input_id']}:{kind}:" + hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]
        result = await services.executor.run(
            kind, params, idempotency_key=key, session_id=state["session_id"],
            run_id=state["run_id"], issue_id=state["active_issue_id"], writer=writer(),
        )
        if result.status != "succeeded":
            say(state, result.receipt.next_step)
            return {"business_context": business.model_dump(mode="json"), "consult_intent": intent, "l3_route": "commit_issue"}
        business = business.observe(kind, params, result.receipt.model_dump(mode="json"), state["input_id"])
        workflow = business.for_order(state["case_order_no"]) if scope in {"case", "issue"} and state.get("case_order_no") else business
    view = conversation_view({**state, "business_context": business.model_dump(mode="json")}, scope)
    case_update = {}
    if "case_status" in request.fields and state.get("case_id") and (view["issue_matches_focus"] or scope in {"case", "issue"}):
        case = await services.cases.store.get(state["case_id"])
        if case:
            case_update["case_status"] = case["status"]
            view["fields"]["case_status"] = {"value": case["status"], "source": "case"}
    if "warranty_end" in request.fields:
        facts = {key: fact["value"] for key, fact in view["fields"].items()}
        if facts.get("purchase_date") and facts.get("sku"):
            value = PolicyInput(
                sku=facts["sku"],
                category=state.get("category") or (state.get("product_confirmed") or {}).get("category"),
                region_purchase=facts.get("region_purchase"),
                region_use=facts.get("region_use") or facts.get("region_purchase"),
                channel=facts.get("channel"), platform=facts.get("platform"),
                purchase_date=facts["purchase_date"], receipt_status="order_verified",
                today=date.fromisoformat(state["at"][:10]), fault_class="unknown",
            )
            policy = PolicyEngine(services.policy_loader.load()).decide(value)
            view["fields"]["warranty_end"] = {"value": policy.warranty_end or "需人工核实", "source": "policy"}
            clauses = list(dict.fromkeys(c.clause_id for r in policy.remedies for c in r.clauses))
            policy_note = f"\n具体退换修资格还需核实使用地和故障情况。依据：{'、'.join(clauses)}；政策版本 {policy.policy_version}。"
        else:
            policy_note = ""
    else:
        policy_note = ""
    say(state, render_answer(request, view) + policy_note)
    return {
        **case_update,
        "business_context": business.model_dump(mode="json"),
        "stage": state.get("stage", "done") if state.get("pending_card") or state.get("case_id") else "done",
        "consult_intent": None, "consult_attempts": 0,
        "consult_answered": not state.get("pending_card"),
        "completed_task_intent": intent, "l3_route": "advance_tasks",
    }


async def apply_l3_action(state, action, pc):
    payload = action.get("payload") or {}
    kind = action["kind"]
    results = dict(state.get("card_results") or {})
    update = {"pending_card": None, "last_action": None, "escalate_reason": None}
    if kind == "confirm_context":
        context = dict(state.get("service_context") or {})
        sources = dict(state.get("context_sources") or {})
        for key, value in payload.items():
            if value and sources.get(key) != "receipt":
                context[key], sources[key] = value, "user"
        results[pc["card_id"]] = {"confirmed_fields": context}
        business = BusinessContext.restore(state).remember(
            payload, state["input_id"], order_no=state.get("case_order_no")
        )
        update.update(service_context=context, context_sources=sources, business_context=business.model_dump(mode="json"), l3_route="service_context")
    elif kind == "confirm_proposal":
        proposal = {
            **state["proposal"],
            "chosen_option_id": payload["option_id"],
            "status": "confirmed",
            "user_confirmed": True,
        }
        results[pc["card_id"]] = {"chosen_option_id": payload["option_id"]}
        update.update(proposal=proposal, l3_route="authorize")
    elif kind == "decline_proposal":
        results[pc["card_id"]] = {"declined_reason": payload["reason"]}
        proposal = dict(state["proposal"])
        if payload["reason"] == "want_other":
            first = next(iter(proposal.get("options", [])), {})
            proposal["excluded"] = [*proposal.get("excluded", []), first.get("remedy")]
        update.update(
            proposal=proposal,
            l3_route={
                "want_other": "propose",
                "not_now": "commit_issue",
                "request_human": "await_human",
            }[payload["reason"]],
        )
    elif kind == "rate_satisfaction":
        await require_services().cases.rate(
            state["session_id"],
            state["active_issue_id"],
            payload["score"],
            payload.get("comment"),
            state.get("case_id"),
        )
        results[pc["card_id"]] = {"score": payload["score"]}
        say(state, "感谢您的评价，案件进度可随时查询。")
        update["l3_route"] = "commit_issue"
    elif kind == "skip_retake":
        results[pc["card_id"]] = {"skipped": True}
        update.update(retake_skipped=True, l3_route="retrieve")
    update["card_results"] = results
    return update


def route(state):
    return state.get("l3_route") or "commit_issue"


async def understand_human(state):
    from copy import deepcopy

    from app.conversation.reduce import ISSUE_FIELDS

    source = state.get("last_action") or {}
    row = await require_services().cases.store.get(source["case_id"])
    if row["session_id"] != state["session_id"] or row["issue_id"] != source.get("target_issue_id"):
        raise ValueError("审批输入与案件不匹配")
    decision = next(
        (d for d in row["decisions"] if d["decision_id"] == source.get("decision_id")), None
    )
    if decision is None and state.get("entry") != "case_command":
        raise ValueError("审批决定不存在")
    issues = deepcopy(state.get("issues") or {})
    if row["issue_id"] not in issues:
        raise ValueError("案件问题已不可恢复")
    if state.get("active_issue_id") in issues:
        issues[state["active_issue_id"]].update(
            {k: deepcopy(state.get(k, v)) for k, v in ISSUE_FIELDS.items()}
        )
    issue = issues[row["issue_id"]]
    update = {k: deepcopy(issue.get(k, v)) for k, v in ISSUE_FIELDS.items()}
    allowed = not any(
        r.get("status") == "reported" and r.get("rule_id") == "R4"
        for r in state.get("risk_cases", [])
    )
    update.update(
        active_issue_id=row["issue_id"],
        issues=issues,
        human_decision_id=decision["decision_id"] if decision else None,
        case_id=row["case_id"],
        l3_route=None,
        turn_decision={
            "primary_intent": state["entry"],
            "allowed_operations": allowed,
            "reply_mode": "business",
            "pending_changes": [],
        },
    )
    writer()(
        {
            "type": "issue_changed",
            "active_issue_id": row["issue_id"],
            "issues": [
                {"issue_id": k, "title": v.get("title", ""), "status": v.get("status", "open")}
                for k, v in issues.items()
            ],
            "input_id": state["input_id"],
            "resolved_issue_id": row["issue_id"],
            "version": state["base_version"] + 1,
        }
    )
    return update


async def reopening_request(state, meaning):
    """Bind a current unresolved report to the existing case before routing it."""
    if state.get("entry") != "message" or not state.get("case_id"):
        return None
    decision = state.get("turn_decision") or {}
    if decision.get("business_ambiguous") or decision.get("primary_intent") not in {
        "report_problem", "step_feedback", "answer_pending", "correct", "complaint",
        "unknown", "replacement_request", "refund_request",
    }:
        return None
    text = state.get("text", "")
    quotes = [meaning.unresolved_quote]
    if meaning.feedback == "not_solved":
        quotes.append(meaning.feedback_quote)
    if meaning.primary_intent == "report_problem":
        quotes.extend(f.quote for f in meaning.facts if f.kind in {"symptom", "observation"})
    quote = next((q for q in quotes if q and q.strip() and q in text), None)
    if not quote:
        return None
    row = await require_services().cases.store.get(state["case_id"])
    if row["session_id"] != state["session_id"] or row["issue_id"] != state["active_issue_id"]:
        raise ValueError("案件不属于当前问题")
    if row["status"] not in {"closed", "closed_unresolved", "escalated_summary", "reopened"}:
        return None
    business = BusinessContext.restore(state)
    binding = business.bind("warranty.check")
    order_no = row.get("external_refs", {}).get("order_no")
    scope = decision.get("answer_scope")
    if scope not in {"case", "issue"} and (
        business.status == "ambiguous" or (order_no and binding.params.get("order_no") not in {None, order_no})
        or (meaning.business_reference and meaning.business_reference.relation == "other")
    ):
        return {"clarification": "请确认仍未解决的是原售后案件的问题，还是刚查询的另一笔订单的问题。"}
    return {"case_id": row["case_id"], "expected_revision": row["revision"], "quote": quote,
            "transition": row["status"] != "reopened"}


def inactive_case_state(state):
    proposal = dict(state.get("proposal") or {})
    if proposal:
        proposal.update(user_confirmed=False, chosen_option_id=None, status="inactive")
    return {"pending_card": None, "last_action": None, "proposal": proposal,
            "human_request_info": False, "human_decision_id": None, "requested_remedy": None}


async def reopen_case(state):
    request = state["turn_decision"]["reopen_request"]
    services = require_services()
    row = await services.cases.reopen(state["case_id"], expected_revision=request["expected_revision"],
                                     input_id=state["input_id"], quote=request["quote"]) if request["transition"] else await services.cases.store.get(state["case_id"])
    pc = state.get("pending_card")
    if pc:
        writer()({"type": "pending_changed", "issue_id": state["active_issue_id"],
                  "pending_id": pc["card_id"], "status": "invalidated", "reason": "case_reopened",
                  "version": state["base_version"] + 1})
    emit_case(state, row, "继续处理未解决的问题")
    say(state, "已恢复原案件，保留之前的订单和处理记录。接下来重新核实适用方案。")
    intent = state["turn_decision"]["primary_intent"]
    return {**inactive_case_state(state), "case_status": row["status"],
            "requested_remedy": {"replacement_request": "replace", "refund_request": "refund"}.get(intent),
            "l3_route": "escalate" if state["turn_decision"].get("escalation_trigger") else "service_context"}


async def apply_case_command(state):
    source = state["last_action"]
    row = await require_services().cases.manual_action(
        state["case_id"], source["command"], command_id=state["input_id"],
        actor=source["actor"], expected_revision=source["expected_revision"],
    )
    pc = state.get("pending_card")
    if pc:
        writer()({"type": "pending_changed", "issue_id": state["active_issue_id"],
                  "pending_id": pc["card_id"], "status": "invalidated",
                  "reason": "case_" + source["command"], "version": state["base_version"] + 1})
    emit_case(state, row, "人工结案" if source["command"] == "close" else "人工重新受理")
    say(state, "人工已将此案件结案，您仍可查询历史记录；如问题仍在，请继续说明。" if source["command"] == "close" else "人工已重新受理此案件，请说明仍需处理的问题。后续办理将重新核实方案并征求您的确认。")
    return {**inactive_case_state(state), "case_status": row["status"], "stage": "done",
            "l3_route": "commit_issue"}


async def apply_human_decision(state):
    services = require_services()
    row = await services.cases.consume_decision(
        state["case_id"], state["human_decision_id"], state["input_id"]
    )
    decision = next(d for d in row["decisions"] if d["decision_id"] == state["human_decision_id"])
    proposal = dict(row.get("proposal") or state.get("proposal") or {})
    emit_case(state, row)
    say(state, "人工审核回复：" + decision["note"])
    if decision["decision"] == "approve":
        options = list(proposal.get("options", []))
        chosen = decision.get("edited_proposal") or next(
            (o for o in options if o["option_id"] == decision.get("option_id")), None
        )
        if not chosen:
            raise ValueError("批准方案不存在")
        chosen = {**chosen, "source": "human"}
        options = [o for o in options if o["option_id"] != chosen["option_id"]] + [chosen]
        consent = (
            proposal.get("user_confirmed", False)
            and proposal.get("chosen_option_id") == chosen["option_id"]
            and not decision.get("edited_proposal")
        )
        # Explicit replacement requests authorize that remedy only. Edited cost/terms require a fresh card.
        if (
            state.get("requested_remedy") == "replace"
            and chosen["remedy"] == "replace"
            and not decision.get("edited_proposal")
        ):
            consent = True
        proposal.update(
            options=options,
            chosen_option_id=chosen["option_id"],
            user_confirmed=consent,
            status="confirmed" if consent else "offered",
        )
        if not consent:
            await services.cases.record_commitment(
                state["case_id"], chosen["title"] + "；费用承担：" + (chosen.get("cost_bearer") or "待核实"),
                "human_decision", source_ref=decision["decision_id"],
            )
            say(state, "人工已审核，请确认最终方案后办理。")
            return {
                "proposal": proposal,
                "stage": "propose",
                "human_request_info": False,
                "pending_card": pending(
                    state,
                    "confirm_proposal",
                    {
                        "options": [chosen],
                        "decision_summary": "人工审核后的方案，请确认",
                        "policy_version": (state.get("policy_decision") or {}).get(
                            "policy_version", "human"
                        ),
                    },
                ),
                "l3_route": "await_input",
            }
        return {"proposal": proposal, "human_request_info": False, "l3_route": "authorize"}
    if decision["decision"] == "reject":
        proposal["excluded"] = list(
            dict.fromkeys([*proposal.get("excluded", []), decision.get("option_id") or "replace"])
        )
        return {"proposal": proposal, "l3_route": "propose"}
    return {
        "stage": "context",
        "human_request_info": True,
        "pending_card": None,
        "l3_route": "commit_issue",
    }


async def prepare_retake(state):
    count = (state.get("retake_attempts") or 0) + 1
    if count > 2:
        say(state, "照片仍无法辨认，我会整理资料交由人工核实。")
        return {
            "retake_attempts": count,
            "pending_card": None,
            "escalate_reason": "R7",
            "l3_route": "summarize",
        }
    quality = state.get("image_quality") or {}
    return {
        "retake_attempts": count,
        "clarification": {"reason": "image", "attempts": count, "asked_run_id": state["run_id"]},
        "pending_card": pending(
            state,
            "upload_retake",
            {
                "reasons": quality.get("reasons", []),
                "guidance": quality.get("guidance", []) or ["请对焦拍摄设备的故障部件。"],
            },
        ),
        "l3_route": "await_input",
    }


async def vision_conflict(state):
    say(
        state,
        "图片与文字描述存在差异，请确认："
        + "；".join((state.get("fault_localization") or {}).get("conflicts_with_text", [])),
    )
    return {
        "pending_card": None,
        "clarification": {"reason": "conflict", "attempts": 1, "asked_run_id": state["run_id"]},
    }


async def advance_tasks(state):
    from app.conversation.tasks import LABELS, next_task, task_business

    completed = state.get("completed_task_intent") or "report_problem"
    business = BusinessContext.restore(state)
    decision = state.get("turn_decision") or {}
    completed_business = business.for_order(state["case_order_no"]) if state.get("case_order_no") and (decision.get("answer_scope") in {"case", "issue"} or completed in {"replacement_request", "refund_request", "address_update"}) else business
    tasks, task = next_task(state.get("task_queue") or [], completed, business=completed_business, task_id=decision.get("task_id"))
    update = {"task_queue": tasks, "completed_task_intent": None}
    if task:
        say(state, "接下来处理：" + LABELS[task["intent"]] + "。")
        update.update(
            text=task["quote"],
            business_context=task_business(task, business).model_dump(mode="json"),
            turn_decision={**state.get("turn_decision", {}), "primary_intent": task["intent"], "secondary_intents": [], "task_id": task["task_id"], "answer_request": None, "answer_scope": "focus", "clarification": None},
            l3_route="consult"
            if task["intent"] in CONSULT_INTENTS
            else "await_input"
            if task["intent"] == "report_problem" and state.get("pending_card")
            else "disambiguate"
            if task["intent"] == "report_problem"
            else "service_context",
        )
        if task["intent"] in {"replacement_request", "refund_request", "address_update"}:
            update["requested_remedy"] = {"replacement_request": "replace", "refund_request": "refund", "address_update": "address_update"}[task["intent"]]
        writer()(
            {
                "type": "issue_changed",
                "active_issue_id": state["active_issue_id"],
                "issues": [
                    {
                        "issue_id": key,
                        "title": issue.get("title", ""),
                        "status": issue.get("status", "open"),
                        "task_queue": tasks
                        if key == state["active_issue_id"]
                        else issue.get("task_queue", []),
                    }
                    for key, issue in state["issues"].items()
                ],
                "input_id": state["input_id"],
                "resolved_issue_id": state["active_issue_id"],
                "version": state["base_version"] + 1,
            }
        )
    else:
        update["l3_route"] = "await_input" if state.get("pending_card") else "commit_issue"
        if (
            state.get("stage") == "done"
            and not state.get("case_id")
            and not state.get("consult_answered")
            and not state.get("pending_card")
        ):
            update.update(
                pending_card=pending(state, "rate_satisfaction", {"case_id": None}),
                l3_route="await_input",
            )
    return update
