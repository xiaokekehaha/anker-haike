"""haike-kb eval（阶段 2）：样例 → state / scope / query；打分与汇总的纯函数。"""

from __future__ import annotations

from app.diagnose.query import build_query
from app.knowledge.adapter import Hit, ToolResult
from app.knowledge.eval import (
    case_scope,
    case_state,
    merge_top_k,
    render_markdown,
    score_case,
    summarize,
)


def _hit(eid: str, doc: str, score: float, *, kb: str = "kb_manual", counter: bool = False) -> Hit:
    h = Hit(eid, "k", eid, doc, "v", kb, "s", score, counter_evidence=counter)
    h.case_outcome = "unsolved" if counter else ("solved" if kb == "kb_tickets" else "n/a")
    return h


def test_case_state_and_scope_confirmed_and_category_only():
    c = {
        "id": "x",
        "product_state": "confirmed_sku",
        "sku": "EUFY-X9-PRO",
        "category": "robot_vacuum",
        "text": "不吸",
        "symptoms": ["不吸"],
    }
    st, sc = case_state(c), case_scope(c)
    assert (
        sc.product_state == "confirmed_sku"
        and sc.sku == "EUFY-X9-PRO"
        and sc.category == "robot_vacuum"
    )
    assert build_query(st) == "EUFY-X9-PRO 不吸"
    c2 = {
        "id": "y",
        "product_state": "category_only",
        "category": "robot_vacuum",
        "text": "扫地机不吸",
        "symptoms": [],
    }
    st2, sc2 = case_state(c2), case_scope(c2)
    assert sc2.sku is None and build_query(st2) == "扫地机器人 扫地机不吸"  # 症状为空退回原文


def test_merge_top_k_puts_counter_evidence_last_and_caps():
    results = {
        "kb_manual": ToolResult(
            "ok", [_hit("c12", "manual_rv_v1", 0.9), _hit("c15", "manual_rv_v1", 0.5)]
        ),
        "kb_tickets": ToolResult(
            "ok",
            [
                _hit("T1", "T0001", 0.95, kb="kb_tickets", counter=True),
                _hit("T2", "T0002", 0.7, kb="kb_tickets"),
            ],
        ),
    }
    top = merge_top_k(results, 3)
    # 跨库按库内名次交错（手册优先破平），反证 T1 虽分高仍排最后并被截掉
    assert [h.evidence_id for h in top] == ["c12", "c15", "T2"]


def test_score_case_hit_precision_rank_and_leak():
    hits = [
        _hit("a", "manual_rv_v1", 0.9),
        _hit("b", "T0009", 0.8),
        _hit("c", "troubleshooting_rv", 0.7),
    ]
    s = score_case({"expected_doc_ids": ["troubleshooting_rv", "T0001"]}, hits)
    assert s["hit"] is True and s["first_rank"] == 3 and abs(s["precision"] - 1 / 3) < 1e-9
    s2 = score_case({"expected_doc_ids": ["faq_rv"]}, hits)
    assert s2["hit"] is False and s2["first_rank"] is None and s2["precision"] == 0.0
    s3 = score_case({"expected_doc_ids": []}, hits)
    assert s3["leak"] is True and "hit" not in s3
    assert score_case({"expected_doc_ids": []}, [])["leak"] is False


def test_summarize_and_render():
    rows = [
        {
            "id": "a",
            "tags": ["口语"],
            "query": "q",
            "status": "ok",
            "hit": True,
            "precision": 0.5,
            "first_rank": 1,
            "doc_ids": ["m"],
            "latency_ms": 100,
        },
        {
            "id": "b",
            "tags": ["口语", "否定"],
            "query": "q",
            "status": "no_match",
            "hit": False,
            "precision": 0.0,
            "first_rank": None,
            "doc_ids": [],
            "latency_ms": 300,
        },
        {
            "id": "c",
            "tags": ["无知识"],
            "query": "q",
            "status": "ok",
            "leak": True,
            "doc_ids": ["m"],
            "latency_ms": 200,
        },
        {
            "id": "d",
            "tags": [],
            "query": "",
            "status": "no_query",
            "leak": False,
            "doc_ids": [],
            "latency_ms": 0,
        },
    ]
    s = summarize(rows, top_k=5)
    assert (
        s["cases"] == 4 and s["scored"] == 2 and s["hit@5"] == "50%" and s["precision@5"] == "25%"
    )
    assert (
        s["leak"] == "1/2"
        and s["no_match"] == 1
        and s["latency_p50_ms"] == 200
        and s["latency_p95_ms"] == 300
    )
    assert s["by_tag"]["口语"] == {"n": 2, "hit@5": "50%"} and s["by_tag"]["否定"]["hit@5"] == "0%"
    md = render_markdown(
        arm="A", cases_meta={"version": "v1", "annotated_count": 0}, summary=s, rows=rows, top_k=5
    )
    assert "| hit@5 | 50% |" in md and "| c | ok | leak |" in md and "| d | no_query | - |" in md
