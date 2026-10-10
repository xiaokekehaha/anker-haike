"""非 intake 任务的会话状态只投影模型用得上的字段（2026-10-10，T55 复测退步）。

T55 补照片那一轮重新诊断时，diagnose.synthesize 的 authority 达 10.1k token（预算 7.0k）：facts 带 fact_id /
device_ref_id / source_entry_ids / recorded_at 等存储字段，step_attempts 带 card_id / instruction_src / ts。
这些字段模型不读；一旦事实或证据多一点就超预算，候选为空直接 R5。intake 要靠 fact_id 做 corrections，保持完整。
"""

from __future__ import annotations

import json

from app.context.builder import _model_authority, estimate_tokens

FACT = {
    "fact_id": "daaf35c844cb5247b38ad7f30dfba971", "kind": "symptom", "context_field": None, "value": "Battery abnormal",
    "issue_id": "b5acc535f9f55b42ae12f6cd54aff05e", "device_ref_id": "4d15694cd8a15784a4938101820e7c8d", "status": "active",
    "revision": 1, "source_kind": "user_report", "source": "device_message", "subject": None, "polarity": "affirmed",
    "timing": None, "source_entry_ids": ["fbf06baa39be432e9280af532aa3e07b"], "recorded_at": "2026-10-09T13:19:05.102015+00:00",
    "occurred_at": None, "time_expression": None, "precision": None, "quote": "E41: Battery abnormal, task ended.",
}
STEP = {
    "plan_id": "qa_bp_0102", "step_id": "s1", "card_id": "f4ecf270fc295aaaa8ef6ae491a3ac7f", "title": "Restore factory settings:",
    "instruction_src": "evidence:bp-0102#s1", "kind": "action", "feedback": "not_solved", "note": None, "answer": None,
    "ts": "2026-10-10T01:30:23.195382+00:00",
}


def test_synthesize_authority_keeps_model_fields_and_drops_storage_fields():
    out = _model_authority({"facts": [FACT], "step_attempts": [STEP], "decision": {"patches": [1], "primary_intent": "report_problem"}}, "diagnose.synthesize")
    assert out["facts"] == [{"fact_id": FACT["fact_id"], "kind": "symptom", "value": "Battery abnormal", "status": "active",
                             "source": "device_message", "polarity": "affirmed", "quote": FACT["quote"]}]
    assert out["step_attempts"] == [{"plan_id": "qa_bp_0102", "step_id": "s1", "title": "Restore factory settings:",
                                     "kind": "action", "feedback": "not_solved"}]
    assert "patches" not in out["decision"]
    full = estimate_tokens(json.dumps([FACT] * 12 + [STEP] * 3, ensure_ascii=False, separators=(",", ":")))
    slim = estimate_tokens(json.dumps(out["facts"] * 12 + out["step_attempts"] * 3, ensure_ascii=False, separators=(",", ":")))
    assert slim < full * 0.5


def test_intake_authority_keeps_full_fact_records_for_corrections():
    out = _model_authority({"facts": [FACT], "step_attempts": [STEP], "decision": {}}, "intake")
    assert out["facts"][0]["fact_id"] == FACT["fact_id"] and out["facts"][0]["source_entry_ids"] == FACT["source_entry_ids"]
    assert out["step_attempts"][0]["card_id"] == STEP["card_id"]
