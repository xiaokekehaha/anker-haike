"""巡检报告（票 45）：JSON + Markdown 写到 reports/inspection/，摘要块回填 findings.md（演示前冻结判定）。"""

from __future__ import annotations

import json
import platform
import re
import statistics
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.inspection.scenarios import ScenarioResult
from app.settings import REPO_ROOT

FINDINGS = REPO_ROOT / "docs" / "planning" / "2026-09-12_smart-service-implementation" / "findings.md"
BLOCK_START = "<!-- inspection:start -->"
BLOCK_END = "<!-- inspection:end -->"


def _git_rev() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=REPO_ROOT, timeout=5, check=False
        )
        return out.stdout.strip() or "-"
    except Exception:  # noqa: BLE001
        return "-"


def _pct(values: list[int], p: float) -> int | None:
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, round(p * (len(s) - 1))))
    return s[k]


def summarize(results: list[ScenarioResult], *, live_url: str | None, groups: list[str] | None) -> dict[str, Any]:
    by_group: dict[str, dict[str, int]] = {}
    fv: list[int] = []
    cr: list[int] = []
    for r in results:
        g = by_group.setdefault(r.group, {"passed": 0, "failed": 0})
        g["passed" if r.passed else "failed"] += 1
        for key, bucket in (("first_visible_ms", fv), ("card_ready_ms", cr)):
            v = r.detail.get(key)
            if isinstance(v, list):
                bucket.extend(x for x in v if isinstance(x, int))
            elif isinstance(v, int):
                bucket.append(v)
    conc = next((r for r in results if r.name == "five_concurrent_a1"), None)
    rewrite_rows = [r for r in results if r.group == "rewrite" and r.passed and "retrieval_rounds" in r.detail]
    failed = [r.name for r in results if not r.passed]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "git": _git_rev(),
        "python": platform.python_version(),
        "mode": "stub" + ("+live" if live_url else ""),
        "live_url": live_url,
        "groups": groups,
        "total": len(results),
        "passed": len(results) - len(failed),
        "failed": failed,
        "by_group": by_group,
        "latency": {
            "first_visible_ms": {"n": len(fv), "p50": _pct(fv, 0.5), "p95": _pct(fv, 0.95), "max": max(fv) if fv else None},
            "card_ready_ms": {"n": len(cr), "p50": _pct(cr, 0.5), "p95": _pct(cr, 0.95), "max": max(cr) if cr else None},
        },
        "concurrency": None if conc is None else {"n": conc.detail.get("n"), "pass_rate": conc.detail.get("pass_rate"), "wall_ms": conc.detail.get("wall_ms"),
                                                   "card_ready_ms": conc.detail.get("card_ready_ms")},
        "rewrite": [
            {"scenario": r.name, "rewrite_enabled": r.detail.get("rewrite_enabled"), "invokes": r.detail.get("invokes"),
             "rewrite_invokes": r.detail.get("rewrite_invokes"), "retrieval_rounds": r.detail.get("retrieval_rounds"),
             "second_round_latency_ms": r.detail.get("second_round_latency_ms"), "fallback": r.detail.get("fallback"),
             "knowledge_status": r.detail.get("knowledge_status"), "decision": (r.detail.get("decision") or {}).get("reason")}
            for r in rewrite_rows
        ],
        "live": [r.detail for r in results if r.group == "live" and r.passed],
    }


def to_markdown(summary: dict[str, Any], results: list[ScenarioResult]) -> str:
    lines = [
        f"# 巡检报告 {summary['generated_at']}",
        "",
        f"- git `{summary['git']}` · mode `{summary['mode']}` · 通过 {summary['passed']}/{summary['total']}"
        + (f" · **失败：{', '.join(summary['failed'])}**" if summary["failed"] else " · 全部通过"),
        (
            f"- 延迟（运行器 run_metric 口径）：first_visible_ms p50/p95/max = {summary['latency']['first_visible_ms']['p50']}/{summary['latency']['first_visible_ms']['p95']}/{summary['latency']['first_visible_ms']['max']}"
            f"（n={summary['latency']['first_visible_ms']['n']}）；card_ready_ms p50/p95/max = {summary['latency']['card_ready_ms']['p50']}/{summary['latency']['card_ready_ms']['p95']}/{summary['latency']['card_ready_ms']['max']}（n={summary['latency']['card_ready_ms']['n']}）"
        ),
    ]
    if summary["concurrency"]:
        c = summary["concurrency"]
        lines.append(f"- 5 并发：通过率 {c['pass_rate']:.0%}，总墙钟 {c['wall_ms']} ms，card_ready_ms={c['card_ready_ms']}")
    lines += ["", "| 场景 | 组 | 结果 | 耗时 | 说明 |", "| --- | --- | --- | --- | --- |"]
    for r in results:
        note = r.error if not r.passed else _short(r.detail)
        lines.append(f"| {r.name} | {r.group} | {'✅' if r.passed else '❌'} | {r.elapsed_ms} ms | {note} |")
    if summary["rewrite"]:
        lines += ["", "## 改写开关巡检（stub 路由测试，不代表改写语义质量）", "",
                  "| 场景 | rewrite_enabled | invoke | rewrite invoke | 检索轮数 | 第二轮延迟 | 回退 | 知识状态 | 决策 |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for row in summary["rewrite"]:
            lines.append(f"| {row['scenario']} | {row['rewrite_enabled']} | {row['invokes']} | {row['rewrite_invokes']} | {row['retrieval_rounds']} | {row['second_round_latency_ms']} ms | {row['fallback']} | {row['knowledge_status']} | {row['decision']} |")
    if summary["live"]:
        lines += ["", "## 真实模型语义样例（--live）", ""]
        for d in summary["live"]:
            lines.append(f"- first_visible_ms={d.get('first_visible_ms')} card_ready_ms={d.get('card_ready_ms')} step={d.get('step')} replay={d.get('replay_mode')}")
    lines.append("")
    return "\n".join(lines)


def _short(detail: dict[str, Any]) -> str:
    keep = {k: v for k, v in detail.items() if k not in ("types", "models", "recorded_versions")}
    s = json.dumps(keep, ensure_ascii=False, default=str)
    return (s[:160] + "…") if len(s) > 160 else s


def write_reports(out_dir: Path, summary: dict[str, Any], results: list[ScenarioResult]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    js = out_dir / f"inspection-{stamp}.json"
    md = out_dir / f"inspection-{stamp}.md"
    js.write_text(json.dumps({"summary": summary, "results": [r.__dict__ for r in results]}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md.write_text(to_markdown(summary, results), encoding="utf-8")
    (out_dir / "latest.md").write_text(to_markdown(summary, results), encoding="utf-8")
    return js, md


def update_findings(summary: dict[str, Any], results: list[ScenarioResult], report_path: Path, findings: Path = FINDINGS) -> None:
    """把最近一次巡检摘要写进 findings.md 的固定块（覆盖上一次），供演示前冻结判定。"""
    fails = ", ".join(summary["failed"]) or "无"
    lat = summary["latency"]
    conc = summary["concurrency"] or {}
    block = "\n".join([
        BLOCK_START,
        "## 巡检结果（票 45，自动回填，最近一次）",
        f"- 时间 {summary['generated_at']}，git `{summary['git']}`，模式 `{summary['mode']}`，报告 `{report_path.relative_to(REPO_ROOT) if report_path.is_relative_to(REPO_ROOT) else report_path}`",
        f"- 场景 {summary['passed']}/{summary['total']} 通过；失败：{fails}",
        f"- 延迟（stub 模型，运行器口径）：first_visible_ms p95 {lat['first_visible_ms']['p95']} ms，card_ready_ms p95 {lat['card_ready_ms']['p95']} ms",
        f"- 5 并发通过率 {conc.get('pass_rate', 0):.0%}（墙钟 {conc.get('wall_ms')} ms）" if conc else "- 5 并发：未运行",
        "- 改写开关：" + "；".join(f"{r['scenario']}={r['retrieval_rounds']} 轮/{r['rewrite_invokes']} 次改写/{r['fallback']}" for r in summary["rewrite"]) if summary["rewrite"] else "- 改写开关：未运行",
        "- 真实模型语义样例：" + (json.dumps([{k: d.get(k) for k in ('first_visible_ms', 'card_ready_ms', 'step')} for d in summary["live"]], ensure_ascii=False, default=str) if summary["live"] else "未运行（加 --live URL）；stub 路由测试通过不代表改写 / 回复语义达标"),
        "- 冻结判定：" + ("**可冻结**（全部场景通过）" if not summary["failed"] else "**不可冻结**，先修失败场景"),
        BLOCK_END,
    ])
    text = findings.read_text(encoding="utf-8") if findings.exists() else "# 实现阶段发现\n"
    if BLOCK_START in text and BLOCK_END in text:
        text = re.sub(re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END), lambda _: block, text, flags=re.DOTALL)
    else:
        text = text.rstrip("\n") + "\n\n" + block + "\n"
    findings.write_text(text, encoding="utf-8")


def median(values: list[int]) -> float | None:
    return statistics.median(values) if values else None
