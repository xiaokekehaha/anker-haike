"""Replay the recorded reader boundary; --expect-success exposes the symptom."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "orchestrator"))
from app.conversation.reader import read_history_for_turn, select_history

fixture = json.loads(Path(__file__).with_name("reader-replay.json").read_text())
entries, request, seq = fixture["entries"], fixture["request"], fixture["before_seq"]
result = select_history(entries, request, before_seq=seq)
print("recorded_request:", json.dumps(result, ensure_ascii=False))
if "--check-fixed" in sys.argv:
    # Actual preceding query used recent, not a unique reference. Clarify safely.
    previous_input = next(e for e in entries if e["first_seq"] == 158)
    previous = select_history(entries, {"mode": "recent"}, before_seq=158)
    state = {
        "history": entries, "input_seq": seq,
        "input_id": request["source_entry_ids"][0],
        "turn_decision": {"input_id": previous_input["entry_id"], "primary_intent": "history_query"},
        "recall_entry_ids": previous["source_entry_ids"],
    }
    fixed = read_history_for_turn(state, request)
    assert fixed["error_code"] == "history_target_unresolved"
    assert "原始记录目前不可用" not in fixed["error"]
    print("fixed_actual_request:", json.dumps(fixed, ensure_ascii=False))
    # When the preceding query pinpoints its question, self-reference can recover.
    state["recall_entry_ids"] = select_history(entries, {
        "mode": "reference", "source_entry_ids": [e["entry_id"] for e in entries if e["first_seq"] == 147]
    }, before_seq=158)["source_entry_ids"]
    recovered = read_history_for_turn(state, request)
    assert recovered["error"] is None
    assert recovered["source_entry_ids"] == state["recall_entry_ids"]
    print("fixed_unique_target:", json.dumps(recovered, ensure_ascii=False))
elif "--expect-success" in sys.argv:
    assert result["error"] is None, result["error"]
else:
    assert result["error"] == "这部分原始记录目前不可用，无法确认当时的原话。"
    current = next(e for e in entries if e["entry_id"] == request["source_entry_ids"][0])
    assert current["first_seq"] == seq
    assert result["missing_ids"] == [current["entry_id"]]
    prior = next(e for e in entries if e["first_seq"] == 147)
    changed_reference = select_history(entries, {"mode": "reference", "source_entry_ids": [prior["entry_id"]]}, before_seq=seq)
    assert changed_reference["error"] is None
    print("prior_question_reference:", json.dumps(changed_reference, ensure_ascii=False))
    recent = select_history(entries, {"mode": "recent"}, before_seq=seq)
    assert recent["error"] is None
    print("recent: error=None, selected=", len(recent["source_entry_ids"]))
    # Counterfactual probe only: never relax the production causal boundary.
    advanced_cutoff = select_history(entries, request, before_seq=seq + 1)
    assert advanced_cutoff["error"] is None
    print("advanced_cutoff: current question becomes selectable; this is not a fix")
