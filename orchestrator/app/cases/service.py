"""Business transitions and approval invariants; no graph or model dependencies."""

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from haike_contracts.common import ProposalOption

from .store import CaseConflict, MemoryCaseStore

TRANSITIONS = {
    "open": {"diagnosing", "proposing", "awaiting_approval"},
    "diagnosing": {"proposing", "awaiting_approval"},
    "proposing": {"awaiting_confirmation", "awaiting_approval", "closed_unresolved"},
    "awaiting_confirmation": {"proposing", "executing", "awaiting_approval", "closed_unresolved"},
    "awaiting_approval": {"approved", "rejected", "awaiting_confirmation"},
    "approved": {"executing", "awaiting_approval"},
    "executing": {"tracking", "executing_failed", "awaiting_approval"},
    "executing_failed": {"executing", "proposing", "awaiting_approval", "closed_unresolved"},
    "tracking": {"closed", "proposing", "awaiting_approval"},
    "rejected": {"proposing", "closed_unresolved"},
    "closed": {"reopened"},
    "closed_unresolved": {"reopened"},
    "reopened": {"tracking", "proposing"},
    "escalated_summary": {"reopened"},
}


def now():
    return datetime.now(UTC).isoformat()


def validate_manual_action(row, command, expected_revision):
    if row["revision"] != expected_revision:
        raise CaseConflict("案件已变化，请刷新")
    if command == "close":
        if row["status"] == "executing":
            raise CaseConflict("动作执行中，待回执返回后结案")
    elif command == "reopen":
        if "reopened" not in TRANSITIONS.get(row["status"], set()):
            raise CaseConflict("仅已结束或已交接案件可以重新受理")
    else:
        raise ValueError("未知案件操作")


def _event(row, kind, payload, actor):
    row["revision"] += 1
    row["updated_at"] = now()
    row["events"].append(
        {
            "seq": len(row["events"]) + 1,
            "type": kind,
            "payload": payload,
            "actor": actor,
            "at": row["updated_at"],
        }
    )


def _transition(row, status, reason, actor="system"):
    if row["status"] == status:
        return
    if status not in TRANSITIONS.get(row["status"], set()) and status != "escalated_summary":
        raise CaseConflict(f"非法案件迁移：{row['status']} → {status}")
    previous = row["status"]
    row["status"] = status
    if status in {"closed", "closed_unresolved"}:
        row["closed_at"] = now()
    if status == "reopened":
        row["reopened_count"] += 1
        row["closed_at"] = None
    _event(row, "status_changed", {"from": previous, "to": status, "reason": reason}, actor)


class CaseService:
    def __init__(self, store=None):
        self.store = store if store is not None else MemoryCaseStore()

    async def open(self, session_id, issue_id, product, complaint_risk=False):
        at = now()
        case_id = str(uuid5(NAMESPACE_URL, f"{session_id}:{issue_id}:case"))
        return await self.store.open(
            {
                "case_id": case_id,
                "session_id": session_id,
                "issue_id": issue_id,
                "sku": product.get("sku"),
                "category": product.get("category"),
                "status": "open",
                "complaint_risk": complaint_risk,
                "priority": "high" if complaint_risk else "normal",
                "policy_decision": None,
                "proposal": None,
                "chosen_option_id": None,
                "gate_result": None,
                "owner": None,
                "external_refs": {},
                "opened_at": at,
                "updated_at": at,
                "closed_at": None,
                "reopened_count": 0,
                "revision": 0,
            }
        )

    async def transition(
        self, case_id, status, reason, *, actor="system", expected_revision=None, **updates
    ):
        allowed = {
            "policy_decision",
            "proposal",
            "chosen_option_id",
            "gate_result",
            "external_refs",
            "complaint_risk",
            "priority",
            "owner",
        }
        if set(updates) - allowed:
            raise ValueError("未知案件字段")

        def apply(row):
            changed = any(row.get(k) != v for k, v in updates.items())
            previous = row["revision"]
            _transition(row, status, reason, actor)
            row.update(updates)
            if changed and row["revision"] == previous:
                _event(row, "updated", {"reason": reason}, actor)

        return await self.store.mutate(case_id, apply, expected_revision)

    async def attach_execution(self, case_id, receipt):
        def apply(row):
            refs = row.setdefault("external_refs", {})
            if (
                refs.get("order_no")
                and receipt.get("order_no")
                and refs["order_no"] != receipt["order_no"]
            ):
                raise CaseConflict("执行回执与案件订单不一致")
            attached = {
                k: receipt[k]
                for k in ("order_no", "service_order_no", "tracking_no")
                if receipt.get(k)
            }
            changed = any(refs.get(k) != v for k, v in attached.items())
            _transition(row, "tracking", "服务单已创建")
            refs.update(attached)
            if changed:
                _event(row, "execution_attached", dict(refs), "system")

        return await self.store.mutate(case_id, apply)

    async def bind_order(self, case_id, order_no):
        """A case's verified order is immutable; another order needs another case."""

        def apply(row):
            refs = row.setdefault("external_refs", {})
            if refs.get("order_no") and refs["order_no"] != order_no:
                raise CaseConflict("案件已关联其他订单，请分别处理")
            if not refs.get("order_no"):
                refs["order_no"] = order_no
                _event(row, "order_identified", {"order_no": order_no}, "system")

        return await self.store.mutate(case_id, apply)

    async def identify_product(self, case_id, product):
        """Fill an initially unknown case product; never change an established identity."""

        def apply(row):
            if row.get("sku") and row["sku"] != product["sku"]:
                raise CaseConflict("案件已关联其他产品，请分别处理")
            if not row.get("sku"):
                row.update(sku=product["sku"], category=product["category"])
                _event(row, "product_identified", {"sku": product["sku"]}, "system")

        return await self.store.mutate(case_id, apply)

    async def close(
        self,
        case_id,
        *,
        user_confirmed=False,
        external_status=None,
        actor="user",
        expected_revision=None,
    ):
        if not actor.startswith("agent:") and not (
            user_confirmed and external_status in {"shipped", "completed", "delivered"}
        ):
            raise CaseConflict("结案需要外部终态与用户确认")
        if actor.startswith("agent:"):

            def apply(row):
                if row["status"] == "executing":
                    raise CaseConflict("动作执行中，待回执返回后结案")
                if row["status"] in {"closed", "closed_unresolved"}:
                    return
                previous = row["status"]
                row["status"], row["closed_at"] = "closed", now()
                _event(
                    row,
                    "status_changed",
                    {"from": previous, "to": "closed", "reason": "人工结案"},
                    actor,
                )

            return await self.store.mutate(case_id, apply, expected_revision)
        return await self.transition(
            case_id,
            "closed",
            "用户确认已收到或人工结案",
            actor=actor,
            expected_revision=expected_revision,
        )

    async def reopen(self, case_id, *, actor="user", expected_revision=None, input_id=None, quote=None):
        if input_id:
            if not quote or not quote.strip():
                raise ValueError("重新受理需要本轮用户原话")

            def apply(row):
                payload = {"input_id": input_id, "quote": quote}
                existing = next((e for e in row["events"] if e["type"] == "resolution_disputed" and e["payload"].get("input_id") == input_id), None)
                if existing:
                    if existing["payload"] != payload or existing["actor"] != actor:
                        raise CaseConflict("同一输入不能用于不同的重开请求")
                    return
                validate_manual_action(row, "reopen", expected_revision)
                _transition(row, "reopened", "用户报告问题仍未解决", actor)
                if row.get("proposal"):
                    row["proposal"] = {**row["proposal"], "user_confirmed": False, "chosen_option_id": None, "status": "inactive"}
                row["chosen_option_id"] = None
                _event(row, "resolution_disputed", payload, actor)

            return await self.store.mutate(case_id, apply)
        return await self.transition(
            case_id, "reopened", "客户再次求助", actor=actor, expected_revision=expected_revision
        )

    async def manual_action(self, case_id, command, *, command_id, actor, expected_revision):
        """Apply once across a crash between the case transaction and graph checkpoint."""
        if not actor.startswith("agent:"):
            raise ValueError("需要管理员身份")

        def apply(row):
            existing = next((e for e in row["events"] if e["type"] == "manual_action" and e["payload"].get("command_id") == command_id), None)
            payload = {"command_id": command_id, "command": command, "expected_revision": expected_revision}
            if existing:
                if existing["payload"] != payload or existing["actor"] != actor:
                    raise CaseConflict("操作编号已用于其他请求")
                return
            validate_manual_action(row, command, expected_revision)
            if command == "reopen":
                _transition(row, "reopened", "人工重新受理", actor)
            elif row["status"] not in {"closed", "closed_unresolved"}:
                previous = row["status"]
                row["status"], row["closed_at"] = "closed", now()
                _event(row, "status_changed", {"from": previous, "to": "closed", "reason": "人工结案"}, actor)
            if row.get("proposal"):
                row["proposal"] = {**row["proposal"], "user_confirmed": False, "chosen_option_id": None, "status": "inactive"}
            row["chosen_option_id"] = None
            _event(row, "manual_action", payload, actor)

        return await self.store.mutate(case_id, apply)

    async def decide(
        self,
        case_id,
        *,
        decision_id,
        decision,
        actor,
        expected_revision,
        note,
        option_id=None,
        edited_option=None,
        override_reason=None,
    ):
        if decision not in {"approve", "reject", "request_info"} or not actor.startswith("agent:"):
            raise ValueError("非法人工决定")

        def apply(row):
            existing = next((d for d in row["decisions"] if d["decision_id"] == decision_id), None)
            if existing:
                if any(
                    existing.get(k) != v
                    for k, v in {
                        "decision": decision,
                        "option_id": option_id,
                        "note": note,
                        "override_reason": override_reason,
                        "edited_proposal": edited_option,
                        "actor": actor,
                    }.items()
                ):
                    raise CaseConflict("decision_id 已用于其他决定")
                return
            if row["revision"] != expected_revision or row["status"] != "awaiting_approval":
                raise CaseConflict("案件已由其他人处理，请刷新")
            options = (row.get("proposal") or {}).get("options", [])
            option = next((o for o in options if o["option_id"] == option_id), None)
            if decision == "approve":
                if (row.get("policy_decision") or {}).get("fault_class") in {"unknown", "safety"}:
                    raise ValueError("请先核实故障并解除安全限制；人工审批不能替代故障证据，可要求补充信息")
                if edited_option:
                    edited = ProposalOption.model_validate(edited_option).model_dump(mode="json")
                    if not option or edited["option_id"] != option_id or edited["remedy"] != option["remedy"]:
                        raise ValueError("人工编辑必须对应所选方案")
                    option = edited
                if not option or option["remedy"] != "replace":
                    raise ValueError("P0 仅支持批准换货动作")
                if (
                    edited_option
                    or (row.get("policy_decision") or {}).get("needs_human")
                    or not option.get("auto_allowed")
                ) and not (override_reason or "").strip():
                    raise ValueError("覆盖政策需填写理由")
            row["decisions"].append(
                {
                    "decision_id": decision_id,
                    "decision": decision,
                    "actor": actor,
                    "option_id": option_id,
                    "edited_proposal": edited_option,
                    "override_reason": override_reason,
                    "note": note,
                    "at": now(),
                    "consumed_input_id": None,
                    "case_revision": expected_revision,
                }
            )
            _transition(
                row,
                {
                    "approve": "approved",
                    "reject": "rejected",
                    "request_info": "awaiting_confirmation",
                }[decision],
                note,
                actor,
            )

        return await self.store.mutate(case_id, apply)

    async def consume_decision(self, case_id, decision_id, input_id):
        def apply(row):
            item = next((d for d in row["decisions"] if d["decision_id"] == decision_id), None)
            if item is None or item.get("consumed_input_id") not in {None, input_id}:
                raise CaseConflict("审批决定无效或已消费")
            expected_status = {"approve": "approved", "reject": "rejected", "request_info": "awaiting_confirmation"}[item["decision"]]
            if item.get("consumed_input_id") is None and row["status"] != expected_status:
                raise CaseConflict("案件状态已变化，原审批决定不能继续办理")
            item["consumed_input_id"] = input_id

        return await self.store.mutate(case_id, apply)

    async def record_handoff(self, case_id, summary):
        """The latest AI handoff for the desk. Case events never reach the customer's timeline."""

        def apply(row):
            last = next((e["payload"] for e in reversed(row["events"]) if e["type"] == "handoff_summary"), None)
            if last != summary:
                _event(row, "handoff_summary", summary, "system")

        return await self.store.mutate(case_id, apply)

    async def record_commitment(self, case_id, text, source, *, source_ref=None):
        from .commitments import valid_commitment

        payload = {"text": text, "source": source, "at": now()}
        if source_ref:
            payload["source_ref"] = source_ref
        if not valid_commitment(payload):
            raise ValueError("方案信息必须有条款、回执、动作配置或人工决定依据")

        def apply(row):
            if source == "human_decision" and not any(d["decision_id"] == source_ref for d in row["decisions"]):
                raise ValueError("人工决定依据不属于当前案件")
            if not any(
                e["type"] == "commitment"
                and e["payload"].get("text") == text
                and e["payload"].get("source") == source
                and e["payload"].get("source_ref") == source_ref
                for e in row["events"]
            ):
                _event(row, "commitment", payload, "system")

        return await self.store.mutate(case_id, apply)

    async def rate(self, session_id, issue_id, score, comment=None, case_id=None):
        if not isinstance(score, int) or not 1 <= score <= 5:
            raise ValueError("评分须为 1–5")
        await self.store.rate(
            {
                "session_id": session_id,
                "issue_id": issue_id,
                "case_id": case_id,
                "score": score,
                "comment": comment,
            }
        )


def case_event(row, *, issue_id=None, version=0, reason="案件状态更新"):
    return {
        "type": "case_changed",
        "card_id": row["case_id"],
        "case_id": row["case_id"],
        "issue_id": issue_id or row["issue_id"],
        "version": version,
        "status": row["status"],
        "complaint_risk": row["complaint_risk"],
        "priority": row["priority"],
        "owner": row.get("owner"),
        "reason": reason,
        "external_refs": row.get("external_refs") or {},
        "updated_at": row["updated_at"],
    }
