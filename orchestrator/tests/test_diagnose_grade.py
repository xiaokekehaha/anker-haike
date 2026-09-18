"""充分性评估：白名单、评分不删除候选、补查决策与失败回退。"""

from __future__ import annotations

import json

from app.diagnose.grade import (
    EvidenceAssessment,
    GradeItem,
    GradeResult,
    apply_assessment,
    normalize_result,
)
from app.knowledge.adapter import Hit, ToolResult
from tests.test_diagnose import (
    NO_MATCH,
    OK_HAIR,
    ScriptedAdapter,
    _rcfg,
    hit,
    make_router,
    run_text,
)


def _h(eid: str, score: float, *, counter: bool = False) -> Hit:
    return Hit(
        eid, "k", eid, "manual_rv_v1", "v", "kb_manual", f"s-{eid}", score, counter_evidence=counter
    )


def test_normalize_whitelists_ids_and_falls_back_on_bad_enums():
    raw = GradeResult(
        items=[
            GradeItem(evidence_id="a", verdict="Relevant "),
            GradeItem(evidence_id="b", verdict="nope"),
            GradeItem(evidence_id="zz", verdict="relevant"),  # 不在输入集合
            GradeItem(evidence_id="a", verdict="irrelevant"),  # 重复取首个
        ],
        coverage="SUFFICIENT",
    )
    verdicts, cov = normalize_result(raw, ["a", "b", "c"])
    assert verdicts == {"a": "relevant", "b": "unsure", "c": "unsure"} and cov == "sufficient"
    # 无 relevant 却说 sufficient → 保守降级；非法 coverage → unknown
    v2, c2 = normalize_result(GradeResult(items=[], coverage="sufficient"), ["a"])
    assert v2 == {"a": "unsure"} and c2 == "insufficient"
    assert normalize_result(GradeResult(items=[], coverage="???"), ["a"])[1] == "unknown"


def test_assessment_keeps_misclassified_candidates_and_counter_evidence():
    hits = [_h("a", 0.9), _h("b", 0.8), _h("t", 0.95, counter=True), _h("c", 0.1)]
    kept = apply_assessment(
        hits, EvidenceAssessment("graded", verdicts={"a": "irrelevant", "b": "relevant", "t": "unsure"})
    )
    assert [h.evidence_id for h in kept] == ["a", "b", "t", "c"]
    assert hits[0].grade == "irrelevant" and hits[1].grade == "relevant"
    assert apply_assessment(hits, EvidenceAssessment("ungraded")) == hits


GRADE_ALL_IRRELEVANT = json.dumps(
    {
        "items": [
            {"evidence_id": "c12", "verdict": "irrelevant"},
            {"evidence_id": "c15", "verdict": "irrelevant"},
        ],
        "coverage": "none",
    }
)
GRADE_PARTIAL = json.dumps(
    {
        "items": [
            {"evidence_id": "c12", "verdict": "relevant"},
            {"evidence_id": "c15", "verdict": "irrelevant"},
        ],
        "coverage": "sufficient",
    }
)
INTAKE = json.dumps(
    {
        "emotion_level": "calm",
        "product_hints": ["X9 Pro"],
        "symptoms": ["不吸"],
        "wants_human": False,
    },
    ensure_ascii=False,
)
SYNTH = json.dumps(
    {
        "hypotheses": [
            {"plan_id": "rv_suction_hair_wrap", "confidence": 0.8, "evidence_ids": ["c12"]}
        ]
    }
)


def _cfg(**grade):
    cfg = _rcfg(enabled=False)
    cfg.grade = cfg.grade.model_copy(update={"enabled": True, **grade})
    return cfg


async def test_grade_keeps_irrelevant_in_synthesize_and_records_assessed_ids(mem_runtime, tmp_path):
    router, fakes = make_router(
        tmp_path, fast=[INTAKE, GRADE_PARTIAL], main=[SYNTH, ["清理滚刷。"]]
    )
    adapter = ScriptedAdapter({"kb_manual": [OK_HAIR()], "kb_tickets": [NO_MATCH()]})
    events, values = await run_text(router, adapter, "eufy X9 Pro 不吸了", rcfg=_cfg())
    tr = next(t for t in values["retrieval_trace"] if t.get("event") == "grade_result")
    assert (
        tr["status"] == "graded"
        and tr["coverage"] == "sufficient"
        and tr["evaluated_ids"] == ["c12", "c15"]
    )
    assert values["evidence_quality"] == "sufficient" and values["knowledge_status"] == "ok"
    assert values["retrieval_rounds"] == 1  # 有相关证据，不补检索
    scall = next(c for c in fakes["main"].calls if c["metadata"]["task"] == "diagnose.synthesize")
    human = next(m for m in scall["messages"] if getattr(m, "type", "") == "human").content
    assert "[c12]" in human and "[c15]" in human  # 误评的候选仍可参与综合判断
    ev = next(e for e in events if e["type"] == "evidence")
    assert {i["evidence_id"] for i in ev["items"]} == {
        "c12",
        "c15",
    }  # SSE 证据仍是原始命中（评分不是证据）
    gcall = next(c for c in fakes["fast"].calls if c["metadata"]["task"] == "retrieve.grade")
    ghuman = next(m for m in gcall["messages"] if getattr(m, "type", "") == "human").content
    assert "[c12]" in ghuman and "[c15]" in ghuman and "relevant|irrelevant|unsure" in ghuman


async def test_all_irrelevant_counts_as_no_relevant_and_triggers_rewrite(mem_runtime, tmp_path):
    rewrite = json.dumps({"query": "扫地机器人 不吸 吸力下降"}, ensure_ascii=False)  # 保留否定词，「吸力下降」为已审核同义
    router, fakes = make_router(
        tmp_path, fast=[INTAKE, GRADE_ALL_IRRELEVANT, rewrite], main=[SYNTH, ["清理滚刷。"]]
    )
    # 首轮命中但评分全不相关 → 视同无相关证据 → 一次改写补检索 → 第二轮命中并入
    second = ToolResult(
        "ok", [hit("c12", "manual_rv_v1", "翻转主机取出滚刷", 0.7)], allowed_count=2
    )
    adapter = ScriptedAdapter(
        {
            "kb_manual": [
                ToolResult(
                    "ok",
                    [
                        hit("c15", "manual_rv_v1", "滤网清洗", 0.5),
                        hit("c12", "manual_rv_v1", "滚刷", 0.4),
                    ],
                    allowed_count=2,
                ),
                second,
            ],
            "kb_tickets": [NO_MATCH(), NO_MATCH()],
        }
    )
    cfg = _cfg()
    cfg.query_rewrite = cfg.query_rewrite.model_copy(update={"enabled": True})
    _, values = await run_text(router, adapter, "eufy X9 Pro 不吸了", rcfg=cfg)
    dec = next(t for t in values["retrieval_trace"] if t.get("event") == "rewrite_decision")
    assert dec["triggered"] is True
    rw = next(t for t in values["retrieval_trace"] if t.get("event") == "rewrite_result")
    assert values["retrieval_rounds"] == 2 and values["rewrite_used"] is True, rw.get("rejected_reason")
    assert values["knowledge_status"] == "ok"  # 实际检索有命中，状态不伪装成 no_match
    assert values["evidence_quality"] == "none"
    tasks = [c["metadata"]["task"] for c in fakes["fast"].calls]
    assert tasks == ["intake", "retrieve.grade", "query.rewrite"]  # 第二轮默认不再评分
    grades = [t for t in values["retrieval_trace"] if t.get("event") == "grade_result"]
    assert len(grades) == 1 and grades[0]["evaluated_ids"] == ["c15", "c12"]


async def test_grade_model_failure_is_ungraded_and_flow_continues(mem_runtime, tmp_path):
    router, _ = make_router(
        tmp_path, fast=[INTAKE], main=[SYNTH, ["清理滚刷。"]]
    )  # grade 无脚本 → 失败
    adapter = ScriptedAdapter({"kb_manual": [OK_HAIR()], "kb_tickets": [NO_MATCH()]})
    _, values = await run_text(router, adapter, "eufy X9 Pro 不吸了", rcfg=_cfg())
    tr = next(t for t in values["retrieval_trace"] if t.get("event") == "grade_result")
    assert tr["status"] == "ungraded" and tr["reason"].startswith("model:")
    assert values["evidence_quality"] is None and values["knowledge_status"] == "ok"
    assert values["plans_ranked"][0]["plan_id"] == "rv_suction_hair_wrap"


async def test_grade_skipped_when_budget_low_or_disabled(mem_runtime, tmp_path):
    router, fakes = make_router(tmp_path, fast=[INTAKE], main=[SYNTH, ["清理滚刷。"]])
    adapter = ScriptedAdapter({"kb_manual": [OK_HAIR()], "kb_tickets": [NO_MATCH()]})
    _, values = await run_text(router, adapter, "eufy X9 Pro 不吸了", rcfg=_rcfg(enabled=False))
    assert not any(t.get("event") == "grade_result" for t in values["retrieval_trace"])
    assert [c["metadata"]["task"] for c in fakes["fast"].calls] == ["intake"]
    router2, fakes2 = make_router(tmp_path, fast=[INTAKE], main=[SYNTH, ["清理滚刷。"]])
    adapter2 = ScriptedAdapter({"kb_manual": [OK_HAIR()], "kb_tickets": [NO_MATCH()]})
    _, values2 = await run_text(
        router2, adapter2, "eufy X9 Pro 不吸了", rcfg=_cfg(min_remaining_ms=10**9)
    )
    tr = next(t for t in values2["retrieval_trace"] if t.get("event") == "grade_result")
    assert tr["status"] == "skipped" and tr["reason"].startswith("budget")
    assert [c["metadata"]["task"] for c in fakes2["fast"].calls] == ["intake"]
