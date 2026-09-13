"""票 42：bake-off 评分规则、单链钉定、裁决、报告与合成图（全部假模型，不发请求）。"""

from __future__ import annotations

import json
from types import SimpleNamespace as NS

import pytest

from app.bakeoff import scoring
from app.bakeoff.config import ALL_TASKS, load_bakeoff_config
from app.bakeoff.recording import RecordingRouter, pin_config
from app.bakeoff.runner import (
    CandidateResult,
    conversation_cost,
    judge,
    render_markdown,
    run_bakeoff,
    summarize,
)
from app.bakeoff.samples import load_samples
from app.bakeoff.synth import render
from app.models.config import load_models_config
from app.models.fake import FakeChatModel
from app.models.registry import ModelRegistry
from app.settings import REPO_ROOT, settings

ALL_KEYS = {
    "DEEPSEEK_API_KEY": "x",
    "DASHSCOPE_API_KEY": "x",
    "ZHIPU_API_KEY": "x",
    "ANTHROPIC_API_KEY": "x",
    "GOOGLE_API_KEY": "x",
}
# 每个 task 一条「答对」的脚本输出，与各 task 第一条样本对齐
GOOD = {
    "intake": {
        "emotion_level": "calm",
        "product_hints": ["扫地机"],
        "symptoms": ["不吸了", "滚刷缠头发"],
        "wants_human": False,
    },
    "disambiguate.clarify": {"question": "请告诉我设备的型号或品类是什么？"},
    "diagnose.synthesize": {
        "hypotheses": [
            {"plan_id": "rv_suction_hair_wrap", "confidence": 0.8, "evidence_ids": ["e-c12"]}
        ]
    },
    "guide.step": {"instruction": "翻转主机，按下滚刷盖两侧卡扣取出滚刷，割断缠绕毛发后装回。"},
    "reply.stream": ["别担心，", "我马上帮您处理。"],
    "escalate.summary": {"problem": "机器不吸了，滚刷缠了很多头发。已经试过清理滤网。"},
    "query.rewrite": {"query": "扫地机器人 地上还是一堆渣 碎屑残留"},
    "retrieve.grade": {
        "items": [
            {"evidence_id": "c12", "verdict": "relevant"},
            {"evidence_id": "c21", "verdict": "irrelevant"},
            {"evidence_id": "water", "verdict": "irrelevant"},
        ],
        "coverage": "sufficient",
    },
    "diagnose.vision": {"observations": ["滚刷缠绕大量毛发"], "visible_parts": ["滚刷"]},
    "warranty.receipt_ocr": {
        "order_no": "2026091200123456",
        "channel": "eufy 官方旗舰店",
        "purchase_date": "2026-08-01",
        "amount": "¥2999.00",
        "confidence": {"order_no": 0.9, "channel": 0.9, "purchase_date": 0.9, "amount": 0.9},
        "unreadable": [],
    },
}


def _script(task: str):
    out = GOOD[task]
    return out if isinstance(out, list) else json.dumps(out, ensure_ascii=False)


@pytest.fixture
def models_cfg():
    return load_models_config(settings.models_config_path)


@pytest.fixture
def models_cfg_no_tbd(tmp_path):
    """仓库配置但把 TBD 全填成占位 id：流程测试要让每个 task 都有可跑候选（真实 id 由票 42 冻结）。"""
    text = (REPO_ROOT / "config" / "models.yaml").read_text(encoding="utf-8")
    p = tmp_path / "models.yaml"
    p.write_text(text.replace("id: TBD", "id: placeholder"), encoding="utf-8")
    return load_models_config(p)


@pytest.fixture
def cfg():
    return load_bakeoff_config().model_copy(update={"repeats": 2, "concurrency": 2})


# ---- 样本与合成图 ----


def test_every_task_has_samples_and_vision_images_are_synthetic():
    counts = {t: load_samples(t) for t in ALL_TASKS}
    assert all(counts[t] for t in ALL_TASKS)
    assert len(counts["intake"]) >= 20 and len(counts["diagnose.vision"]) >= 15
    assert len(counts["warranty.receipt_ocr"]) >= 15
    for s in counts["diagnose.vision"] + counts["warranty.receipt_ocr"]:
        assert s.images and s.images[0][0] == "image/png" and s.images[0][1][:4] == b"\x89PNG"
    # 图片不落仓库（tests/test_images 亦有全局扫描）
    assert not list((REPO_ROOT / "orchestrator" / "tests" / "fixtures" / "bakeoff").glob("*.png"))


def test_render_variants_produce_distinct_images():
    a = render({"kind": "parts", "part": "roller_brush", "hair": True, "seed": 1})
    b = render({"kind": "parts", "part": "roller_brush", "hair": False, "seed": 1})
    c = render({"kind": "receipt", "fields": {"order_no": "123"}, "blur": 2})
    assert a != b and len(c) > 1000


# ---- 评分规则 ----


def test_scoring_intake_partial_credit():
    out = NS(
        degraded=False,
        emotion={"level": "calm"},
        wants_human=False,
        product_hints=["S1 Pro"],
        symptoms=["不吸了"],
    )
    assert (
        scoring.score_intake(
            out, {"level": "calm", "wants_human": False, "hints_include_any": ["S1 Pro"]}
        )
        == 1.0
    )
    assert scoring.score_intake(out, {"level": "angry", "wants_human": False}) == 0.5
    assert scoring.score_intake(NS(degraded=True), {}) == 0.0


def test_scoring_receipt_normalizes_digits_and_amount():
    out = NS(
        status="ok",
        fields={
            "order_no": "JD-3012345678",
            "amount": "¥1,899",
            "channel": "京东自营",
            "purchase_date": None,
        },
    )
    exp = {
        "fields": {"order_no": "3012345678", "amount": "1899", "channel": "京东"},
        "unreadable": ["purchase_date"],
    }
    assert scoring.score_receipt(out, exp) == 1.0


def test_scoring_vision_recall_and_safety():
    out = NS(
        status="ok", observations=["滚刷缠绕毛发", "底部有 burnt 痕迹"], visible_parts=["滚刷"]
    )
    assert (
        scoring.score_vision(out, {"observe": [["滚刷"], ["毛发"]], "safety_any": ["burnt"]}) == 1.0
    )
    assert scoring.score_vision(out, {"observe": [["滚刷"], ["滤网"]]}) == 0.5
    assert scoring.score_vision(out, {"safety_any": ["smoke"]}) == 0.0


def test_scoring_summary_requires_same_sentences_and_no_warranty_claims():
    src = "机器 不吸了 。 滚刷缠头发"
    assert scoring.score_summary(src, "机器不吸了。滚刷缠头发", {}) == 1.0
    assert scoring.score_summary(src, "机器不吸了。滚刷缠头发。该机器可保", {}) == 0.0
    assert scoring.score_summary(src, None, {}) == 0.0


# ---- 钉链与记录 ----


def test_pin_config_only_changes_target_route(models_cfg):
    pinned = pin_config(models_cfg, "intake", "deepseek", "domestic")
    assert pinned.route("intake", "domestic").chain == ["deepseek"]
    assert (
        pinned.route("guide.step", "domestic").chain
        == models_cfg.route("guide.step", "domestic").chain
    )
    assert models_cfg.route("intake", "domestic").chain != ["deepseek"]


async def test_recording_router_captures_attempts_and_usage(models_cfg):
    pinned = pin_config(models_cfg, "intake", "deepseek", "domestic")
    fake = FakeChatModel(script=[_script("intake")])
    router = RecordingRouter(
        ModelRegistry(pinned, env=ALL_KEYS), "deepseek", model_factory=lambda r, _: fake
    )
    from app.intake.extract import IntakeExtraction

    await router.invoke("intake", [("human", "hi")], IntakeExtraction, budget_ms=5000)
    (rec,) = router.records
    assert (
        rec.ok
        and rec.first_pass
        and rec.usage["total_tokens"] == 15
        and rec.attempts[0].alias == "deepseek"
    )


# ---- 全流程（假模型）----


def _factory_all_good(pinned, task, alias):
    fake = FakeChatModel(script=[_script(task)] * 40, name_for_trace=alias)
    return RecordingRouter(
        ModelRegistry(pinned, env=ALL_KEYS), alias, model_factory=lambda r, _: fake
    )


async def test_run_bakeoff_first_samples_all_pass_and_judge_picks_primary(models_cfg_no_tbd, cfg):
    models_cfg = models_cfg_no_tbd
    samples = {t: load_samples(t)[:1] for t in ALL_TASKS}
    results = await run_bakeoff(
        models_cfg,
        cfg,
        samples,
        aliases=["deepseek", "qwen-flash", "qwen-vl", "sonnet"],
        router_factory=_factory_all_good,
        env=ALL_KEYS,
    )
    assert {r.task for r in results} == set(ALL_TASKS)
    for tr in results:
        ran = [c for c in tr.candidates if c.available]
        assert ran, tr.task
        for c in ran:
            assert c.schema_pass == 1.0 and c.accuracy == 1.0, (tr.task, c.alias, c.runs)
            assert len(c.runs) == cfg.repeats
        assert tr.primary is not None
    md = render_markdown(results, cfg, models_version=models_cfg.version)
    assert "| intake |" in md and "**主**" in md and "## 裁决" in md


async def test_run_bakeoff_records_failure_as_zero_not_exception(models_cfg, cfg):
    def factory(pinned, task, alias):
        fake = FakeChatModel(script=["not json at all"] * 40, name_for_trace=alias)
        return RecordingRouter(
            ModelRegistry(pinned, env=ALL_KEYS), alias, model_factory=lambda r, _: fake
        )

    results = await run_bakeoff(
        models_cfg,
        cfg,
        {"intake": load_samples("intake")[:2]},
        aliases=["deepseek"],
        router_factory=factory,
        env=ALL_KEYS,
    )
    (c,) = [c for c in results[0].candidates if c.available]
    assert c.schema_pass == 0.0 and c.accuracy == 0.0 and c.verdict == "below"
    assert results[0].primary is None and "无候选" in (results[0].note or "")


# ---- 裁决与成本 ----


def _cand(alias, model, sp, acc, lat, cost):
    c = CandidateResult("intake", alias, model, available=True)
    c.schema_pass, c.accuracy, c.latency_p50_ms, c.cost_cny_per_call = sp, acc, lat, cost
    return c


def test_judge_requires_fallback_from_another_provider(cfg, models_cfg):
    cands = [
        _cand("qwen-flash", "dashscope/q", 1.0, 0.95, 800, 0.0001),
        _cand("qwen-plus", "dashscope/p", 1.0, 0.96, 900, 0.0004),
        _cand("deepseek", "deepseek/d", 0.97, 0.92, 1200, 0.0002),
    ]
    primary, fallback, note = judge("intake", cands, cfg, models_cfg.lane_of)
    assert primary == "qwen-flash" and fallback == "deepseek" and note is None
    cands[2].schema_pass = 0.5
    primary, fallback, note = judge("intake", cands, cfg, models_cfg.lane_of)
    assert primary == "qwen-flash" and fallback is None and "两家" in note


def test_summarize_uses_median_over_repeats(cfg):
    from app.bakeoff.runner import SampleRun

    c = CandidateResult("intake", "deepseek", "deepseek/d", available=True)
    c.runs = [
        SampleRun("s", 0, True, 1.0, 100, {"input_tokens": 100, "output_tokens": 10}),
        SampleRun("s", 1, False, 0.0, 5000, {"input_tokens": 100, "output_tokens": 10}),
        SampleRun("s", 2, True, 1.0, 120, {"input_tokens": 100, "output_tokens": 10}),
    ]
    summarize(c, cfg)
    assert c.schema_pass == 1.0 and c.accuracy == 1.0 and c.latency_p50_ms == 120
    assert c.cost_cny_per_call is not None and c.cost_cny_per_call > 0


def test_conversation_cost_lists_missing_tasks(cfg):
    from app.bakeoff.runner import TaskResult

    c = _cand("deepseek", "deepseek/d", 1.0, 1.0, 100, 0.001)
    results = [TaskResult("intake", "domestic", 1, [c], primary="deepseek")]
    total, missing = conversation_cost(results, cfg)
    assert total is None and "reply.stream" in missing
