"""haike-inspect：一条命令跑完全部巡检场景并出报告（票 45）。

  haike-inspect                      # stub 模型 / 适配器跑全部分组，写 reports/inspection/，回填 findings.md
  haike-inspect --group boundary     # 只跑某些组（可重复）
  haike-inspect --live http://127.0.0.1:8000   # 追加真实服务 A1 语义样例
  haike-inspect --no-findings        # 不改 findings.md

退出码：0 全部通过；1 有场景失败（stderr 列出场景名）；2 参数错误。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
from pathlib import Path

from app.settings import REPO_ROOT

DEFAULT_OUT = REPO_ROOT / "reports" / "inspection"


async def run_all(groups: list[str] | None, live_url: str | None, tmp: Path):
    from app.inspection.scenarios import Ctx, run_scenario, scenarios_for

    ctx = Ctx(tmp=tmp, live_url=live_url)
    results = []
    for s in scenarios_for(groups, live=live_url is not None):
        r = await run_scenario(s, ctx)
        results.append(r)
        mark = "PASS" if r.passed else "FAIL"
        print(f"[{mark}] {s.group:11s} {s.name:36s} {r.elapsed_ms:6d} ms" + ("" if r.passed else f"  ← {r.error}"), flush=True)
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="故障与边界场景巡检（票 45）")
    ap.add_argument("--group", action="append", help="boundary / routing / rewrite / concurrency / live，可重复")
    ap.add_argument("--live", default=None, help="真实服务地址，追加 live 组（真实模型语义样例）")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="报告目录")
    ap.add_argument("--no-findings", action="store_true", help="不回填 findings.md")
    ns = ap.parse_args(sys.argv[1:] if argv is None else argv)
    # 与单测同一套默认：stub 模式下不加载故障卡（票 33 的故障卡路径由其单测覆盖），不发任何网络请求
    os.environ.setdefault("HAIKE_FAULT_CARDS", "off")
    os.environ.setdefault("HAIKE_LLM", "off")
    os.environ.setdefault("HAIKE_KNOWLEDGE", "off")

    from app.inspection.report import summarize, update_findings, write_reports

    with tempfile.TemporaryDirectory(prefix="haike-inspect-") as td:
        results = asyncio.run(run_all(ns.group, ns.live, Path(td)))
    summary = summarize(results, live_url=ns.live, groups=ns.group)
    _js, md = write_reports(Path(ns.out), summary, results)
    if not ns.no_findings:
        update_findings(summary, results, md)
    lat = summary["latency"]
    print(
        f"\n{summary['passed']}/{summary['total']} passed · first_visible_ms p95={lat['first_visible_ms']['p95']} "
        f"card_ready_ms p95={lat['card_ready_ms']['p95']} · report {md}"
    )
    if summary["failed"]:
        print("FAILED scenarios: " + ", ".join(summary["failed"]), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
