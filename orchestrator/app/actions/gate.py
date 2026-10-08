"""服务单提交闸门：能否把单子交给售后工具，不是能否自动办理（主办方要求提交后一律转人工）。

四项检查（顺序固定，执行器按名单核对）：
- eligibility：换货 / 退款要保内（订单质保结束日期或授权经销商 12 个月）；补发要物流未送达且客户未收到；
  承运商调查要显示已送达而客户称未收到（D3）。
- evidence：主办方「换货 / 退款必须提供的质保信息」——订单或购买凭证、收货地址、照片或视频、SN（故障类）。
  补发与调查只需订单。
- safety：未解除的 R4 安全风险不提交服务单，直接转人工。
- idempotency：案件允许提交且没有执行中或已成功的同键动作。
"""

from haike_contracts.common import GateCheck, GateResult, WarrantyDecision

from .registry import GATE_CHECKS

EVIDENCE_LABELS = {
    "order_or_receipt": "订单或购买凭证",
    "address": "收货地址",
    "photo_or_video": "故障照片或视频",
    "serial_number": "产品 SN",
}
REQUIRED_EVIDENCE = {
    "replace": ("order_or_receipt", "address", "photo_or_video", "serial_number"),
    "refund": ("order_or_receipt", "address", "photo_or_video", "serial_number"),
    "reship": ("order_or_receipt",),
    "carrier_investigation": ("order_or_receipt",),
}


def missing_evidence(kind: str, evidence: dict) -> list[str]:
    return [key for key in REQUIRED_EVIDENCE[kind] if not evidence.get(key)]


class AuthorizationGate:
    def check(
        self,
        *,
        kind: str,
        warranty: WarrantyDecision | None,
        logistics_ok: bool,
        evidence: dict,
        risk_cases: list,
        allowed_operations: bool,
        user_confirmed: bool,
        case_status: str,
        execution_status: str | None = None,
    ) -> GateResult:
        if kind in {"replace", "refund"}:
            eligible = warranty is not None and warranty.status == "in_warranty"
            eligibility_detail = warranty.reason if warranty else "尚未完成订单质保判断"
        else:
            eligible = logistics_ok
            eligibility_detail = "物流状态符合" + ("补发" if kind == "reship" else "承运商调查") + "条件"
        missing = missing_evidence(kind, evidence)
        checks = [
            GateCheck(name="eligibility", passed=eligible, detail=eligibility_detail),
            GateCheck(
                name="evidence",
                passed=not missing and user_confirmed,
                detail="缺少：" + "、".join(EVIDENCE_LABELS[m] for m in missing)
                if missing
                else ("资料齐全，客户已确认" if user_confirmed else "客户尚未确认提交"),
            ),
            GateCheck(
                name="safety",
                passed=allowed_operations
                and not any(r.get("rule_id") == "R4" and r.get("status") == "reported" for r in risk_cases),
                detail="无未解除的安全风险或操作限制",
            ),
            GateCheck(
                name="idempotency",
                passed=execution_status not in {"running", "succeeded"}
                and case_status in {"awaiting_confirmation", "approved", "executing_failed"},
                detail="案件允许提交且没有执行中或已成功的同键动作",
            ),
        ]
        assert [c.name for c in checks] == GATE_CHECKS
        passed = all(c.passed for c in checks)
        return GateResult(passed=passed, checks=checks, fallback=None if passed else "await_human")
