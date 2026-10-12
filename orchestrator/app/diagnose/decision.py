"""Issue-local symptom evidence and next-move decisions.

Facts are the inputs: a described symptom or an error code goes to the official Q&A retrieval;
with neither, ask once for the symptom.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.conversation.operation_conditions import (
    BURDEN_SKIP_LIMIT,
    answered_history,
    conditions_for,
    effective_exhausted,
    execution_history,
    resource_recheck,
    step_unavailable,
    support_question,
)
from app.guide.verify import unanswered


def _active_facts(issue):
    return [
        f
        for f in issue.get("facts", [])
        if f.get("status") == "active" and f.get("kind") == "symptom"
    ]


@dataclass(frozen=True)
class DiagnosticDecision:
    outcome: Literal["continue", "clarify", "escalate"]
    reason: str
    source_refs: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()

    def snapshot(self, state):
        return {
            **asdict(self),
            "issue_id": state.get("active_issue_id"),
            "input_id": state.get("input_id"),
        }


RETRYABLE_HANDOFF = {"R5", "R7"}  # 交接原因是「没有官方指引」或「追问后仍不明」：客户补了信息，排障可能重新可行


def retry_after_handoff(state) -> bool:
    """等人工审核期间客户补了新的具体现象或产品身份，是否回到排障（T60 方案 A）。

    只在交接原因是缺指引 / 缺信息、人工还没作出决定、本轮确实带来新的事实时重试。客户要求人工（R3）、
    安全（R4）、质保与订单类交接都不撤回：那些交接的原因不会因为多一条现象而消失。"""
    decision = state.get("turn_decision") or {}
    if (state.get("stage") != "awaiting_human" or state.get("case_status") != "awaiting_approval"
            or state.get("human_decision_id") or state.get("requested_remedy")):
        return False
    if (state.get("diagnose_outcome") or {}).get("reason") not in RETRYABLE_HANDOFF and state.get("escalate_reason") not in RETRYABLE_HANDOFF:
        return False
    if not decision.get("allowed_operations", True) or decision.get("escalation_trigger"):
        return False
    issue = (state.get("issues") or {}).get(state.get("active_issue_id"), {})
    added = {p["fact_id"] for p in decision.get("patches") or [] if p.get("op") in {"add", "replace"}}
    new_symptom = any(f["fact_id"] in added and concrete(f) for f in _active_facts(issue))
    return new_symptom or bool(decision.get("product_answered"))


def described(state, issue) -> bool:
    """本问题已有可检索的现象：模型抽取的现象事实、intake 现象、或消息里的错误码 / 结构化问题描述。"""
    from app.official.message import parse_message

    if _active_facts(issue) or state.get("error_codes") or [s for s in state.get("symptoms") or [] if str(s).strip()]:
        return True
    text = state.get("text") or ""
    parsed = parse_message(text)
    if parsed.codes or (parsed.description and len(parsed.description.strip()) >= 6):
        return True
    # 自由文本：去掉型号名后仍有足够的话（≥ 6 个词或 12 个汉字），就交给检索判断有没有对应的官方说明。
    # 63 单实测：「omni c20 isn't following my schedule」「detergent level has barely moved」模型没抽出现象事实，
    # 被当成「无现象」追问，客户已经说清的问题又被问一遍（T40 / T61）。
    rest = re.sub(r"\b(T\d{4}|T8D\d{2}|omni\s*[A-Za-z0-9]+|s1\s*pro|x10\s*pro|solocam\s*[A-Za-z0-9]+|eufy|anker)\b", " ", text, flags=re.IGNORECASE)
    words = re.findall(r"[A-Za-zÀ-ÿ']+", rest)
    return len(words) >= 6 or len(re.findall(r"[一-鿿]", rest)) >= 12


def parse_codes(text: str) -> tuple[str, ...]:
    from app.official.message import parse_message

    return parse_message(text).codes


# 「I just want my hoover to clean」：客户在说想要什么结果，不是设备在做什么。这是愿望句式（一小类语法结构），
# 不是现象词表；模型有时改写成「not cleaning properly」，有时原样抄成现象（T60 复跑两种都出现）。
WISH = re.compile(r"\b(?:i|we)\s+(?:just\s+|only\s+|really\s+)?(?:want|wish|would like|need)\b[^.!?]*\bto\b"
                  r"|我(?:只|就)?(?:想|希望|要)(?:让)?它", re.IGNORECASE)
# 引文去掉情绪词后只剩这些词（指代整机 / 系动词 / 语气），说的是客户的评价，不是设备在做什么
_EVALUATION_REST = {
    "you", "your", "you're", "youre", "re", "my", "the", "this", "these", "that", "it", "its", "it's", "is", "are", "was",
    "were", "so", "really", "very", "just", "all", "they", "them", "a", "an", "and", "of", "eufy", "anker",
    "device", "devices", "machine", "machines", "product", "products", "thing", "things", "robot", "robots",
    "vacuum", "vacuums", "pump", "pumps", "camera", "cameras", "了", "的", "啊", "吧", "呢", "这个", "东西", "机器", "产品",
}


def evaluation_only(fact: dict) -> bool:
    """引文只有情绪 / 评价词（「cameras suck」「太烂了」）：客户在表达不满，没说设备在做什么。
    情绪词用情绪分级的同一份词表（config/rules/complaint_terms.yaml），不另立现象词表。"""
    from app.emotion.policy import emotion_terms, term_hit

    quote = fact.get("quote") or ""
    hits = [word for word in emotion_terms() if term_hit(word, quote)]
    if not hits:
        return False
    rest = quote.casefold()
    for word in sorted(hits, key=len, reverse=True):
        rest = re.sub(rf"(?<![\w]){re.escape(word.casefold())}(?![\w])" if word.isascii() else re.escape(word), " ", rest)
    subject = set(re.findall(r"[^\W\d_]+", (fact.get("subject") or "").casefold()))
    words = re.findall(r"[a-zà-ÿ']+", rest)
    # 汉字没有词边界：去掉指代与语气字串后看还剩什么
    han = "".join(re.findall(r"[一-鿿]+", rest))
    for filler in sorted((w for w in _EVALUATION_REST if not w.isascii()), key=len, reverse=True):
        han = han.replace(filler, "")
    return not han and not [w for w in words if w not in _EVALUATION_REST and w not in subject]


def concrete(fact: dict) -> bool:
    """客户原话支持的具体现象：引文不是一句愿望，也不只是评价。模型对现象的正常归纳（「going off 2 hours before」→
    「starts two hours early」）不算改写，不按词面比对。T58「You're fucking cameras suck」被抽成现象 poor quality，
    据此选了画质指南；评价不是现象，交给症状追问。"""
    return not WISH.search(fact.get("quote") or "") and not evaluation_only(fact)


def missing_for_retrieval(state, issue=None) -> list[str]:
    """检索落空时，输入还缺什么：product（型号未确认）/ symptoms（没有客户原话支持的具体现象）。
    空列表 = 已问清仍查不到，是知识缺失；非空 = 信息不足，先问再交接（T60）。错误码本身就是具体现象。"""
    issue = issue if issue is not None else (state.get("issues") or {}).get(state.get("active_issue_id"), {})
    missing = []
    if state.get("product_state") != "confirmed_sku":
        missing.append("product")
    facts = [f for f in _active_facts(issue) if f.get("polarity", "affirmed") == "affirmed" and concrete(f)]
    if not (facts or state.get("error_codes") or parse_codes(state.get("text") or "")):
        missing.append("symptoms")
    return missing


def fact_codes(state) -> list[str]:
    """本问题症状事实上的码。只有照片签名写的症状事实带码：签名命中的官方 Q&A 标题里的错误码。"""
    issue = (state.get("issues") or {}).get(state.get("active_issue_id"), {})
    return list(dict.fromkeys(code for f in _active_facts(issue) for code in f.get("symptom_codes", [])))


def decide_symptoms(state) -> DiagnosticDecision:
    issue = (state.get("issues") or {}).get(state.get("active_issue_id"), {})
    refs = tuple(dict.fromkeys(ref for f in _active_facts(issue) for ref in f.get("source_entry_ids", [])))
    if not (state.get("turn_decision") or {}).get("allowed_operations", True):
        return DiagnosticDecision("escalate", "safety_restriction", refs)
    if described(state, issue):
        # 官方 Q&A 是英文、客户多语言：现象不必先归类，有描述或错误码就交给检索。
        return DiagnosticDecision("continue", "symptom_described", refs)
    # 没有任何现象描述也没有错误码：问一次现象（开放问题，可贴错误码）。
    return DiagnosticDecision("clarify", "symptom_missing", refs, ("故障现象或 App 错误码",))


def owns_diagnostic_reply(state):
    """Physical advice always uses published plan content, including conversational detours."""
    issue = (state.get("issues") or {}).get(state.get("active_issue_id"), {})
    return bool(
        _active_facts(issue)
        or state.get("symptoms")
        or state.get("plan_cursor")
    )


def explanation(state):
    decision = state.get("turn_decision") or {}
    if not decision.get("allowed_operations", True):
        return "There's an unconfirmed safety concern with this device, so please stop using and charging it. We can review the record or I can prepare it for our support team."
    step = ((state.get("pending_card") or {}).get("payload") or {}).get("step")
    if step:
        caution = f" Note: {step['caution']}" if step.get("caution") else ""
        return (
            f"The current step is: {step['instruction']}{caution} "
            "Asking about it doesn't mark it as done; please tell me the result after trying it, "
            "or choose \"can't do it\" on the card."
        )
    if state.get("stage") == "done":
        if (state.get("diagnose_outcome") or {}).get("mode") == "explained":
            return "The official explanation has been provided; this does not mark the device as repaired. If it doesn't match what you're seeing, describe the difference so we can review it."
        if state.get("case_status") == "closed_unresolved":
            return "This case is closed, but the problem is not resolved. No new service request has been submitted. Please describe any new information if you need further help."
        if state.get("case_id"):
            return "This case has been closed. If the problem persists, please describe what is happening so we can review the case."
        return "This issue was marked as resolved. If it comes back, describe what's happening and I'll check the right guidance again."
    if state.get("case_id") and state.get("case_status") == "awaiting_approval":
        # 已在人工队列：不再承诺「我去查官方资料」——这一轮不会去查（T60）
        return "Your case is with a support colleague. Anything you add here goes into the case; describe what the device is doing and I'll include it."
    if state.get("exhausted_plans"):
        return "The applicable troubleshooting steps have been tried and it isn't resolved yet. I can prepare the steps you tried for our support team; I won't repeat steps you've already done."
    return "There's no troubleshooting step to give yet. Tell me more about the problem (or the error code shown in the app) and I'll check the official guidance; if none applies, I'll say so."


# ---------------- 依据反馈与操作条件做下一次决策（design §3.2–§3.3） ----------------

SWITCH_CONFIDENCE = 0.3
# 对外兼容 / 观测层的规则码映射；真实原因在 NextAction.reason
COMPAT_RULE = {
    "safety_stop": "R4",
    "handoff_offer": "R2",
}
HANDOFF_RULE_BY_REASON = {"user_requested_human": "R3", "safety_risk": "R4", "guide_exhausted": "R1"}
# 主办方 SOP：排障后仍未解决 → 确认是否进入换货 / 退款。一条官方 Q&A 指南走完仍未解决就进入质保判断，
# 不再换下一条相近的指南（实测 T55 / T29 会连走 3 条指南、7 步以上才停）。
MAX_GUIDES = 1


@dataclass(frozen=True)
class NextAction:
    """同一问题的下一动作。函数只返回决策，不调模型、不写库、不发事件。"""

    kind: Literal["ask", "step", "resolved", "handoff_offer", "safety_stop", "pause"]
    reason: str
    plan_cursor: dict[str, Any] | None = None
    question: dict[str, Any] | None = None
    basis: tuple[str, ...] = ()
    trace: dict[str, Any] = field(default_factory=dict)

    @property
    def compat_rule(self) -> str | None:
        if self.kind == "handoff_offer":
            return HANDOFF_RULE_BY_REASON.get(self.reason, "R2")
        return COMPAT_RULE.get(self.kind)

    def snapshot(self, state) -> dict[str, Any]:
        value = asdict(self)
        return {
            **value,
            "compat_rule": self.compat_rule,
            "issue_id": state.get("active_issue_id"),
            "input_id": state.get("input_id"),
            "issue_revision": ((state.get("issues") or {}).get(state.get("active_issue_id")) or {}).get(
                "issue_revision"
            ),
        }


def _first_open_step(plan, executed_src: set[str], executed_steps: set[tuple[str, str]], state=None):
    """重放已答节点的出边，查找所选分支中的未执行步骤；数组位置不代表执行顺序。"""
    skipped = []
    answered = {s.get("instruction_src"): s for s in answered_history(state or {})}
    step_id = plan.first_step().step_id
    visited = set()
    while step_id not in {"DONE", "EXHAUSTED"} and step_id not in visited:
        visited.add(step_id)
        step = plan.step(step_id)
        recorded = answered.get(step.instruction_src) or {}
        nxt = plan.next_step_id(step_id, "not_solved", option=(recorded.get("answer") or {}).get("option"))
        unavailable = step_unavailable(state or {}, plan.plan_id, step)
        if unavailable:
            skipped.append({"plan_id": plan.plan_id, "step_id": step.step_id, "reason": unavailable})
            step_id = nxt
            continue
        if (plan.plan_id, step.step_id) in executed_steps:
            skipped.append({"plan_id": plan.plan_id, "step_id": step.step_id, "reason": "already_executed"})
            step_id = nxt
            continue
        if step.instruction_src in executed_src:
            skipped.append({"plan_id": plan.plan_id, "step_id": step.step_id, "reason": "duplicate_instruction_src"})
            step_id = nxt
            continue
        return step, skipped
    return None, skipped


def replay_end(library, plan_id: str, state) -> str:
    """沿已回答的边重放计划，看它停在哪儿：handoff = 走到官方交售后结论段；question_exit = 选中了审核写成
    EXHAUSTED 的选项（诊断树里原文没覆盖的那一支）；open = 其余（有未回答的步骤，或步骤走完）。"""
    try:
        plan = library.get(plan_id)
    except KeyError:
        return "open"
    answered = {s.get("instruction_src"): s for s in answered_history(state)}
    step_id, seen = plan.first_step().step_id, set()
    while step_id not in {"DONE", "EXHAUSTED"} and step_id not in seen:
        seen.add(step_id)
        step = plan.step(step_id)
        if step.kind == "handoff":
            return "handoff"
        record = answered.get(step.instruction_src)
        if record is None and step.kind != "statement":
            return "open"
        record = record or {}
        answer = record.get("answer") or {}
        option = answer.get("option")
        # 审核显式写成 EXHAUSTED 的选项分支（原文没覆盖的那一支），或重发后仍答「还没检查 / 不知道」（B21）：
        # 计划没有走完，不算一条走完的指南，也不能说「官方排查已完成」
        if step.kind == "question" and (step.branches.get(option) == "EXHAUSTED" or unanswered(step, answer)):
            return "question_exit"
        step_id = plan.next_step_id(step_id, record.get("feedback") or "not_solved", option=option)
        # 有选项的问句收到对不上任何选项的短答、计划就此结束：答非所问不等于走完（B25「拆了还响，是吱吱声」打成文字，
        # 没走到试拖地模式那一支，rv-0341 不该算一条走完的指南）
        if step.kind == "question" and step_id == "EXHAUSTED" and step.options and option is None and (answer.get("text") or "").strip():
            return "question_exit"
    return "open"


def decide_next(state, *, library) -> NextAction:
    """按 design §3.3 的顺序选下一动作：风险 → 用户意愿 → 已恢复 → 操作条件 → 可发布步骤 → 人工出口。

    候选动作只来自计划库（有来源）：plans_ranked 中 confidence ≥ 0.3 的未耗尽计划按原顺序。
    已执行 / 已耗尽的不复发。
    """
    decision = state.get("turn_decision") or {}
    executed = execution_history(state)
    exhausted = effective_exhausted(state)
    conditions = conditions_for(state)
    basis = tuple(dict.fromkeys(s.get("card_id") for s in executed if s.get("card_id")))

    def result(kind, reason, **extra):
        return NextAction(kind=kind, reason=reason, basis=basis, **extra)

    # 1. 实际风险证据
    if not decision.get("allowed_operations", True) or state.get("escalate_reason") == "R4":
        return result("safety_stop", "safety_risk")
    # 2. 用户明确要求人工
    if decision.get("escalation_trigger") == "R3" or decision.get("primary_intent") == "request_human":
        return result("handoff_offer", "user_requested_human")
    # 3. 用户确认功能恢复
    if executed and executed[-1].get("feedback") == "solved":
        return result("resolved", "user_confirmed_resolved")
    if conditions.paused:
        return result("pause", "user_paused")
    # 诊断树判定原文没覆盖的指南（rv-0341「其他声音」）不算走完一条：交给下一条候选指南完整排查（T36）。
    # 诊断树的一支直接得出官方交售后结论时，没有「未解决」也进质保判断（rv-0341「拆下滚刷后噪音消失」）。
    ends = {pid: replay_end(library, pid, state) for pid in exhausted}
    counted = [pid for pid in exhausted if ends[pid] != "question_exit"]
    # 客户原话说已经做过这条指南的步骤、问题仍在（fact_check 判 done 跳过），与点「未解决」是同一个事实：
    # 指南走完仍未解决，按 SOP 进质保判断并说明理由（T27 走到「没有可用后续」，索凭证前没有任何理由）
    done_by_customer = any(v.get("status") == "done" and v.get("skip")
                           for pid in counted for v in (((state.get("step_checks") or {}).get(pid) or {}).get("steps") or {}).values())
    if len(counted) >= MAX_GUIDES and (any(s.get("feedback") == "not_solved" for s in executed)
                                       or done_by_customer or "handoff" in ends.values()):
        return result("handoff_offer", "guide_exhausted")
    if decision.get("primary_intent") == "complaint" and not decision.get("diagnostic_request"):
        return result("pause", "complaint_reduce_burden")
    blocker_question = support_question(state)
    if blocker_question:
        return result("ask", "operation_conditions_missing", question=blocker_question)
    explaining = next((b for b in reversed(conditions.blockers) if not b.cleared and b.reason == "explain"), None)
    if explaining:
        product = state.get("product_confirmed") or {}
        plan = next((p for p in library.plans if p.plan_id == explaining.plan_id), None)
        if plan and plan.applies(category=state.get("category") or product.get("category"), sku=product.get("sku")):
            return result("pause", "explain_blocked_step", trace={"plan_id": explaining.plan_id, "step_id": explaining.step_id})

    product = state.get("product_confirmed") or {}
    category = state.get("category") or product.get("category")
    sku = product.get("sku")
    answered = answered_history(state)
    executed_src = {s.get("instruction_src") for s in answered}
    executed_steps = {(s.get("plan_id"), s.get("step_id")) for s in answered}

    trace: dict[str, Any] = {"skipped": []}
    pending_step: NextAction | None = None
    for entry in state.get("plans_ranked") or []:
        pid = entry.get("plan_id")
        if pid in exhausted or float(entry.get("confidence", 0) or 0) < SWITCH_CONFIDENCE:
            continue
        try:
            plan = library.get(pid)
        except KeyError:
            continue
        if not plan.applies(category=category, sku=sku):
            continue
        step, skipped_steps = _first_open_step(plan, executed_src, executed_steps, state)
        if step is None:
            trace["skipped"].extend(skipped_steps)
            continue
        # 5. 有适用、未执行、有来源支持的动作
        pending_step = result(
            "step",
            "ranked_plan",
            plan_cursor={
                "plan_id": plan.plan_id,
                "version": plan.version,
                "step_id": step.step_id,
                "source": entry.get("source"),
            },
            trace={**trace, "confidence": entry.get("confidence"), "switched_to": plan.plan_id,
                   "skipped_steps": skipped_steps},
        )
        break
    blocked = [b for b in conditions.blockers if not b.cleared]
    unresolved_blocker = any(b.reason == "unknown" for b in blocked) and not (
        conditions.continue_input_id and conditions.continue_input_id == state.get("input_id")
    )
    burden_stop = int((state.get("counters") or {}).get("skipped", 0)) - conditions.skip_baseline >= BURDEN_SKIP_LIMIT
    if pending_step is not None and not (unresolved_blocker or burden_stop):
        # 情绪策略「少加步骤、多给方案」：已做两步后先让客户选继续还是转人工，不冒用操作条件暂停的文案（T56 / T58
        # 首封带粗口，两步后被说成「I can't confirm the cause yet」，客户不知道还能继续）。说过「继续」就不再拦
        # （客户点卡的轮次不重算情绪，否则每张卡后都会再停一次）。A bare complaint already returned pause above.
        if ("prefer_proposal_over_more_steps" in state.get("emotion_actions", [])
                and len(executed) + len(blocked) >= 2
                and conditions.continue_input_id is None
                and not decision.get("diagnostic_request")):
            return result("pause", "emotion_prefer_proposal", trace=trace)
        return pending_step
    if blocked or any(v is False for v in conditions.resources.values()) or burden_stop:
        recheck = resource_recheck(state)
        if recheck:
            return result("ask", "operation_conditions_recheck", question=recheck, trace=trace)
        return result("pause", "operation_conditions_unavailable", trace=trace)
    # 7. 没有支持的下一动作：说明覆盖边界，提供人工选项
    reason = "no_supported_followup" if executed or exhausted else "knowledge_coverage_missing"
    return result("handoff_offer", reason, trace=trace)
