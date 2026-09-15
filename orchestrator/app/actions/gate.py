from haike_contracts.common import GateCheck, GateResult, PolicyDecision


class AuthorizationGate:
    def check(
        self,
        *,
        decision: PolicyDecision,
        option: dict,
        receipt: dict,
        product_state: str,
        risk_cases: list,
        allowed_operations: bool,
        user_confirmed: bool,
        case_status: str,
        execution_status: str | None = None,
        human_approved: bool = False,
        case_order_no: str | None = None,
    ) -> GateResult:
        remedy = next(
            (r for r in decision.remedies if r.remedy == option.get("remedy") and r.eligible), None
        )
        policy = bool(remedy and remedy.auto_allowed and not decision.needs_human)
        checks = [
            GateCheck(
                name="policy",
                passed=policy or human_approved,
                detail="人工已批准该方案" if human_approved else "方案必须符合当前政策自动办理条件",
            ),
            GateCheck(
                name="evidence_and_consent",
                passed=receipt.get("status") == "order_verified"
                and product_state == "confirmed_sku"
                and decision.fault_class != "unknown"
                and (
                    case_order_no is None
                    or (receipt.get("fields") or {}).get("order_no") == case_order_no
                )
                and user_confirmed,
                detail="订单与案件、产品一致，故障定性明确且用户已确认方案",
            ),
            GateCheck(
                name="safety",
                passed=allowed_operations
                and not any(
                    r.get("rule_id") == "R4" and r.get("status") == "reported" for r in risk_cases
                )
                and decision.fault_class != "safety",
                detail="无未解除的安全风险或操作限制",
            ),
            GateCheck(
                name="idempotency",
                # Only states that follow a published confirmation card, a human
                # approval or a recoverable failure may execute. "proposing" is
                # excluded: TRANSITIONS has no proposing → executing edge, so
                # letting it through here would only fail later in the case store.
                passed=execution_status not in {"running", "succeeded"}
                and case_status in {"awaiting_confirmation", "approved", "executing_failed"},
                detail="案件允许办理且没有执行中或已成功的同键动作",
            ),
        ]
        passed = all(c.passed for c in checks)
        return GateResult(passed=passed, checks=checks, fallback=None if passed else "await_human")
