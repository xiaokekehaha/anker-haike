"""Only grounded diagnostic facts can justify quality; default unknown."""

from app.conversation.operation_conditions import feedback_history

DAMAGE_WORDS = ("摔", "进水", "宠物咬", "人为损坏", "跌落")


def derive_fault_class(state: dict) -> str:
    risks = state.get("risk_cases") or []
    if isinstance(risks, dict):
        risks = risks.values()
    if any(r.get("rule_id") == "R4" and r.get("status") == "reported" for r in risks):
        return "safety"
    notes = (
        " ".join(str(s.get("note", "")) for s in feedback_history(state))
        + " "
        + " ".join(str(f.get("value", "")) for f in ((state.get("issues") or {}).get(state.get("active_issue_id"), {}).get("facts", [])) if f.get("status") in {"active", "disputed"})
        + " " + " ".join(str(s) for s in state.get("symptoms", []))
    )
    if any(word in notes for word in DAMAGE_WORDS):
        return "user_damage"
    diagnosis = state.get("diagnose_outcome") or {}
    if diagnosis.get("mode") == "evidence" and diagnosis.get("plan_id") in {
        "rv_suction_hair_wrap",
        "rv_suction_filter_clog",
        "rv_suction_dustbin_full",
        "rv_suction_side_brush",
    }:
        return "quality"
    return "unknown"
