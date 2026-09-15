"""每种事件 / 动作的合法样例与对应非法样例（票 03 验收：一正一负）。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

BASE = {"seq": 1, "run_id": "run-1", "event_id": "event-1", "recorded_at": "2026-09-13T00:00:00Z"}


def ev(type_: str, **payload: Any) -> dict:
    meta = (
        {
            "summary_id": "summary-1",
            "revision": 1,
            "issue_id": "issue-1",
            "updated_at": "2026-09-13T00:00:00Z",
            "source_through_seq": 1,
        }
        if type_ == "escalation_summary"
        else {}
    )
    if type_ == "message_start":
        meta.update(reply_to_input_id=None, issue_id=None)
    if type_ == "input_received":
        meta.update(issue_id=None)
    if type_ == "escalation_summary":
        meta.update(previous_card_id=None, handoff_status="prepared")
    return {**BASE, "type": type_, **meta, **payload}


STEP = {
    "step_id": "s1",
    "plan_id": "p1",
    "plan_version": 1,
    "step_no": 1,
    "title": "重启设备",
    "instruction": "长按电源键 10 秒",
    "expected_result": "指示灯闪烁",
    "caution": None,
    "evidence_ids": ["e1"],
}

SUMMARY = {
    "product": "A1234",
    "problem": "无法充电",
    "observations": ["指示灯不亮"],
    "hypotheses": ["线材故障"],
    "steps": [{"step_id": "s1", "title": "重启设备", "feedback": "not_solved"}],
    "reason": {"rule_id": "R2", "text": "两步未解决"},
    "emotion": {"level": "anxious", "strategy": "reassure_first"},
    "receipt": {
        "status": "not_collected",
        "verified_facts": {},
        "conflicts": [],
        "next_step": None,
    },
    "model_trace": [
        {"task": "intake.extract", "model_used": "deepseek-chat", "lane": "domestic", "attempts": 1}
    ],
}

# type -> (合法样例, 非法样例, 非法原因)
EVENTS: dict[str, tuple[dict, dict, str]] = {}


def _reg(valid: dict, invalid: dict, why: str) -> None:
    EVENTS[valid["type"]] = (valid, invalid, why)


_reg(
    ev("run_started", resumed=False, deadline_ms=25000),
    ev("run_started", resumed=False, deadline_ms=0),
    "deadline_ms 必须 > 0",
)
_reg(ev("ping"), ev("ping", extra=1), "拒绝未知字段")
_reg(
    ev("progress", stage="diagnose", substage=None),
    ev("progress", stage="thinking"),
    "stage 不在枚举内",
)
_reg(
    ev("tool_call", tool_id="t1", name="knowledge.search", status="started", summary=None),
    ev("tool_call", tool_id="t1", name="knowledge.search", status="running"),
    "status 非法",
)
_reg(ev("message_start", message_id="m1", replaces=None), ev("message_start"), "缺 message_id")
_reg(
    ev("message", message_id="m1", delta="您好"),
    ev("message", message_id="m1", delta=123),
    "delta 必须是字符串",
)
_reg(
    ev("message_end", message_id="m1", status="aborted", model_tier="primary"),
    ev("message_end", message_id="m1", status="completed", model_tier="tertiary"),
    "model_tier 非法",
)
_reg(
    ev(
        "product_card",
        card_id="c1",
        version=3,
        candidates=[
            {"sku": "A1", "name": "充电器", "category": "charger", "image": None, "in_scope": True}
        ],
    ),
    ev("product_card", card_id="c1", version=3, candidates=[]),
    "候选不能为空",
)
_reg(
    ev("step_card", card_id="c2", version=4, step=STEP),
    ev("step_card", card_id="c2", version=4, **{k: v for k, v in STEP.items()}),
    "step 字段必须嵌在 step 对象内",
)
_reg(
    ev(
        "evidence",
        items=[
            {
                "evidence_id": "e1",
                "source": "weknora",
                "doc_id": "d1",
                "doc_version": "v1",
                "chunk_id": "k1",
                "snippet": "……",
                "score": 0.82,
                "status": "ok",
            }
        ],
    ),
    ev(
        "evidence",
        items=[
            {
                "evidence_id": "e1",
                "source": "weknora",
                "doc_id": "d1",
                "doc_version": "v1",
                "chunk_id": "k1",
                "snippet": "……",
                "score": 1.5,
            }
        ],
    ),
    "score 超出 0–1",
)
_reg(
    ev(
        "receipt_card",
        card_id="c3",
        version=5,
        fields={
            "order_no": "1234",
            "channel": "京东",
            "purchase_date": "2026-01-02",
            "amount": None,
        },
        confidence={"order_no": 0.9},
        unreadable=["amount"],
    ),
    ev("receipt_card", card_id="c3", version=5, fields={"order_no": "1234", "warranty_ok": True}),
    "fields 不得含质保结论等未知字段",
)
_reg(
    ev("awaiting_input", kind="step_feedback", input_token="c2", card_id="c2", version=4),
    ev("awaiting_input", kind="free_text", input_token="c2", card_id="c2", version=4),
    "kind 非法",
)
_reg(
    ev("escalation_summary", card_id="c9", summary=SUMMARY),
    ev("escalation_summary", card_id="c9", summary={**SUMMARY, "reason": "R2"}),
    "reason 必须是对象",
)
_reg(
    ev(
        "error",
        code="model_unavailable",
        message="全部通道失败",
        recoverable=True,
        retry_with_same_action=True,
    ),
    ev("error", code="x", message="y"),
    "缺 recoverable",
)
_reg(
    ev("done", reason="awaiting_input", version=18),
    ev("done", reason="finished", version=18),
    "reason 非法",
)


ACTION_BASE = {
    "target_issue_id": "issue-1",
    "action_id": "a-1",
    "expected_version": 17,
    "input_token": "c1",
    "card_id": "c1",
}


def act(kind: str, payload: dict | None = None, **over: Any) -> dict:
    d = {**ACTION_BASE, "kind": kind, **over}
    if payload is not None:
        d["payload"] = payload
    return d


ACTIONS: dict[str, tuple[dict, dict, str]] = {
    "select_product": (
        act("select_product", {"sku": "A1"}),
        act("select_product", {"sku": "A1", "name": "x"}),
        "payload 有未知字段",
    ),
    "step_feedback": (
        act("step_feedback", {"feedback": "solved", "note": None}),
        act("step_feedback", {"feedback": "maybe"}),
        "feedback 非法",
    ),
    "confirm_receipt": (
        act("confirm_receipt", {"fields": {"order_no": "1"}, "edited": ["order_no"]}),
        act("confirm_receipt", {"fields": {"order_no": "1"}, "edited": ["warranty"]}),
        "edited 字段名非法",
    ),
    "skip_receipt": (
        act("skip_receipt", {"reason": "later"}),
        act("skip_receipt", {"reason": "lost"}),
        "reason 非法",
    ),
    "request_human": (
        {"action_id": "a-2", "expected_version": 0, "kind": "request_human", "payload": {}},
        {
            "action_id": "a-2",
            "expected_version": 0,
            "kind": "request_human",
            "payload": {"why": "x"},
        },
        "payload 必须为空对象",
    ),
}


SNAPSHOT_FULL = {
    "session_id": "s-1",
    "version": 17,
    "stage": "guide",
    "substage": None,
    "active_run": {
        "run_id": "run-1",
        "started_at": "2026-09-12T10:00:00Z",
        "deadline_at": "2026-09-12T10:00:25Z",
    },
    "pending_input": {
        "kind": "step_feedback",
        "input_token": "c2",
        "card_id": "c2",
        "version": 17,
    },
    "timeline": [
        {
            "kind": "user_message",
            "id": "u1",
            "text": "充不上电",
            "image_ids": [],
            "at": "2026-09-12T09:59:00Z",
        },
        {
            "kind": "assistant_message",
            "message_id": "m1",
            "text": "别担心……",
            "status": "completed",
            "model_tier": "primary",
            "replaces": None,
        },
        {
            "kind": "tool",
            "tool_id": "t1",
            "name": "knowledge.search",
            "status": "finished",
            "summary": "3 条",
        },
        {
            "kind": "product_card",
            "card_id": "c1",
            "version": 2,
            "candidates": [
                {
                    "sku": "A1",
                    "name": "充电器",
                    "category": "charger",
                    "image": None,
                    "in_scope": True,
                }
            ],
            "selected_sku": "A1",
        },
        {
            "kind": "step_card",
            "card_id": "c2",
            "version": 4,
            "step": STEP,
            "feedback": None,
            "note": None,
        },
        {
            "kind": "receipt_card",
            "card_id": "c3",
            "version": 5,
            "fields": {"order_no": "1"},
            "confidence": {},
            "unreadable": [],
            "confirmed_fields": None,
            "skipped_reason": "later",
        },
        {"kind": "evidence", "items": []},
        {
            "kind": "escalation_summary",
            "card_id": "c9",
            "summary": SUMMARY,
            "summary_id": "s1",
            "revision": 1,
            "updated_at": "2026-09-13T00:00:00Z",
            "source_through_seq": 1,
        },
    ],
    "last_error": {
        "code": "model_unavailable",
        "message": "模型暂时不可用，请稍后重试",
        "recoverable": True,
        "at": "2026-09-12T09:59:30Z",
    },
    "cancelled_run": {"run_id": "run-0", "at": "2026-09-12T09:58:00Z"},
}


def mutate(d: dict, **changes: Any) -> dict:
    out = deepcopy(d)
    out.update(changes)
    return out


_reg(
    ev("input_received", input_id="i1", input_kind="message", payload={"text": "设备不工作"}),
    ev("input_received", input_id="i1", input_kind="invalid", payload={}),
    "invalid input kind",
)
_reg(
    ev(
        "issue_changed",
        active_issue_id="issue-1",
        issues=[],
        input_id="i1",
        resolved_issue_id="issue-1",
        version=1,
    ),
    ev("issue_changed", issues=[]),
    "missing active issue",
)

ACTIONS["new_issue"] = (
    {"kind": "new_issue", "action_id": "a-new", "expected_version": 0, "payload": {}},
    {"kind": "new_issue", "expected_version": 0},
    "missing action ID",
)
ACTIONS["resume_issue"] = (
    {
        "kind": "resume_issue",
        "action_id": "a-resume",
        "expected_version": 0,
        "target_issue_id": "issue-1",
        "payload": {},
    },
    {"kind": "resume_issue", "action_id": "a-resume", "expected_version": 0},
    "missing target",
)

_reg(
    ev(
        "pending_changed",
        issue_id="issue-1",
        pending_id="c1",
        status="suspended",
        reason="issue_switched",
        superseded_by=None,
        version=2,
    ),
    ev("pending_changed", status="unknown"),
    "invalid pending status",
)
_reg(
    ev(
        "summary_updated",
        issue_id="issue-1",
        summary_id="summary-1",
        revision=2,
        card_id="c2",
        previous_card_id="c1",
        source_through_seq=20,
        updated_at="2026-09-13T00:00:00Z",
    ),
    ev("summary_updated", revision=0),
    "invalid revision",
)

_reg(
    ev("context_card", card_id="l3-context_card", version=1, fields=["region_use"]),
    ev("context_card", version=1),
    "missing card_id",
)

_reg(
    ev(
        "proposal_card",
        card_id="l3-proposal_card",
        version=1,
        options=[], decision_summary="演示政策", policy_version="v1",
    ),
    ev("proposal_card", version=1),
    "missing card_id",
)

_reg(
    ev(
        "execution_card",
        card_id="l3-execution_card",
        version=1,
        execution_id="e1", action_kind="replacement.create", status="succeeded", receipt={"status": "created"}, idempotency_key="case:replace",
    ),
    ev("execution_card", version=1),
    "missing card_id",
)

_reg(
    ev(
        "retake_card",
        card_id="l3-retake_card",
        version=1,
        reasons=["模糊"], guidance=["请对焦"],
    ),
    ev("retake_card", version=1),
    "missing card_id",
)

_reg(
    ev("rating_card", card_id="l3-rating_card", version=1),
    ev("rating_card", version=1),
    "missing card_id",
)

_reg(
    ev(
        "case_changed",
        card_id="l3-case_changed",
        version=1,
        case_id="case1", status="tracking", reason="created", updated_at="2026-09-14T00:00:00Z",
    ),
    ev("case_changed", version=1),
    "missing card_id",
)

ACTIONS["confirm_context"] = (
    {
        "kind": "confirm_context",
        "action_id": "a-confirm_context",
        "expected_version": 1,
        "target_issue_id": "issue1",
        "input_token": "t",
        "card_id": "c",
        "payload": {"region_purchase": "CN", "region_use": "CN", "channel": "official_store"},
    },
    {
        "kind": "confirm_context",
        "action_id": "a-confirm_context",
        "expected_version": 1,
        "target_issue_id": "issue1",
        "card_id": "c",
        "payload": {"region_purchase": "CN", "region_use": "CN", "channel": "official_store"},
    },
    "missing token",
)

ACTIONS["confirm_proposal"] = (
    {
        "kind": "confirm_proposal",
        "action_id": "a-confirm_proposal",
        "expected_version": 1,
        "target_issue_id": "issue1",
        "input_token": "t",
        "card_id": "c",
        "payload": {"option_id": "replace"},
    },
    {
        "kind": "confirm_proposal",
        "action_id": "a-confirm_proposal",
        "expected_version": 1,
        "target_issue_id": "issue1",
        "card_id": "c",
        "payload": {"option_id": "replace"},
    },
    "missing token",
)

ACTIONS["decline_proposal"] = (
    {
        "kind": "decline_proposal",
        "action_id": "a-decline_proposal",
        "expected_version": 1,
        "target_issue_id": "issue1",
        "input_token": "t",
        "card_id": "c",
        "payload": {"reason": "not_now"},
    },
    {
        "kind": "decline_proposal",
        "action_id": "a-decline_proposal",
        "expected_version": 1,
        "target_issue_id": "issue1",
        "card_id": "c",
        "payload": {"reason": "not_now"},
    },
    "missing token",
)

ACTIONS["skip_retake"] = (
    {
        "kind": "skip_retake",
        "action_id": "a-skip_retake",
        "expected_version": 1,
        "target_issue_id": "issue1",
        "input_token": "t",
        "card_id": "c",
        "payload": {"reason": "skip"},
    },
    {
        "kind": "skip_retake",
        "action_id": "a-skip_retake",
        "expected_version": 1,
        "target_issue_id": "issue1",
        "card_id": "c",
        "payload": {"reason": "skip"},
    },
    "missing token",
)

ACTIONS["rate_satisfaction"] = (
    {
        "kind": "rate_satisfaction",
        "action_id": "a-rate_satisfaction",
        "expected_version": 1,
        "target_issue_id": "issue1",
        "input_token": "t",
        "card_id": "c",
        "payload": {"score": 5},
    },
    {
        "kind": "rate_satisfaction",
        "action_id": "a-rate_satisfaction",
        "expected_version": 1,
        "target_issue_id": "issue1",
        "card_id": "c",
        "payload": {"score": 5},
    },
    "missing token",
)
