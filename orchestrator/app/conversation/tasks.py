"""Sequential intent queue; inline reads never consume a troubleshooting card."""

from copy import deepcopy

from app.conversation.business import BusinessContext
from app.conversation.reduce import stable_id

PRIORITY = {
    "request_human": 0,
    "replacement_request": 1,
    "refund_request": 1,
    "address_update": 1,
    "report_problem": 2,
    "logistics_query": 3,
    "warranty_query": 3,
    "order_query": 3,
    "social": 4,
}
TASK_INTENTS = set(PRIORITY) - {"social", "request_human"}
LABELS = {
    "replacement_request": "换货申请",
    "refund_request": "退款审核",
    "address_update": "地址变更",
    "report_problem": "设备排障",
    "logistics_query": "物流查询",
    "warranty_query": "保修查询",
    "order_query": "订单查询",
}


# 投诉 / 情绪不是要办的事：和业务诉求同时出现时排在最后，由情绪策略处理语气，不抢走查询或办理。
TRAILING = {"complaint", "social"}


def ordered_intents(primary, secondary):
    return sorted(
        dict.fromkeys([primary, *secondary]),
        key=lambda intent: (intent in TRAILING, PRIORITY.get(intent, 2)),
    )


def task_business(task, business):
    if "business_reference" in task:
        return business.for_reference(task["business_reference"])
    # Old queues have no ownership. Only their original explicit identifiers
    # establish a target; an intervening chat focus is not evidence.
    return (
        business.for_reference(None)
        .model_copy(update={"last_input_id": None})
        .accept(task.get("quote", ""), "task-binding:" + task["task_id"])
    )


def enqueue(tasks, primary, secondary, text, input_id, *, business=None):
    result = deepcopy(tasks)
    business = business or BusinessContext()
    # Once the user resolves an active task's missing/ambiguous target, keep
    # that selection for subsequent suspension and completion.
    for task in result:
        if (
            task["status"] == "active"
            and task["intent"] == primary
            and business.status == "resolved"
            and task_business(task, business).status != "resolved"
        ):
            task["business_reference"] = business.reference()
    incoming = [i for i in ordered_intents(primary, secondary) if i in TASK_INTENTS]
    if not secondary:
        return result, None
    reference = business.reference()

    def identity(intent, ref):
        return (
            intent,
            ref["status"],
            ref.get("subject_id"),
            tuple(sorted(ref.get("candidate_ids", []))),
        )

    existing = {
        identity(t["intent"], task_business(t, business).reference())
        for t in result
        if t["status"] in {"pending", "active"}
    }
    for intent in incoming:
        key = identity(intent, reference)
        if key not in existing:
            result.append(
                {
                    "task_id": stable_id(input_id, intent),
                    "intent": intent,
                    "quote": text,
                    "status": "active" if intent == primary else "pending",
                    "created_input_id": input_id,
                    "business_reference": reference,
                }
            )
            existing.add(key)
    primary_key = identity(primary, reference)
    for task in result:
        if task["status"] in {"active", "pending"}:
            task["status"] = (
                "active"
                if identity(task["intent"], task_business(task, business).reference())
                == primary_key
                else "pending"
            )
    labels = [LABELS[i] for i in incoming]
    notice = "您提到的需求将按顺序处理：" + " → ".join(labels) + "。" if len(labels) > 1 else None
    return result, notice


def next_task(tasks, completed_intent, *, business=None, task_id=None):
    result = deepcopy(tasks)
    for task in result:
        matches = (
            business is None
            or task_business(task, business).reference() == business.reference()
            or (task["status"] == "active" and task["intent"] == "report_problem")
        )
        if (
            task["status"] in {"active", "pending"}
            and task["intent"] == completed_intent
            and matches
            and (not task_id or task["task_id"] == task_id)
        ):
            task["status"] = "done"
    if any(t["status"] == "active" for t in result):
        return result, None
    candidates = [t for t in result if t["status"] == "pending"]
    if not candidates:
        return result, None
    chosen = min(candidates, key=lambda t: PRIORITY[t["intent"]])
    chosen["status"] = "active"
    return result, chosen
