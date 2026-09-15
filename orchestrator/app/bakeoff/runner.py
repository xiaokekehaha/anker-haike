"""跑评测：task × 候选别名 × 样本 × repeats → 四项指标 → 门槛裁决 → 报告（Markdown + JSON）。"""

from __future__ import annotations

import asyncio
import statistics
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from app.bakeoff.config import BakeoffConfig
from app.bakeoff.recording import RecordingRouter, pin_config
from app.bakeoff.samples import Sample
from app.bakeoff.tasks import ADAPTORS
from app.models.config import ModelsConfig
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter

RouterFactory = Callable[[ModelsConfig, str, str], ModelRouter]


@dataclass
class SampleRun:
    sample_id: str
    repeat: int
    first_pass: bool
    accuracy: float
    latency_ms: int
    usage: dict[str, int]
    info: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class CandidateResult:
    task: str
    alias: str
    model_used: str
    available: bool
    skip_reason: str | None = None
    runs: list[SampleRun] = field(default_factory=list)
    # 汇总（样本内 3 遍取中位数，再跨样本平均 / P50）
    schema_pass: float | None = None
    accuracy: float | None = None
    latency_p50_ms: int | None = None
    cost_cny_per_call: float | None = None
    verdict: str = "not_run"  # primary_ok / fallback_ok / below / not_run / unavailable
    reasons: list[str] = field(default_factory=list)


@dataclass
class TaskResult:
    task: str
    lane: str
    samples: int
    candidates: list[CandidateResult]
    primary: str | None = None
    fallback: str | None = None
    note: str | None = None


def _median(xs: list[float]) -> float:
    return float(statistics.median(xs)) if xs else 0.0


def summarize(cand: CandidateResult, cfg: BakeoffConfig) -> None:
    by_sample: dict[str, list[SampleRun]] = {}
    for r in cand.runs:
        by_sample.setdefault(r.sample_id, []).append(r)
    if not by_sample:
        return
    passes, accs, lats, ins, outs = [], [], [], [], []
    for runs in by_sample.values():
        passes.append(_median([1.0 if r.first_pass else 0.0 for r in runs]))
        accs.append(_median([r.accuracy for r in runs]))
        lats.append(_median([r.latency_ms for r in runs]))
        ins.append(_median([r.usage.get("input_tokens", 0) for r in runs]))
        outs.append(_median([r.usage.get("output_tokens", 0) for r in runs]))
    cand.schema_pass = round(sum(passes) / len(passes), 4)
    cand.accuracy = round(sum(accs) / len(accs), 4)
    cand.latency_p50_ms = int(_median(lats))
    price = cfg.price_cny(cand.alias)
    if price is not None:
        pi, po = price
        cand.cost_cny_per_call = round(
            (sum(ins) / len(ins) * pi + sum(outs) / len(outs) * po) / 1_000_000, 6
        )


def judge(
    task: str, cands: list[CandidateResult], cfg: BakeoffConfig, lane_of: Callable[[str], str]
) -> tuple[str | None, str | None, str | None]:
    """§3.8 裁决：先按通过率 / 准确率过滤；达标者中延迟 + 成本综合最低为主；备用须来自另一家厂商。"""
    th = cfg.thresholds
    lat_cap = th.latency_p50_ms.get(task)
    acc_th = cfg.accuracy_threshold(task)
    # 硬门先于准确率：聚合准确率会把「失效方式」抹平 —— 一个在铭牌上编造、一个在误导文字下编造，
    # 两种幻觉各扣几个点又被别的样本补回来，排序就看不出差别了。这几项不达标直接出局。
    gates = th.hard_gates.get(task, {})
    for c in cands:
        if not c.available:
            continue
        breakdown = metric_breakdown(c)
        for metric, floor in gates.items():
            got = breakdown.get(metric)
            if got is not None and got[0] < floor:
                c.reasons.append(f"硬门 {METRIC_LABELS.get(metric, metric)} {got[0]:.0%} < {floor:.0%}")
    ok: list[CandidateResult] = []
    for c in cands:
        if not c.available or c.schema_pass is None:
            c.verdict = "unavailable" if not c.available else "not_run"
            continue
        c.reasons = []
        if c.schema_pass < th.primary.schema_pass:
            c.reasons.append(f"schema_pass {c.schema_pass:.0%} < {th.primary.schema_pass:.0%}")
        if c.accuracy is not None and c.accuracy < acc_th:
            c.reasons.append(f"accuracy {c.accuracy:.0%} < {acc_th:.0%}")
        if lat_cap and c.latency_p50_ms is not None and c.latency_p50_ms > lat_cap:
            c.reasons.append(f"latency_p50 {c.latency_p50_ms} ms > {lat_cap} ms")
        if c.reasons:
            c.verdict = "below"
        else:
            c.verdict = "primary_ok"
            ok.append(c)
    if not ok:
        return None, None, "无候选达到主模型门槛（见各候选 reasons）；按 §3.8 需降低门槛并记录原因"

    def key(c: CandidateResult) -> tuple[float, float]:
        lat = (c.latency_p50_ms or 0) / (lat_cap or 5000)
        cost = c.cost_cny_per_call if c.cost_cny_per_call is not None else 0.0
        return (lat + cost * 100, cost)

    ok.sort(key=key)
    primary = ok[0]
    fallback = None
    for c in cands:
        if c is primary or not c.available or c.schema_pass is None:
            continue
        if lane_of(c.alias) == lane_of(primary.alias) and _provider(c) == _provider(primary):
            continue
        ok_fb = (
            c.schema_pass >= th.fallback.schema_pass
            and (c.accuracy or 0) >= (primary.accuracy or 0) - th.fallback.accuracy_delta_max
            and (c.latency_p50_ms or 0)
            <= (primary.latency_p50_ms or 1) * th.fallback.latency_ratio_max
        )
        if ok_fb:
            if c.verdict != "primary_ok":
                c.verdict = "fallback_ok"
            fallback = c
            break
    note = None if fallback else "无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）"
    return primary.alias, fallback.alias if fallback else None, note


def _provider(c: CandidateResult) -> str:
    return c.model_used.split("/", 1)[0]


async def _run_candidate(
    task: str,
    alias: str,
    samples: list[Sample],
    cfg: BakeoffConfig,
    models_cfg: ModelsConfig,
    lane: str,
    router_factory: RouterFactory | None,
    sem: asyncio.Semaphore,
    progress: Callable[[str], None],
    env: dict[str, str] | None = None,
) -> CandidateResult:
    registry = ModelRegistry(models_cfg, env=env)
    resolved = registry.resolve(alias)
    res = CandidateResult(task, alias, resolved.model_used, available=True)
    reason = registry.unavailable_reason(alias)
    route = models_cfg.route(task, lane)
    if reason:
        res.available, res.skip_reason = False, reason
        return res
    if route.needs_vision and not resolved.spec.vision:
        res.available, res.skip_reason = False, "no vision capability"
        return res
    pinned = pin_config(models_cfg, task, alias, lane)
    adaptor = ADAPTORS[task]

    async def one(sample: Sample, repeat: int) -> SampleRun:
        router = (
            router_factory(pinned, task, alias)
            if router_factory
            else RecordingRouter(ModelRegistry(pinned), alias)
        )
        async with sem:
            t0 = time.perf_counter()
            try:
                acc, info = await adaptor(router, sample, lane)
                err = None
            except Exception as exc:  # noqa: BLE001 - 评测要把任何失败记成 0 分而不是中断
                acc, info, err = 0.0, {}, f"{type(exc).__name__}: {exc}"[:200]
            wall = int((time.perf_counter() - t0) * 1000)
        recs = getattr(router, "records", [])
        first_pass = (
            all(r.first_pass for r in recs)
            if recs
            else bool(info.get("gated_without_model_call"))  # 有意不调模型，不是失败
        )
        usage: dict[str, int] = {}
        for r in recs:
            for k, v in r.usage.items():
                usage[k] = usage.get(k, 0) + int(v)
        lat = sum(r.latency_ms for r in recs) or wall
        if task == "reply.stream" and isinstance(info.get("first_visible_ms"), int):
            lat = info["first_visible_ms"]  # 流式口径：首个可见 delta
        progress(f"  {task} {alias} {sample.id} #{repeat} acc={acc:.2f} pass={first_pass} {lat}ms")
        return SampleRun(sample.id, repeat, first_pass, acc, lat, usage, info, err)

    res.runs = await asyncio.gather(*(one(s, i) for s in samples for i in range(cfg.repeats)))
    summarize(res, cfg)
    return res


async def run_bakeoff(
    models_cfg: ModelsConfig,
    cfg: BakeoffConfig,
    samples_by_task: dict[str, list[Sample]],
    *,
    lane: str | None = None,
    aliases: list[str] | None = None,
    extra: list[str] | None = None,
    router_factory: RouterFactory | None = None,
    progress: Callable[[str], None] = lambda _m: None,
    env: dict[str, str] | None = None,
) -> list[TaskResult]:
    """aliases 只跑链上这些别名；extra 把不在链上的别名也当候选（如拿 deepseek-pro 与 deepseek 对照）。"""
    lane = lane or models_cfg.default_lane
    sem = asyncio.Semaphore(cfg.concurrency)
    results: list[TaskResult] = []
    for task, samples in samples_by_task.items():
        if task not in ADAPTORS or task not in models_cfg.lanes[lane]:
            continue
        chain = list(models_cfg.route(task, lane).chain)
        for a in extra or []:
            if a not in chain and models_cfg.models[a].kind == "chat":
                chain.append(a)
        cands_aliases = [a for a in chain if not aliases or a in aliases]
        progress(f"task {task}: {len(samples)} samples × {cfg.repeats} repeats × {cands_aliases}")
        cands = [
            await _run_candidate(
                task, a, samples, cfg, models_cfg, lane, router_factory, sem, progress, env
            )
            for a in cands_aliases
        ]
        primary, fallback, note = judge(task, cands, cfg, models_cfg.lane_of)
        results.append(TaskResult(task, lane, len(samples), cands, primary, fallback, note))
    return results


# ---- 报告 ----


def conversation_cost(
    results: list[TaskResult], cfg: BakeoffConfig
) -> tuple[float | None, list[str]]:
    """一次 A1 对话成本（按 primary 的单次成本 × conversation_profile 次数）；缺数据的 task 列出。"""
    total, missing = 0.0, []
    for task, n in cfg.conversation_profile.items():
        tr = next((t for t in results if t.task == task), None)
        c = next((c for c in tr.candidates if tr and c.alias == tr.primary), None) if tr else None
        if c is None or c.cost_cny_per_call is None:
            missing.append(task)
            continue
        total += c.cost_cny_per_call * n
    return (round(total, 4) if not missing else None), missing


METRIC_LABELS = {
    "part": "部件准确率",
    "phenomenon": "现象准确率",
    "plan": "plan 命中率",
    "model_hint": "铭牌读出率",
    "hallucination_free": "无幻觉率",
    "abstention_free": "未过度弃答率",
    "safety": "安全召回",
    "usable": "可用判定准确率",
}


def metric_breakdown(cand: CandidateResult) -> dict[str, tuple[float, int]]:
    """把各样本 info.metrics 按指标族聚合成（命中率, 适用样本数）。

    样本内多遍先取中位数再跨样本平均，与 summarize 的口径一致；分母只算该指标适用的样本。
    """
    per_sample: dict[str, dict[str, list[float]]] = {}
    for r in cand.runs:
        for k, v in (r.info.get("metrics") or {}).items():
            per_sample.setdefault(k, {}).setdefault(r.sample_id, []).append(1.0 if v else 0.0)
    out: dict[str, tuple[float, int]] = {}
    for k, samples in per_sample.items():
        vals = [_median(xs) for xs in samples.values()]
        out[k] = (round(sum(vals) / len(vals), 4), len(vals))
    return out


def render_markdown(results: list[TaskResult], cfg: BakeoffConfig, *, models_version: str) -> str:
    from app.diagnose.localization import vocabulary
    from app.diagnose.vision import VISION_PROMPT_VERSION

    header = (
        f"# bake-off 结果（models.yaml {models_version}，bakeoff.yaml {cfg.version}，"
        f"读图提示词 {VISION_PROMPT_VERSION}，词表 {vocabulary()['version']}，repeats={cfg.repeats}）"
    )
    lines = [header, ""]
    lines.append(
        "| task | 候选 | 模型 | Schema 通过率 | 字段准确率 | 延迟 P50 | 成本 ¥/次 | 裁决 |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for t in results:
        for c in t.candidates:
            if not c.available:
                lines.append(
                    f"| {t.task} | {c.alias} | {c.model_used} | — | — | — | — | 未跑：{c.skip_reason} |"
                )
                continue
            tag = {
                "primary_ok": "达标",
                "fallback_ok": "备用达标",
                "below": "未达标",
                "not_run": "未跑",
            }[c.verdict]
            if c.alias == t.primary:
                tag = "**主**"
            elif c.alias == t.fallback:
                tag = "**备**"
            cost = f"{c.cost_cny_per_call:.4f}" if c.cost_cny_per_call is not None else "—"
            lines.append(
                f"| {t.task} | {c.alias} | {c.model_used} | {c.schema_pass:.0%} | {c.accuracy:.0%} | {c.latency_p50_ms} ms | {cost} | {tag}"
                + (
                    f"（{'；'.join(c.reasons)}）"
                    if c.reasons and c.alias not in (t.primary, t.fallback)
                    else ""
                )
                + " |"
            )
    rows = [
        (t_.task, c.alias, metric_breakdown(c))
        for t_ in results
        for c in t_.candidates
        if c.available and metric_breakdown(c)
    ]
    if rows:
        keys = [k for k in METRIC_LABELS if any(k in m for _, _, m in rows)]
        lines.append("")
        lines.append("## 字段级指标（分母为该指标适用的样本数）")
        lines.append("| task | 候选 | " + " | ".join(METRIC_LABELS[k] for k in keys) + " |")
        lines.append("| --- | --- | " + " | ".join(["---"] * len(keys)) + " |")
        for task, alias, m in rows:
            cells = [f"{m[k][0]:.0%} ({m[k][1]})" if k in m else "—" for k in keys]
            lines.append(f"| {task} | {alias} | " + " | ".join(cells) + " |")
        lines.append("")
        lines.append(
            "> 安全召回用的是合成烧灼图。合成图画不出烧焦的材质感（模型一致读成污渍 / 破损），"
            "**该列在换上真实照片前不具备参考价值**。文字侧 R4（text_terms 冒烟 / 烧焦 / 鼓包）不依赖视觉，仍然生效。"
        )
    lines.append("")
    lines.append("## 裁决")
    for t in results:
        lines.append(
            f"- {t.task}：主 = {t.primary or '—'}，备 = {t.fallback or '—'}"
            + (f"；{t.note}" if t.note else "")
        )
    total, missing = conversation_cost(results, cfg)
    lines.append("")
    if total is not None:
        ok = "达标" if total <= cfg.thresholds.conversation_cost_cny_max else "超标"
        lines.append(
            f"## 一次 A1 对话成本：¥{total}（门槛 ¥{cfg.thresholds.conversation_cost_cny_max}，{ok}）"
        )
    else:
        lines.append(f"## 一次 A1 对话成本：无法估算（缺 {', '.join(missing)} 的主模型成本）")
    return "\n".join(lines) + "\n"


def to_json(results: list[TaskResult]) -> list[dict[str, Any]]:
    return [asdict(t) for t in results]
