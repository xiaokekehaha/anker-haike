"""票 32：查询规范化、无命中改写决策与校验、synthesize 过滤，以及图内 A1 流水线（假 router + 假适配器）。"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.diagnose import (
    build_query,
    get_retrieval_config,
    normalize_query,
    should_rewrite,
    validate_rewrite,
)
from app.diagnose.config import RetrievalConfig, set_retrieval_config
from app.diagnose.synthesize import filter_hypotheses
from app.knowledge.adapter import HINTS, Hit, ToolResult
from app.knowledge.runtime import set_knowledge_adapter
from app.main import app
from app.models.config import load_models_config
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter
from app.models.runtime import set_model_router
from app.plans import PlanLibrary
from app.rules import RulesService, set_rules_service
from app.sessions import sse
from app.settings import REPO_ROOT
from tests.message_form import message_form, model_task_text
from tests.scripted_model import ScriptedSemanticModel as FakeChatModel
from tests.test_reply_stream import CONFIG as REPLY_CONFIG

RULES = REPO_ROOT / "config" / "rules" / "safety_terms.yaml"
LIB = PlanLibrary.from_yaml(REPO_ROOT / "config" / "plans.yaml")
X9 = {"sku": "EUFY-X9-PRO", "name": "eufy X9 Pro", "category": "robot_vacuum", "in_scope": True}
CFG_RW = get_retrieval_config().query_rewrite


# ---- 1.4.1 查询规范化 ----


def test_query_confirmed_sku_fixed_sample_is_stable():
    s = {
        "product_state": "confirmed_sku",
        "product_confirmed": X9,
        "symptoms": ["不吸了"],
        "text": "我的 X9 Pro 不吸了",
    }
    assert build_query(s) == build_query(dict(s)) == "eufy X9 Pro 不吸了"


def test_query_dedupe_and_whitespace_keep_negation_parts_codes():
    s = {
        "product_state": "confirmed_sku",
        "product_confirmed": X9,
        "symptoms": [" 滚刷  不转 ", "滚刷不转", "报 E12 错误", "不吸了，"],
        "text": "x",
    }
    q = build_query(s)
    assert q == "eufy X9 Pro 滚刷 不转 报 E12 错误 不吸了"
    assert "不" in q and "E12" in q and "滚刷" in q


def test_query_category_only_has_no_sku_and_unknown_is_empty():
    s = {
        "product_state": "category_only",
        "category": "robot_vacuum",
        "product_candidates": [X9],
        "symptoms": ["不吸了"],
        "text": "x",
    }
    q = build_query(s)
    assert q == "扫地机器人 不吸了" and "X9" not in q and "EUFY" not in q
    assert build_query({"product_state": "unknown", "symptoms": ["不吸了"], "text": "x"}) == ""


def test_query_falls_back_to_text_when_extraction_failed_and_empty_when_nothing():
    s = {
        "product_state": "confirmed_sku",
        "product_confirmed": X9,
        "symptoms": [],
        "text": "它跑完了，地上还是一堆渣",
    }
    assert build_query(s) == "eufy X9 Pro 它跑完了，地上还是一堆渣"
    assert (
        build_query(
            {
                "product_state": "confirmed_sku",
                "product_confirmed": X9,
                "symptoms": [],
                "text": "  ",
            }
        )
        == ""
    )
    assert normalize_query("  A  b ") == "a b"


# ---- 1.4.2 / 09 §4.1 改写决策 ----


def _decide(**kw):
    base = {
        "cfg": CFG_RW.model_copy(update={"enabled": True}),
        "per_kb_status": {"kb_manual": "no_match", "kb_tickets": "no_match"},
        "allowed_counts": {"kb_manual": 2, "kb_tickets": 30},
        "has_hits": False,
        "remaining_ms": 20000,
        "quota_used": False,
        "product_state": "confirmed_sku",
        "router_available": True,
    }
    base.update(kw)
    return should_rewrite(**base)


def test_rewrite_decision_table():
    assert _decide().triggered is True
    assert _decide(cfg=CFG_RW).reason == "disabled"  # 默认关闭
    assert _decide(has_hits=True, coverage="sufficient").reason == "sufficient"
    assert _decide(has_hits=True, coverage="insufficient").triggered
    assert _decide(has_hits=True, coverage="unknown").triggered
    assert (
        _decide(per_kb_status={"kb_manual": "no_match", "kb_tickets": "unavailable"}).reason
        == "unavailable"
    )
    assert _decide(allowed_counts={"kb_manual": 0, "kb_tickets": 0}).reason == "empty_scope"
    # 工单库允许集合为空、手册库真实无命中 → 只看实际请求的库 → 触发
    assert _decide(
        allowed_counts={"kb_manual": 2, "kb_tickets": 0},
        per_kb_status={"kb_manual": "no_match", "kb_tickets": "no_match"},
    ).triggered
    assert _decide(product_state="unknown").reason == "product_state"
    assert _decide(quota_used=True).reason == "quota_used"
    assert _decide(remaining_ms=7999).reason.startswith("budget")
    assert (
        _decide(in_clarify=True).reason == "state:clarify"
        and _decide(replay=True).reason == "state:replay"
        and _decide(cancelled=True).reason == "state:cancelled"
    )
    assert _decide(router_available=False).reason == "router_unavailable"


@pytest.mark.parametrize(
    ("candidate", "reason"),
    [
        ("", "empty"),
        ("扫地机器人 " * 60, "too_long"),
        ("eufy X9 Pro 它跑完了，地上还是一堆渣", "same_as_original"),
        ('{"query": "x", "sku": "EUFY"}', "contains_filter_or_structure"),
        ("扫地机器人 清扫后残留碎屑 L60", "new_model_token"),
        ("扫地机器人 清扫后残留碎屑 E12", "new_error_code"),
        ("扫地机器人 清扫后残留碎屑 电机损坏", "new_cause_or_action:电机"),
        ("扫地机器人 清扫后不残留碎屑", "negation_changed"),
        ("扫地机器人 清扫后残留碎屑 3 次", "new_number"),
        ("扫地机器人 清扫后残留碎屑 轮子打滑", "new_part:轮子"),  # 部件未经输入支持
        ("扫地机器人 清扫路线混乱", "lost_original_symptom"),  # 整体漂移到别的故障
    ],
)
def test_rewrite_validation_rejects(candidate, reason):
    original = "eufy X9 Pro 它跑完了，地上还是一堆渣"
    got = validate_rewrite(
        original, candidate, inputs="eufy X9 Pro 它跑完了，地上还是一堆渣", cfg=CFG_RW
    )
    assert got == reason or (got or "").startswith(reason.split(":")[0]), (candidate, got)


def test_rewrite_validation_accepts_natural_paraphrase_within_intent():
    """阶段 6：03 §1.4.2 只禁「新增部件 / 原因 / 操作」；自然连接词与同义表达应放行。"""
    original = "eufy L60 Hybrid 吸不起来东西"
    inputs = original + " 吸不起来 感觉吸不起来东西了"
    assert (
        validate_rewrite(original, "eufy L60 Hybrid 吸力不足无法吸尘", inputs=inputs, cfg=CFG_RW)
        is None
    )
    # 「不是 X，是 Y」纠正句式：丢掉被纠正的否定不算改变原意
    corr = "不是吸力小，是有异响"
    assert validate_rewrite(corr, "扫地机器人 异响", inputs=corr + " 异响", cfg=CFG_RW) is None
    # 但普通否定丢失仍然拒绝（滚刷「没」缠头发 → 缠头发是事实翻转）
    neg = "滚刷没缠头发，但还是不吸"
    assert validate_rewrite(neg, "滚刷缠头发", inputs=neg, cfg=CFG_RW) == "negation_changed"
    # anchors 不含产品词：只剩产品词的改写算漂移
    assert (
        validate_rewrite(
            "eufy X9 Pro 不吸",
            "eufy X9 Pro 基站不亮",
            inputs="eufy X9 Pro 不吸",
            cfg=CFG_RW,
            anchors="不吸",
        )
        == "new_part:基站"
    )
    # strict_terms=true 时回到早期严格模式
    strict = CFG_RW.model_copy(update={"strict_terms": True})
    assert (
        validate_rewrite(original, "eufy L60 Hybrid 吸力不足无法吸尘", inputs=inputs, cfg=strict)
        or ""
    ).startswith("unsupported_term")


def test_rewrite_validation_accepts_synonym_mapping():
    original = "eufy X9 Pro 它跑完了，地上还是一堆渣"
    assert (
        validate_rewrite(
            original,
            "扫地机器人 清扫后残留碎屑 清洁效果差",
            inputs=original + " 扫地机器人",
            cfg=CFG_RW,
        )
        is None
    )
    # 保留否定的改写
    assert (
        validate_rewrite(
            "eufy X9 Pro 不吸了",
            "扫地机器人 吸力下降 不吸",
            inputs="eufy X9 Pro 扫地机器人 不吸了",
            cfg=CFG_RW,
        )
        is None
    )


@pytest.mark.parametrize(("source", "candidate", "reason"), [
    ("滚刷没缠头发，但还是不吸", "滚刷缠头发 不吸", "negation_changed"),
    ("不是吸力小，是有异响", "扫地机器人 吸力小 异响", "corrected_fact_reintroduced"),
    ("刷子不转", "滚刷不转", "new_part:滚刷"),
])
def test_rewrite_preserves_local_negation_corrections_and_ambiguous_parts(source, candidate, reason):
    assert validate_rewrite(source, candidate, inputs=source, cfg=CFG_RW) == reason


# ---- synthesize 过滤 ----


def test_filter_hypotheses_drops_unknown_plan_and_invalid_evidence():
    allowed = {p.plan_id: p for p in LIB.allowed_for(category="robot_vacuum", sku="EUFY-X9-PRO")}
    raw = [
        {"plan_id": "rv_suction_hair_wrap", "confidence": 0.9, "evidence_ids": ["e1", "bogus"]},
        {"plan_id": "made_up_plan", "confidence": 0.8, "evidence_ids": ["e1"]},
        {"plan_id": "rv_suction_filter_clog", "confidence": 0.6, "evidence_ids": ["nope"]},
        {"plan_id": "rv_suction_hair_wrap", "confidence": 0.5, "evidence_ids": ["e1"]},
        {"plan_id": "rv_suction_dustbin_full", "confidence": 0.4, "evidence_ids": ["e2"]},
    ]
    kept, dropped = filter_hypotheses(raw, allowed=allowed, evidence_ids={"e1", "e2"}, max_n=3)
    assert [k["plan_id"] for k in kept] == ["rv_suction_hair_wrap", "rv_suction_dustbin_full"]
    assert (
        kept[0]["evidence_ids"] == ["e1"]
        and kept[0]["version"] == 1
        and kept[0]["source"] == "synthesize"
    )
    assert (
        "plan_id:made_up_plan" in dropped
        and "no_evidence:rv_suction_filter_clog" in dropped
        and "duplicate:rv_suction_hair_wrap" in dropped
    )


# ---- 图内流水线 ----


class ScriptedAdapter:
    """按 (kb, round) 返回预设结果；记录调用顺序与 query。"""

    def __init__(self, plan: dict[str, list[ToolResult]]):
        self.plan = plan
        self.calls: list[tuple[str, str]] = []

    async def hybrid_search(self, kb, query, top_k, allow):
        self.calls.append((kb, query))
        seq = self.plan.get(kb, [])
        r = (
            seq.pop(0)
            if seq
            else ToolResult("no_match", hint=HINTS["no_match"], kb=kb, query=query, allowed_count=1)
        )
        r.kb, r.query = kb, query
        return r


def hit(eid: str, doc: str, snippet: str, score: float = 0.4) -> Hit:
    return Hit(eid, "k-" + doc, eid, doc, "2026-09-12.1", "kb_manual", snippet, score)


OK_HAIR = lambda: ToolResult(
    "ok",
    [
        hit("c12", "manual_rv_v1", "翻转主机取出滚刷，割断缠绕的毛发"),
        hit("c15", "manual_rv_v1", "取出滤网清洗", 0.2),
    ],
    allowed_count=2,
)
NO_MATCH = lambda: ToolResult("no_match", hint=HINTS["no_match"], allowed_count=2)
EMPTY_SCOPE = lambda: ToolResult("no_match", hint=HINTS["no_match_empty_scope"], allowed_count=0)
UNAVAILABLE = lambda: ToolResult(
    "unavailable", hint=HINTS["unavailable"], allowed_count=2, detail="ConnectError"
)

INTAKE_X9 = json.dumps(
    {
        "emotion_level": "calm",
        "product_hints": ["X9 Pro"],
        "symptoms": ["不吸了", "滚刷缠头发"],
        "wants_human": False,
    },
    ensure_ascii=False,
)
SYNTH_HAIR = json.dumps(
    {
        "hypotheses": [
            {
                "plan_id": "rv_suction_hair_wrap",
                "confidence": 0.85,
                "evidence_ids": ["c12"],
                "rationale": "滚刷缠绕毛发",
            },
            {"plan_id": "rv_suction_filter_clog", "confidence": 0.4, "evidence_ids": ["c15"]},
            {
                "plan_id": "rv_battery_swap",
                "confidence": 0.9,
                "evidence_ids": ["c12"],
            },  # 不在枚举内 → 丢弃
        ]
    },
    ensure_ascii=False,
)


def make_router(tmp_path, *, fast: list, main: list):
    p = tmp_path / "models.yaml"
    p.write_text(
        REPLY_CONFIG.replace(
            "    escalate.summary:     {chain: [fast]}\n",
            "    escalate.summary:     {chain: [fast]}\n    query.rewrite:        {chain: [fast]}\n"
            "    retrieve.grade:       {chain: [fast]}\n",
        ),
        encoding="utf-8",
    )
    fakes = {
        "fast": FakeChatModel(script=list(fast), name_for_trace="fast"),
        "main": FakeChatModel(script=list(main), name_for_trace="main"),
        "backup": FakeChatModel(script=[]),
    }
    router = ModelRouter(
        ModelRegistry(load_models_config(p), env={"K1": "x", "K2": "x"}),
        model_factory=lambda r, _: fakes[r.alias],
    )
    return router, fakes


async def run_text(
    router, adapter, text: str, *, at: str | None = None, rcfg: RetrievalConfig | None = None
):
    set_model_router(router)
    set_knowledge_adapter(adapter)
    set_rules_service(RulesService(RULES, hot_reload=False))
    set_retrieval_config(rcfg)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            if (
                at is not None
            ):  # 模拟 run 已耗时：先塞一个 at 到 checkpoint 输入不可行，改用 runner 钩子
                from app.sessions import inputs as runner_mod

                orig = runner_mod.datetime

                class _Dt(datetime):
                    @classmethod
                    def now(cls, tz=None):
                        return datetime.fromisoformat(at)

                runner_mod.datetime = _Dt
            try:
                events = sse.parse(
                    (await client.post(f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": text}))).text
                )
            finally:
                if at is not None:
                    runner_mod.datetime = orig
            state = await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})
            return events, state.values
    finally:
        set_model_router(None)
        set_knowledge_adapter(None)
        set_rules_service(None)
        set_retrieval_config(None)


async def test_a1_plans_ranked_first_is_hair_wrap_and_bad_plan_dropped(mem_runtime, tmp_path):
    router, fakes = make_router(tmp_path, fast=[INTAKE_X9], main=[SYNTH_HAIR, ["请先清理滚刷。"]])
    adapter = ScriptedAdapter({"kb_manual": [OK_HAIR()], "kb_tickets": [NO_MATCH()]})
    events, values = await run_text(router, adapter, "eufy X9 Pro 扫地机不吸了，滚刷缠了很多头发")
    pr = values["plans_ranked"]
    assert [p["plan_id"] for p in pr] == ["rv_suction_hair_wrap", "rv_suction_filter_clog"]
    assert (
        pr[0]["evidence_ids"] == ["c12"]
        and pr[0]["source"] == "synthesize"
        and pr[0]["version"] == 1
    )
    synth_trace = next(t for t in values["retrieval_trace"] if t.get("event") == "synthesize")
    assert "plan_id:rv_battery_swap" in synth_trace["dropped"]
    # synthesize 的 prompt 带允许计划枚举与证据 id，且是 internal
    call = fakes["main"].calls[0]
    assert (
        "rv_suction_hair_wrap" in model_task_text(call)
        and "[c12]" in model_task_text(call)
    )
    assert "internal" in call["tags"] and call["metadata"]["task"] == "diagnose.synthesize"
    # query 只在 trace，不在任何事件里
    # 票 19：症状码贯通检索，query 以故障族开头
    assert values["query"] == "eufy X9 Pro 吸力下降 不吸了 滚刷缠头发"
    assert values["query"] not in json.dumps(events, ensure_ascii=False)
    r1 = [
        t
        for t in values["retrieval_trace"]
        if t.get("round") == 1 and t.get("kb") in ("kb_manual", "kb_tickets")
    ]
    assert {t["kb"] for t in r1} == {"kb_manual", "kb_tickets"} and r1[0]["query"] == values[
        "query"
    ]
    assert r1[0]["scope"] == {
        "product_state": "confirmed_sku",
        "category": "robot_vacuum",
        "sku": "EUFY-X9-PRO",
    }
    assert (
        r1[0]["hit_ids"] == ["c12", "c15"]
        and r1[0]["scores"] == [0.4, 0.2]
        and r1[0]["status"] == "ok"
    )
    assert (
        [t["kb"] for t in r1]
        and values["retrieval_rounds"] == 1
        and values["rewrite_used"] is False
    )
    # 操作原文发布，不再调用 guide.step。
    assert [a["task"] for a in values["model_trace"]] == [
        "intake",
        "diagnose.synthesize",
    ]
    tool = [e for e in events if e["type"] == "tool_call"]
    assert tool[-1]["summary"].startswith("命中 2 条来源")
    assert [e["type"] for e in events][-1] == "done"


async def test_no_evidence_uses_standard_flow_plans_without_model_call(mem_runtime, tmp_path):
    router, fakes = make_router(tmp_path, fast=[INTAKE_X9], main=[["按标准流程先清理滚刷。"]])
    adapter = ScriptedAdapter({"kb_manual": [NO_MATCH()], "kb_tickets": [NO_MATCH()]})
    _events, values = await run_text(router, adapter, "eufy X9 Pro 不吸了")
    pr = values["plans_ranked"]
    # 票 19：没有证据时唯一的线索是症状码，降级计划仍按症状过滤，不下发与当前症状无关的计划
    expected = LIB.allowed_for(category="robot_vacuum", sku="EUFY-X9-PRO", symptom_codes=["suction_low"])
    assert expected and [p["plan_id"] for p in pr] == [x.plan_id for x in expected] and all(
        p["source"] == "standard_flow" and p["confidence"] == 0.3 for p in pr
    )
    assert values["knowledge_status"] == "no_match"
    assert [a["task"] for a in values["model_trace"]] == [
        "intake",
        "diagnose.synthesize",
    ] and values["model_trace"][1]["model_used"] == "skipped"
    # 默认开关关闭：没有 query.rewrite 调用，fast 只被 intake 用过一次
    assert len(fakes["fast"].calls) == 1
    dec = next(t for t in values["retrieval_trace"] if t.get("event") == "rewrite_decision")
    assert dec["triggered"] is False and dec["reason"] == "disabled"


def _rcfg(enabled: bool = True, **rw) -> RetrievalConfig:
    cfg = get_retrieval_config().model_copy(deep=True)
    cfg.query_rewrite = cfg.query_rewrite.model_copy(update={"enabled": enabled, **rw})
    return cfg


async def test_rewrite_enabled_triggers_once_and_second_round_finds_plan(mem_runtime, tmp_path):
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
    events, values = await run_text(
        router, adapter, "eufy X9 Pro 它跑完了，地上还是一堆渣", rcfg=_rcfg()
    )
    assert values["retrieval_rounds"] == 2 and values["rewrite_used"] is True
    assert [c[1] for c in adapter.calls] == ["eufy X9 Pro 吸力下降 跑完了地上还是一堆渣"] * 2 + [
        "扫地机器人 清扫后残留碎屑 清洁效果差"
    ] * 2
    rw = next(t for t in values["retrieval_trace"] if t.get("event") == "rewrite_result")
    assert rw["accepted"] is True and rw["query_before"] != rw["query_after"]
    r2 = [
        t for t in values["retrieval_trace"] if t.get("round") == 2 and t.get("kb") == "kb_manual"
    ]
    assert r2[0]["scope"] == {
        "product_state": "confirmed_sku",
        "category": "robot_vacuum",
        "sku": "EUFY-X9-PRO",
    }  # scope 不变
    assert (
        values["plans_ranked"][0]["plan_id"] == "rv_suction_hair_wrap"
        and values["knowledge_status"] == "ok"
    )
    assert len(fakes["fast"].calls) == 2  # intake + 一次 rewrite
    tool = [e for e in events if e["type"] == "tool_call"]
    assert "已补检索" in tool[-1]["summary"]


async def test_rewrite_not_triggered_when_partial_unavailable_or_sufficient(mem_runtime, tmp_path):
    intake = json.dumps(
        {
            "emotion_level": "calm",
            "product_hints": ["X9 Pro"],
            "symptoms": ["不吸了"],
            "wants_human": False,
        }
    )
    router, fakes = make_router(
        tmp_path, fast=[intake, json.dumps({"query": "should not be used"})], main=[["x"]]
    )
    adapter = ScriptedAdapter({"kb_manual": [NO_MATCH()], "kb_tickets": [UNAVAILABLE()]})
    _, values = await run_text(router, adapter, "eufy X9 Pro 不吸了", rcfg=_rcfg())
    dec = next(t for t in values["retrieval_trace"] if t.get("event") == "rewrite_decision")
    assert (
        dec["triggered"] is False
        and dec["reason"] == "unavailable"
        and len(fakes["fast"].calls) == 1
    )
    assert values["knowledge_status"] == "no_match"  # 部分故障：不算全库不可用，也不算可改写
    router2, fakes2 = make_router(
        tmp_path,
        fast=[intake, json.dumps({"coverage": "sufficient", "items": [{"evidence_id": "c12", "verdict": "relevant"}]})],
        main=[json.dumps({"hypotheses": []}), ["x"]],
    )
    adapter2 = ScriptedAdapter({"kb_manual": [OK_HAIR()], "kb_tickets": [NO_MATCH()]})
    _, values2 = await run_text(router2, adapter2, "eufy X9 Pro 不吸了", rcfg=_rcfg())
    assert (
        next(t for t in values2["retrieval_trace"] if t.get("event") == "rewrite_decision")[
            "reason"
        ]
        == "sufficient"
    )
    assert [call["metadata"]["task"] for call in fakes2["fast"].calls] == ["intake", "retrieve.grade"]


async def test_rewrite_rejected_candidate_is_discarded_and_no_third_round(mem_runtime, tmp_path):
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
    router, _fakes = make_router(
        tmp_path, fast=[intake, json.dumps({"query": "扫地机器人 电机损坏 L60"})], main=[["x"]]
    )
    adapter = ScriptedAdapter({"kb_manual": [NO_MATCH()], "kb_tickets": [NO_MATCH()]})
    _, values = await run_text(
        router, adapter, "eufy X9 Pro 它跑完了，地上还是一堆渣", rcfg=_rcfg()
    )
    rw = next(t for t in values["retrieval_trace"] if t.get("event") == "rewrite_result")
    assert rw["accepted"] is False and rw["rejected_reason"] in (
        "new_model_token",
        "new_cause_or_action:电机",
    )
    assert (
        values["retrieval_rounds"] == 1
        and values["rewrite_used"] is True
        and len(adapter.calls) == 2
    )
    assert [p["source"] for p in values["plans_ranked"]] and values["plans_ranked"][0][
        "source"
    ] == "standard_flow"


async def test_second_round_skipped_when_budget_low(mem_runtime, tmp_path):
    """run 已耗时 20 s（剩余 < 8 s）：跳过补救并记录，不发第二轮。"""
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
    router, fakes = make_router(tmp_path, fast=[intake, json.dumps({"query": "x"})], main=[["x"]])
    adapter = ScriptedAdapter({"kb_manual": [NO_MATCH(), OK_HAIR()], "kb_tickets": [NO_MATCH()]})
    late = (datetime.now(UTC) - timedelta(seconds=20)).isoformat()
    _, values = await run_text(
        router, adapter, "eufy X9 Pro 它跑完了，地上还是一堆渣", at=late, rcfg=_rcfg()
    )
    dec = next(t for t in values["retrieval_trace"] if t.get("event") == "rewrite_decision")
    assert (
        dec["triggered"] is False
        and dec["reason"].startswith("budget")
        and dec["remaining_ms"] < 8000
    )
    assert (
        values["retrieval_rounds"] == 1
        and len(adapter.calls) == 2
        and len(fakes["fast"].calls) == 1
    )


async def test_category_only_query_and_scope_exclude_sku(mem_runtime, tmp_path):
    from app.sessions.graph import knowledge_scope_of, retrieval_query

    state = {
        "product_state": "category_only",
        "category": "robot_vacuum",
        "product_candidates": [X9],
        "symptoms": ["不吸了"],
        "text": "扫地机不吸了",
    }
    assert retrieval_query(state) == "扫地机器人 不吸了"
    scope = knowledge_scope_of(state)
    assert scope.product_state == "category_only" and scope.sku is None
    # 品类级只放出本品类且品类通用的计划：官方资料计划按型号开放，category_only 拿不到
    allowed = {p.plan_id for p in LIB.allowed_for(category=scope.category, sku=scope.sku)}
    assert allowed == {
        p.plan_id
        for p in LIB.plans
        if p.applies_to.category == "robot_vacuum" and p.applies_to.scope == "category_generic"
    }
    assert not [p for p in allowed if p.startswith("rv_x10_")]
