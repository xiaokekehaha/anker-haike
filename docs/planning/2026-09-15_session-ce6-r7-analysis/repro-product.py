"""Offline single-variable probes of the 9db product clarification decision."""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "orchestrator"))
from app.sessions.cards import get_plans
from app.sessions.clarify import decide, fixed_question

state = json.loads(Path(sys.argv[1]).read_text())
before = decide(copy.deepcopy(state), abandoned_card=None)
assert before.outcome == "escalate" and before.update["escalate_reason"] == "R7"

corrected_count = copy.deepcopy(state)
corrected_count["clarification"]["attempts"] = 1
after_count = decide(corrected_count, abandoned_card=None)
assert after_count.outcome == "clarify" and after_count.reason == "product"

# Counterfactual only: a category must first be established from user/image
# evidence in production. This does not validate x00001 or edit session state.
known_category = copy.deepcopy(state)
known_category["category"] = "robot_vacuum"
after_category = decide(known_category, abandoned_card=None)
assert after_category.outcome == "continue"
assert after_category.update["product_state"] == "category_only"
plans = get_plans().allowed_for(category="robot_vacuum", symptom_codes=["abnormal_noise"])
assert plans

print(json.dumps({
    "session_id": "9db433aece2d47378f9ce8bbeb0701e4",
    "before": {"outcome": before.outcome, "reason": before.reason,
               "attempts": state["clarification"]["attempts"]},
    "correct_count_only": {"outcome": after_count.outcome,
                           "fallback_question": fixed_question(after_count.reason, after_count.detail)},
    "hypothetical_verified_category_only": {
        "outcome": after_category.outcome,
        "product_state": after_category.update["product_state"],
        "symptom_codes": after_category.update["symptom_codes"],
        "applicable_noise_plan_count": len(plans),
    },
}, ensure_ascii=False, indent=2))
