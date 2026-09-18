"""有界 Agentic RAG 阶段 1（P0）：两库并发、补检索整轮硬超时、两轮合并、工单结果进 synthesize。
设计见 docs/planning/2026-09-13_bounded-agentic-rag/design.md §2。"""

from __future__ import annotations

import asyncio
import json
import time

from app.diagnose.synthesize import synthesize
from app.knowledge.adapter import HINTS, Hit, KnowledgeScope, ToolResult, case_outcome_of
from app.knowledge.context import OUTCOME_LABELS
from app.plans.library import PlanLibrary, load_plans_config
from app.sessions.graph import _merge_rounds, _search_round
from app.settings import REPO_ROOT
from tests.test_diagnose import (
    NO_MATCH,
    OK_HAIR,
    ScriptedAdapter,
    _rcfg,
    hit,
    make_router,
    run_text,
)

SCOPE = KnowledgeScope("confirmed_sku", "robot_vacuum", "EUFY-X9-PRO")


class SlowAdapter(ScriptedAdapter):
    """每次请求固定延迟；after_calls 之后的请求用 slow_s（模拟第二轮变慢）。"""

    def __init__(self, plan, *, delay_s: float, slow_s: float | None = None, after_calls: int = 0):
        super().__init__(plan)
        self.delay_s, self.slow_s, self.after_calls = delay_s, slow_s, after_calls
        self.started: list[float] = []

    async def hybrid_search(self, kb, query, top_k, allow):
        self.started.append(time.perf_counter())
        n = len(self.calls)
        await asyncio.sleep(
            self.slow_s if self.slow_s is not None and n >= self.after_calls else self.delay_s
        )
        return await super().hybrid_search(kb, query, top_k, allow)


# ---- P0-1 两库并发 ----


async def test_search_round_runs_two_kbs_concurrently_and_keeps_trace_order():
    adapter = SlowAdapter({"kb_manual": [OK_HAIR()], "kb_tickets": [NO_MATCH()]}, delay_s=0.25)
    t0 = time.perf_counter()
    results, traces = await _search_round(
        adapter, "q", SCOPE, 5, round_no=1, session_id="s", run_id="r"
    )
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.45, f"two kbs must overlap, took {elapsed:.2f}s"  # 串行会 ≥ 0.5 s
    assert abs(adapter.started[0] - adapter.started[1]) < 0.1  # 几乎同时发出
    assert [t["kb"] for t in traces] == ["kb_manual", "kb_tickets"]  # trace 顺序固定
    assert results["kb_manual"].status == "ok" and results["kb_tickets"].status == "no_match"
    assert all(h.round == 1 for h in results["kb_manual"].hits)


# ---- P0-3 两轮合并 ----


def _res(status: str, hits: list[Hit] | None = None, truncated: bool = False) -> ToolResult:
    return ToolResult(status, hits or [], truncated=truncated, allowed_count=2)


def test_merge_rounds_dedupes_by_evidence_id_and_takes_better_status():
    first = [hit("c12", "manual_rv_v1", "滚刷")]
    results = {"kb_manual": _res("ok", first), "kb_tickets": _res("unavailable")}
    c15 = hit("c15", "manual_rv_v1", "滤网")
    c15.round = 2
    dup = hit("c12", "manual_rv_v1", "滚刷（第二轮重复）")
    results2 = {"kb_manual": _res("ok", [dup, c15], truncated=True), "kb_tickets": _res("no_match")}
    merged, status, truncated = _merge_rounds(first, results, results2)
    assert [h.evidence_id for h in merged] == ["c12", "c15"]
    assert merged[0].snippet == "滚刷" and merged[1].round == 2  # 首轮优先，不被第二轮覆盖
    assert status == {"kb_manual": "ok", "kb_tickets": "no_match"}
    assert truncated is True


def test_merge_rounds_keeps_first_round_when_second_is_empty():
    first = [hit("c12", "manual_rv_v1", "滚刷")]
    results = {"kb_manual": _res("ok", first), "kb_tickets": _res("no_match")}
    results2 = {"kb_manual": _res("no_match"), "kb_tickets": _res("no_match")}
    merged, status, _ = _merge_rounds(first, results, results2)
    assert [h.evidence_id for h in merged] == ["c12"] and status["kb_manual"] == "ok"


# ---- P0-2 补检索整轮硬超时 ----


async def test_second_round_timeout_keeps_first_round_and_records_trace(mem_runtime, tmp_path):
    intake = json.dumps(
        {
            "emotion_level": "calm",
            "product_hints": ["X9 Pro"],
            "primary_intent": "report_problem",
            "device_relation": "current",
            "facts": [{"value": "跑完了地上还是一堆渣", "quote": "地上还是一堆渣", "symptom_code": "suction_low"}],
        },
        ensure_ascii=False,
    )
    rewrite = json.dumps({"query": "扫地机器人 清扫后残留碎屑 清洁效果差"}, ensure_ascii=False)
    router, _fakes = make_router(tmp_path, fast=[intake, rewrite], main=[["清理滚刷。"]])
    # 首轮两库都 no_match → 触发改写 → 第二轮每个请求 1.2 s，整轮预算 500 ms → 超时
    adapter = SlowAdapter(
        {"kb_manual": [NO_MATCH(), OK_HAIR()], "kb_tickets": [NO_MATCH(), NO_MATCH()]},
        delay_s=0.0,
        slow_s=1.2,
        after_calls=2,
    )
    cfg = _rcfg(enabled=True)
    cfg.retrieval = cfg.retrieval.model_copy(update={"second_round_budget_ms": 500})
    t0 = time.perf_counter()
    events, values = await run_text(
        router, adapter, "eufy X9 Pro 它跑完了，地上还是一堆渣", rcfg=cfg
    )
    assert time.perf_counter() - t0 < 5
    timeout = [t for t in values["retrieval_trace"] if t.get("event") == "second_round_timeout"]
    assert len(timeout) == 1 and timeout[0]["reason"] == "query_rewrite"
    assert timeout[0]["budget_ms"] == 500
    # 第二轮结果未被采用：知识状态仍为首轮的 no_match，名额已用、轮次记 2、不再第三轮
    assert values["knowledge_status"] == "no_match"
    assert values["retrieval_rounds"] == 2 and values["rewrite_used"] is True
    assert len(adapter.started) == 4 and len(adapter.calls) == 2  # 第二轮两请求被取消，未完成
    assert values["plans_ranked"][0]["source"] == "standard_flow"
    tool = [e for e in events if e["type"] == "tool_call"]
    assert tool[-1]["status"] == "finished" and "未找到匹配知识" in tool[-1]["summary"]


async def test_second_round_within_budget_merges_and_marks_round(mem_runtime, tmp_path):
    intake = json.dumps(
        {
            "emotion_level": "calm",
            "product_hints": ["X9 Pro"],
            "primary_intent": "report_problem",
            "device_relation": "current",
            "facts": [{"value": "跑完了地上还是一堆渣", "quote": "地上还是一堆渣", "symptom_code": "suction_low"}],
        },
        ensure_ascii=False,
    )
    rewrite = json.dumps({"query": "扫地机器人 清扫后残留碎屑 清洁效果差"}, ensure_ascii=False)
    synth = json.dumps(
        {
            "hypotheses": [
                {"plan_id": "rv_suction_hair_wrap", "confidence": 0.7, "evidence_ids": ["c12"]}
            ]
        }
    )
    router, fakes = make_router(tmp_path, fast=[intake, rewrite], main=[synth, ["清理滚刷。"]])
    adapter = ScriptedAdapter(
        {"kb_manual": [NO_MATCH(), OK_HAIR()], "kb_tickets": [NO_MATCH(), NO_MATCH()]}
    )
    _events, values = await run_text(
        router, adapter, "eufy X9 Pro 它跑完了，地上还是一堆渣", rcfg=_rcfg(enabled=True)
    )
    assert values["knowledge_status"] == "ok" and values["retrieval_rounds"] == 2
    r2 = [
        t for t in values["retrieval_trace"] if t.get("round") == 2 and t.get("kb") == "kb_manual"
    ]
    assert r2 and r2[0]["reason"] == "query_rewrite" and r2[0]["hit_ids"] == ["c12", "c15"]
    assert not any(t.get("event") == "second_round_timeout" for t in values["retrieval_trace"])
    # synthesize 看到的证据带轮次与工单结果字段
    scall = next(c for c in fakes["main"].calls if c["metadata"]["task"] == "diagnose.synthesize")
    human = next(m for m in scall["messages"] if getattr(m, "type", "") == "human").content
    assert "[c12] (kb_manual)" in human  # 手册不加工单标签


# ---- P0-4 工单结果进 synthesize ----


def test_case_outcome_mapping_and_internal_item():
    assert case_outcome_of("kb_manual", "unsolved") == "n/a"
    assert case_outcome_of("kb_tickets", "solved") == "solved"
    assert case_outcome_of("kb_tickets", "escalated") == "unsolved"
    assert case_outcome_of("kb_tickets", None) == "unknown"
    h = Hit("t1", "k", "t1", "T0015", "v", "kb_tickets", "噪音变大", 0.5, counter_evidence=True)
    h.case_outcome, h.round = "unsolved", 2
    item, internal = h.as_evidence_item(), h.as_internal_item()
    assert "case_outcome" not in item and "round" not in item  # 契约形状不变
    assert internal["case_outcome"] == "unsolved" and internal["round"] == 2
    assert {k: v for k, v in internal.items() if k not in ("case_outcome", "round")} == item


async def test_synthesize_prompt_labels_unsolved_tickets(tmp_path):
    synth = json.dumps(
        {
            "hypotheses": [
                {"plan_id": "rv_suction_hair_wrap", "confidence": 0.6, "evidence_ids": ["c12"]}
            ]
        }
    )
    router, fakes = make_router(tmp_path, fast=[], main=[synth])
    lib = PlanLibrary(load_plans_config(REPO_ROOT / "config" / "plans.yaml"))
    allowed = lib.allowed_for(category="robot_vacuum", sku="EUFY-X9-PRO")
    evidence = [
        {
            **hit("c12", "manual_rv_v1", "翻转主机取出滚刷").as_evidence_item(),
            "case_outcome": "n/a",
        },
        {
            "evidence_id": "T0015",
            "source": "kb_tickets",
            "doc_id": "T0015",
            "doc_version": "v",
            "chunk_id": "T0015",
            "snippet": "噪音变大吸力弱；吸口卡异物；未解决",
            "score": 0.5,
            "status": "ok",
            "case_outcome": "unsolved",
        },
        {
            "evidence_id": "T0001",
            "source": "kb_tickets",
            "doc_id": "T0001",
            "doc_version": "v",
            "chunk_id": "T0001",
            "snippet": "吸力变小；滚刷毛发缠绕；已解决",
            "score": 0.4,
            "status": "ok",
            "case_outcome": "solved",
        },
    ]
    out = await synthesize(
        router,
        state={"text": "不吸了", "symptoms": ["不吸"], "product_confirmed": {"name": "X9"}},
        allowed=allowed,
        evidence=evidence,
        observations=[],
        budget_ms=3000,
        max_hypotheses=3,
        session_id="s",
        lane="domestic",
    )
    assert out["plans_ranked"][0]["plan_id"] == "rv_suction_hair_wrap"
    human = next(m for m in fakes["main"].calls[0]["messages"] if m.type == "human").content
    assert f"[T0015] (kb_tickets{OUTCOME_LABELS['unsolved']})" in human
    assert f"[T0001] (kb_tickets{OUTCOME_LABELS['solved']})" in human
    assert "[c12] (kb_manual)" in human
    assert "未解决工单」的片段只说明该次服务未确认解决" in human
    assert HINTS  # 引用保持导入有效
