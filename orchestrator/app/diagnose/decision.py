"""Issue-local symptom evidence and next-move decisions.

Facts and quoted answers are the inputs. Codes/status are compatibility projections,
never independent evidence capable of overruling an accepted answer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.conversation.operation_conditions import (
    BURDEN_SKIP_LIMIT,
    conditions_for,
    effective_exhausted,
    execution_history,
    resource_recheck,
    step_unavailable,
    support_question,
)
from app.conversation.taxonomy import (
    canonical_codes,
    families,
    interview_answer,
    next_interview,
    record_response,
    response_attempts,
    taxonomy,
    taxonomy_for,
)


def _active_facts(issue):
    return [
        f
        for f in issue.get("facts", [])
        if f.get("status") == "active" and f.get("kind") == "symptom"
    ]


def valid_interview(interview):
    return bool(
        interview
        and not interview.get("superseded_by_input_id")
        and interview.get("taxonomy_version") in {None, taxonomy()["version"]}
    )


def _answer_codes(interview):
    if not valid_interview(interview):
        return []
    # Recover old checkpoints whose `narrowed` flag was overwritten, using the
    # accepted answers and candidate set, not the stale presentation flag.
    if not interview.get("answers") or (
        len(interview.get("candidates", [])) != 1
        and not any(a.get("answer") == "selection" for a in interview["answers"])
    ):
        return []
    return [
        f["symptom_code"]
        for f in families(interview.get("category"))
        if f["fault_family"] in interview["candidates"]
    ]


def symptom_codes(issue):
    codes = [code for f in _active_facts(issue) for code in f.get("symptom_codes", [])]
    codes += _answer_codes(issue.get("symptom_interview"))
    return list(dict.fromkeys(codes))


def accept_answer(issue, answer, *, text, input_id, changed_fact_ids, answer_expected=False):
    """The only writer of accepted interview results; corrections explicitly supersede them."""
    original = issue.get("symptom_interview")
    interview, accepted = interview_answer(original, answer, text, input_id)
    question = (interview or {}).get("question")
    if (
        valid_interview(interview)
        and question
        and not accepted
        and answer_expected
        and text.strip()
        and question.get("asked_input_id") != input_id
    ):
        interview = record_response(
            interview,
            input_id=input_id,
            outcome="unparsed",
            candidates=interview.get("candidates", []),
            progressed=False,
            quote=text,
        )
    changed = [
        f
        for f in issue.get("facts", [])
        if f.get("fact_id") in changed_fact_ids and f.get("kind") == "symptom"
    ]
    corrected = any(f.get("status") != "active" for f in changed)
    usable = [f for f in changed if f.get("symptom_codes")]
    if interview and usable and not corrected:
        # New symptom evidence starts a new consecutive-progress window, not
        # a new total budget. Retries are de-duplicated by the reducer.
        interview = {**interview, "progress_start": len(response_attempts(interview))}
    elif (
        valid_interview(interview)
        and changed
        and not corrected
        and not accepted
        and interview.get("question")
    ):
        # A described symptom that maps to no fault family did not move the
        # interview: it neither answers the pending question nor narrows the
        # candidates. Counting it keeps both budgets live — otherwise every
        # supplement clears the window and the same question repeats forever.
        interview = record_response(
            interview,
            input_id=input_id,
            outcome="unmapped",
            candidates=interview.get("candidates", []),
            progressed=False,
            quote=text,
        )
    if interview and corrected and not accepted:
        interview = {
            **interview,
            "status": "superseded",
            "question": None,
            "superseded_by_input_id": input_id,
        }
    elif interview and not interview.get("superseded_by_input_id"):
        # Adding a symptom does not retract earlier answers. It can make the
        # pending question unnecessary, while all accepted observations remain.
        if changed and not accepted and symptom_codes(issue):
            interview = {**interview, "question": None}
        interview = {
            **interview,
            "status": "narrowed"
            if _answer_codes(interview)
            else "asking"
            if interview.get("question")
            else "resolved",
        }
    projected = {**issue, "symptom_interview": interview}
    codes = symptom_codes(projected)
    if not codes and not issue.get("facts") and not changed_fact_ids and not original:
        # Legacy/no-model checkpoints already carry a positively matched code.
        # It remains issue-local; changing devices creates a fresh issue.
        codes = list(issue.get("symptom_codes") or [])
    return {"symptom_interview": interview, "symptom_codes": codes}, accepted


MAX_NO_PROGRESS = 2
MAX_INTERVIEW_RESPONSES = 8


@dataclass(frozen=True)
class DiagnosticDecision:
    outcome: Literal["continue", "clarify", "escalate"]
    codes: list[str]
    reason: str
    interview: dict[str, Any] | None = None
    source_refs: tuple[str, ...] = ()
    candidate_codes: tuple[str, ...] = ()
    allowed_plans: tuple[dict[str, Any], ...] = ()
    constrain_plans: bool = False
    missing_information: tuple[str, ...] = ()
    progress: dict[str, int] = field(default_factory=dict)

    def snapshot(self, state):
        value = asdict(self)
        value.pop("interview")
        return {
            **value,
            "issue_id": state.get("active_issue_id"),
            "taxonomy_version": taxonomy()["version"],
            "input_id": state.get("input_id"),
        }


def constrain_plans(state, plans):
    """Carry the decision's intersection through ranking and operation publication."""
    decision = state.get("diagnostic_decision") or {}
    if not decision.get("constrain_plans"):
        return list(plans)
    if (
        decision.get("issue_id") != state.get("active_issue_id")
        or decision.get("taxonomy_version") != taxonomy()["version"]
    ):
        return []
    allowed = {(p["plan_id"], p["version"]) for p in decision.get("allowed_plans", [])}
    return [p for p in plans if (p.plan_id, p.version) in allowed]


def _progress(interview):
    attempts = response_attempts(interview)
    no_progress = 0
    for attempt in reversed(attempts[int((interview or {}).get("progress_start", 0)) :]):
        if attempt["progressed"]:
            break
        no_progress += 1
    return {
        "attempts": len(attempts),
        "consecutive_no_progress": no_progress,
        "hard_limit": MAX_INTERVIEW_RESPONSES,
    }


def decide_symptoms(state, *, available_plans=()) -> DiagnosticDecision:
    issue = (state.get("issues") or {}).get(state.get("active_issue_id"), {})
    raw_interview = state.get("symptom_interview")
    interview = raw_interview if valid_interview(raw_interview) else None
    issue = {**issue, "symptom_interview": interview}
    codes = symptom_codes(issue)
    if not issue.get("facts") and not raw_interview:
        codes = list(dict.fromkeys([*codes, *(state.get("symptom_codes") or [])]))
    product = state.get("product_confirmed") or {}
    category = state.get("category") or product.get("category")
    if not codes:
        for text in state.get("symptoms") or []:
            codes.extend(canonical_codes(text, category=category)[0])
        codes.extend(canonical_codes(state.get("text", ""), category=category)[0])
    codes = list(dict.fromkeys(codes))
    # 品类未定时 intake 用全品类并集归一症状码（「异响」同时命中扫地机 / 充电器 / 吸奶器）；
    # 品类一定，只保留本品类词表里的码，别的品类的码不进决策与状态
    known = {f["symptom_code"] for f in families(category)}
    if known:
        codes = [c for c in codes if c in known]
    refs = list(
        dict.fromkeys(ref for f in _active_facts(issue) for ref in f.get("source_entry_ids", []))
    )
    if interview:
        refs = list(dict.fromkeys([*refs, *(a["input_id"] for a in response_attempts(interview))]))
    candidates = tuple(
        f["symptom_code"]
        for f in families(category)
        if interview and f["fault_family"] in interview.get("candidates", [])
    )
    eligible = [
        p
        for p in available_plans
        if p.applies(category=category, sku=product.get("sku"))
        and p.plan_id not in effective_exhausted(state)
    ]
    progress = _progress(interview)

    def result(
        outcome,
        reason,
        *,
        selected=(),
        constrained=False,
        missing=(),
        current=interview,
        resolved_codes=None,
    ):
        return DiagnosticDecision(
            outcome=outcome,
            codes=codes if resolved_codes is None else resolved_codes,
            reason=reason,
            interview=current,
            source_refs=tuple(refs),
            candidate_codes=candidates,
            allowed_plans=tuple(
                {
                    "plan_id": p.plan_id,
                    "version": p.version,
                    "step_id": p.first_step().step_id,
                    "instruction_src": p.first_step().instruction_src,
                }
                for p in selected
            ),
            constrain_plans=constrained,
            missing_information=tuple(missing),
            progress=progress,
        )

    if not (state.get("turn_decision") or {}).get("allowed_operations", True):
        return result("escalate", "safety_restriction")
    if interview and interview.get("answers") and not interview.get("candidates"):
        return result("escalate", "evidence_conflict", missing=["核对互相冲突的现象和回答"])
    if codes:
        return result(
            "continue",
            "symptom_evidence_available",
            selected=[p for p in eligible if set(codes).intersection(p.symptom_codes)],
        )
    if not taxonomy_for(category)["families"]:
        # 该品类没有症状词表（目录级品类）：没有判别题可问，按「缺少适用的澄清问题」诚实结束，
        # 不拿别的品类的判别题去问用户
        return result(
            "escalate", "category_coverage_missing", missing=["该品类暂无可用的排查资料"], current=None
        )
    # Same plan identity/version guarantees compatible instructions, conditions,
    # and subsequent transitions. Similar step names do not establish equivalence.
    if interview and any(a["answer"] in {"yes", "no"} for a in interview.get("answers", [])):
        choices = [{p.plan_id for p in eligible if code in p.symptom_codes} for code in candidates]
        shared = set.intersection(*choices) if choices else set()
        if shared:
            reason = (
                "same_applicable_plans"
                if all(c == choices[0] for c in choices)
                else "common_applicable_plans"
            )
            return result(
                "continue",
                reason,
                selected=[p for p in eligible if p.plan_id in shared],
                constrained=True,
                resolved_codes=list(candidates),
            )
    interview = next_interview(interview, state.get("active_issue_id"), state.get("input_id"), category=category)
    progress = _progress(interview)
    question = (interview.get("question") or {}).get("question")
    missing = [question] if question else ["可区分当前现象的澄清问题"]
    reason = None
    if progress["consecutive_no_progress"] >= MAX_NO_PROGRESS:
        tail = response_attempts(interview)[-MAX_NO_PROGRESS:]
        reason = (
            "answers_unavailable" if all(a["outcome"] == "unknown" for a in tail) else "no_progress"
        )
    elif progress["attempts"] >= MAX_INTERVIEW_RESPONSES:
        reason = "clarification_budget_exhausted"
    elif not question:
        reason = "question_coverage_missing"
    if reason:
        return result(
            "escalate",
            reason,
            missing=missing,
            current={**interview, "status": "insufficient", "question": None},
        )
    return result("clarify", "symptom_missing", current=interview, missing=missing)


def owns_diagnostic_reply(state):
    """Physical advice always uses published plan content, including conversational detours."""
    issue = (state.get("issues") or {}).get(state.get("active_issue_id"), {})
    return bool(
        _active_facts(issue)
        or state.get("symptoms")
        or state.get("symptom_interview")
        or state.get("symptom_codes")
        or state.get("plan_cursor")
    )


def explanation(state):
    decision = state.get("turn_decision") or {}
    if not decision.get("allowed_operations", True):
        return "这台设备还有待核实的安全风险，请暂停使用和充电。可以继续核对记录或整理给人工客服。"
    step = ((state.get("pending_card") or {}).get("payload") or {}).get("step")
    if step:
        caution = f"注意：{step['caution']}。" if step.get("caution") else ""
        return (
            f"当前已确认的排查步骤是：{step['instruction']}。{caution}"
            f"预期结果：{step['expected_result']}。这次问答不会记为已执行；"
            "请完成后反馈结果，如不能操作请反馈“无法操作”。"
        )
    if state.get("stage") == "done":
        return "此前已记录问题解决；如果问题再次出现，请描述当前现象，我会重新核对适用方案。"
    if state.get("symptom_interview", {}) and (state.get("symptom_interview") or {}).get(
        "question"
    ):
        return state["symptom_interview"]["question"]["question"]
    if state.get("exhausted_plans"):
        return "现有适用排查步骤已经尝试或无法继续，尚未确认解决。可以整理已试步骤给人工客服；不会重复建议您已做过的操作。"
    return "当前尚未有可下发的排查步骤。可以要求继续排查，我会核对已报告现象和适用方案；没有对应方案时会明确说明。"


# ---------------- 依据观察做下一次决策（design §3.2–§3.3） ----------------

SWITCH_CONFIDENCE = 0.3
MAX_OBSERVATION_ASKS = 2
# 对外兼容 / 观测层的规则码映射；真实原因在 NextAction.reason
COMPAT_RULE = {
    "safety_stop": "R4",
    "handoff_offer": "R2",
}
HANDOFF_RULE_BY_REASON = {"user_requested_human": "R3", "safety_risk": "R4"}


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


def _asks_for(state, observation_id: str) -> list[dict[str, Any]]:
    return [
        r
        for r in state.get("observation_requests") or []
        if r.get("observation_id") == observation_id
        and r.get("issue_id", state.get("active_issue_id")) == state.get("active_issue_id")
    ]


def _first_open_step(plan, executed_src: set[str], executed_steps: set[tuple[str, str]], state=None):
    """第一个未执行的步骤与途中跳过的步骤（同 instruction_src 已执行 → 不重复建议）。"""
    skipped = []
    for step in plan.steps:
        unavailable = step_unavailable(state or {}, plan.plan_id, step)
        if unavailable:
            skipped.append({"plan_id": plan.plan_id, "step_id": step.step_id, "reason": unavailable})
            continue
        if (plan.plan_id, step.step_id) in executed_steps:
            skipped.append({"plan_id": plan.plan_id, "step_id": step.step_id, "reason": "already_executed"})
            continue
        if step.instruction_src in executed_src:
            skipped.append({"plan_id": plan.plan_id, "step_id": step.step_id, "reason": "duplicate_instruction_src"})
            continue
        return step, skipped
    return None, skipped


def decide_next(state, *, library) -> NextAction:
    """按 design §3.3 的顺序选下一动作：风险 → 用户意愿 → 已恢复 → 缺失观察 → 可发布步骤 → 人工出口。

    候选动作只来自计划库（有来源）：plans_ranked 中 confidence ≥ 0.3 的未耗尽计划按原顺序优先；
    其后是被已知观察解锁（requires_observations 满足）的计划。已排除 / 已执行 / 已耗尽的不复发。
    """
    from app.diagnose.observations import known_observations, known_option_ids

    issue = (state.get("issues") or {}).get(state.get("active_issue_id"), {})
    raw_interview = state.get("symptom_interview") or issue.get("symptom_interview")
    interview = raw_interview if valid_interview(raw_interview) else None
    decision = state.get("turn_decision") or {}
    executed = execution_history(state)
    exhausted = effective_exhausted(state)
    conditions = conditions_for(state)
    known = known_observations(issue, interview, library)
    option_ids = known_option_ids(known)
    basis = tuple(
        dict.fromkeys(
            [
                *(v["source_id"] for v in known.values() if v.get("source_id")),
                *(s.get("card_id") for s in executed if s.get("card_id")),
            ]
        )
    )

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
    executed_src = {s.get("instruction_src") for s in executed}
    executed_steps = {(s.get("plan_id"), s.get("step_id")) for s in executed}
    codes = symptom_codes({**issue, "symptom_interview": interview}) or list(
        state.get("symptom_codes") or []
    )

    ranked: list[tuple[Any, dict[str, Any]]] = []
    for entry in state.get("plans_ranked") or []:
        pid = entry.get("plan_id")
        if pid in exhausted or float(entry.get("confidence", 0) or 0) < SWITCH_CONFIDENCE:
            continue
        try:
            ranked.append((library.get(pid), entry))
        except KeyError:
            continue
    ranked_ids = {p.plan_id for p, _ in ranked}
    unlocked = [
        (p, {"plan_id": p.plan_id, "confidence": None, "source": "observation"})
        for p in library.allowed_for(category=category, sku=sku, symptom_codes=codes)
        if p.requires_observations and p.plan_id not in exhausted and p.plan_id not in ranked_ids
    ] if category else []
    # 问诊期的计划约束只针对模型排序结果；观察解锁的计划以观察条件 + 症状码为门槛
    candidates = [
        (p, entry)
        for p, entry in [*ranked, *unlocked]
        if p.applies(category=category, sku=sku)
        and (entry.get("source") == "observation" or constrain_plans(state, [p]))
    ]

    trace: dict[str, Any] = {"skipped": [], "known_observations": option_ids}
    pending_ask: tuple[Any, str] | None = None
    pending_step: NextAction | None = None
    unavailable: list[str] = []
    for plan, entry in candidates:
        gate, missing = plan.observation_gate(option_ids)
        if gate == "excluded":
            trace["skipped"].append({"plan_id": plan.plan_id, "reason": "excluded_by_observation"})
            continue
        if gate == "missing":
            # 4. 只问会改变可用动作的观察；同一问题不反复问
            for obs_id in missing:
                asks = _asks_for(state, obs_id)
                obs = library.observation_definitions()[obs_id]
                if obs.requires_execution and not any(
                    (owner.plan_id, step.step_id) in executed_steps
                    for owner in library.plans for step in owner.steps
                    if any(o.observation_id == obs_id for o in step.observations)
                ):
                    trace["skipped"].append({"observation_id": obs_id, "reason": "observation_requires_execution"})
                    continue
                if (any(conditions.resources.get(r) is False for r in obs.required_resources)
                        or any(a.get("status") == "unknown" for a in asks) or len(asks) >= MAX_OBSERVATION_ASKS):
                    unavailable.append(obs_id)
                    continue
                if pending_ask is None:
                    pending_ask = (plan, obs_id)
            trace["skipped"].append({"plan_id": plan.plan_id, "reason": "observation_missing", "missing": missing})
            continue
        step, skipped_steps = _first_open_step(plan, executed_src, executed_steps, state)
        if step is None:
            trace["skipped"].extend(skipped_steps)
            continue
        # 5. 有适用、未执行、有来源支持的动作
        candidate_step = result(
            "step",
            "ranked_plan" if entry.get("source") != "observation" else "observation_unlocked_plan",
            plan_cursor={
                "plan_id": plan.plan_id,
                "version": plan.version,
                "step_id": step.step_id,
                "source": entry.get("source"),
            },
            trace={**trace, "confidence": entry.get("confidence"), "switched_to": plan.plan_id,
                   "skipped_steps": skipped_steps},
        )
        if pending_step is None:
            pending_step = candidate_step
    if pending_ask is not None:
        plan, obs_id = pending_ask
        obs = library.observation_definitions()[obs_id]
        return result(
            "ask",
            "observation_changes_next_action",
            question={
                "observation_id": obs.observation_id,
                "question": obs.question,
                "options": [{"option_id": o.option_id, "label": o.label, "kind": o.kind} for o in obs.options],
                "plan_id": plan.plan_id,
                "attempt": len(_asks_for(state, obs_id)) + 1,
            },
            trace=trace,
        )
    blocked = [b for b in conditions.blockers if not b.cleared]
    unresolved_blocker = any(b.reason == "unknown" for b in blocked) and not (
        conditions.continue_input_id and conditions.continue_input_id == state.get("input_id")
    )
    burden_stop = int((state.get("counters") or {}).get("skipped", 0)) - conditions.skip_baseline >= BURDEN_SKIP_LIMIT
    # A bare complaint already returned pause above, so only the emotion action is left here.
    emotion_stop = (
        "prefer_proposal_over_more_steps" in state.get("emotion_actions", [])
        and len(executed) + len(blocked) >= 2
        and conditions.continue_input_id != state.get("input_id")
        and not decision.get("diagnostic_request")
    )
    if pending_step and not (unresolved_blocker or burden_stop or emotion_stop):
        return pending_step
    if blocked or any(v is False for v in conditions.resources.values()) or burden_stop or emotion_stop:
        recheck = resource_recheck(state)
        if recheck:
            return result("ask", "operation_conditions_recheck", question=recheck, trace=trace)
        return result("pause", "operation_conditions_unavailable", trace=trace)
    # 7. 没有支持的下一动作：说明覆盖边界，提供人工选项
    if unavailable:
        reason = "observation_unavailable"
    elif executed or exhausted:
        reason = "no_supported_followup"
    else:
        reason = "knowledge_coverage_missing"
    return result("handoff_offer", reason, trace={**trace, "unavailable": unavailable})
