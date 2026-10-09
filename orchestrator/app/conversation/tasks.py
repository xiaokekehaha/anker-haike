"""Sequential intent queue; inline reads never consume a troubleshooting card."""

from copy import deepcopy

from app.conversation.business import BusinessContext
from app.conversation.reduce import stable_id

PRIORITY = {
    "request_human": 0,
    "replacement_request": 1,
    "refund_request": 1,
    "address_update": 1,
    # 暂缓发货 / 取消订单 / 改买：本系统不能改订单，但诉求有时效性（东西可能正要发出），
    # 所以和其他办理类诉求同级，排在查询之前。
    "order_change": 1,
    "report_problem": 2,
    "logistics_query": 3,
    "warranty_query": 3,
    "order_query": 3,
    "social": 4,
}
TASK_INTENTS = set(PRIORITY) - {"social", "request_human"}
LABELS = {
    "replacement_request": "replacement request",
    "refund_request": "refund request",
    "address_update": "address change",
    "order_change": "order change",
    "report_problem": "device troubleshooting",
    "logistics_query": "delivery status",
    "warranty_query": "warranty check",
    "order_query": "order details",
}


# 投诉 / 情绪不是要办的事：和业务诉求同时出现时排在最后，由情绪策略处理语气，不抢走查询或办理。
TRAILING = {"complaint", "social"}

# 要走办理流程（而不是查询）的业务诉求。本系统只能提交预定义服务单，
# 改地址与改订单（暂缓发货 / 取消 / 改买）都超出它能执行的范围，由人工办理。
REMEDY_INTENTS = frozenset({"replacement_request", "refund_request", "address_update", "order_change"})
# 其中本系统完全不能执行、只能如实说明并转人工的那些
NOT_EXECUTABLE = frozenset({"address_update", "order_change"})


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
    notice = "I'll handle your requests in this order: " + " → ".join(labels) + "." if announces_order(incoming) else None
    return result, notice


# 查询类诉求都是从同一张订单上读字段，consult 一轮就一起答完，不会排队逐项处理。
# 「按顺序处理」只在真的要分轮处理时才说（T7 实测：问物流 + 问订单，一次答完却先播报了一句排序）。
CONSULT_ONLY = frozenset({"logistics_query", "warranty_query", "order_query"})


def announces_order(incoming: list[str]) -> bool:
    """这一轮是否真的要分几步办，值得先告诉客户顺序。"""
    return len(incoming) > 1 and not set(incoming) <= CONSULT_ONLY


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
