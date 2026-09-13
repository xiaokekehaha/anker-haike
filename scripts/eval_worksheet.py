#!/usr/bin/env python3
"""生成检索评测集的标注工作单：把每条样例的现有金标与「实际检索到什么」并排放在一页里，边看边改 cases.yaml。

用法：
    make eval-worksheet                       # 等价于下面这条（需要项目 venv 里的 pyyaml）
    cd orchestrator && uv run python ../scripts/eval_worksheet.py [报告.json] [-o 输出.md]

报告默认取 reports/retrieval/ 下最新的一份（优先带 _synth 的，因为它还带模型选了哪个 plan）。
先跑一次 `make kb-eval ARM=A` 或带 --with-synthesize 的评测，再生成工作单。
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "eval" / "retrieval" / "cases.yaml"


def latest_report() -> Path:
    files = sorted(glob.glob(str(ROOT / "reports" / "retrieval" / "*.json")))
    if not files:
        sys.exit("reports/retrieval/ 下没有报告，先跑 make kb-eval ARM=A")
    synth = [f for f in files if "_synth" in f]
    return Path((synth or files)[-1])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("report", nargs="?", default=None)
    ap.add_argument("-o", "--out", default=str(ROOT / "reports" / "retrieval" / "worksheet.md"))
    args = ap.parse_args()

    import yaml

    report = Path(args.report) if args.report else latest_report()
    data = json.loads(report.read_text(encoding="utf-8"))
    rows = {r["id"]: r for r in data["rows"]}
    doc = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    cases = doc.get("cases") or []
    done = sum(1 for c in cases if c.get("annotated"))

    out = [
        "# 检索评测集标注工作单",
        "",
        f"报告：`{report.relative_to(ROOT)}`　样例：{len(cases)} 条，已标注 {done} 条。",
        "对照每条的「实际检索」改 `data/eval/retrieval/cases.yaml`，改完把 `annotated` 置 true 并填 `annotator`。",
        "字段含义与判断口径见 [ANNOTATION.md](../../docs/planning/2026-09-13_bounded-agentic-rag/ANNOTATION.md)。",
        "",
    ]
    for c in cases:
        r = rows.get(c["id"], {})
        mark = "已标注" if c.get("annotated") else "待标注"
        scope = c.get("sku") or c.get("category")
        out += [
            f"## {c['id']}　{mark}",
            "",
            f"- 用户原话：{c.get('text')}",
            f"- 范围：{c['product_state']} / {scope}　症状：{c.get('symptoms')}",
            f"- 实际 query：`{r.get('query', '-')}`",
            f"- 现有金标：doc={c.get('expected_doc_ids')} cause={c.get('expected_ticket_cause', '-')} "
            f"plan={c.get('expected_plan')} outcome={c.get('expected_outcome')}",
        ]
        synth = r.get("synth")
        if synth:
            out.append(f"- 模型选了：{synth.get('top_plan')}（{synth.get('source')}）→ {synth.get('outcome')}")
        if c.get("note"):
            out.append(f"- 起草备注：{c['note']}")
        out += ["", "| # | 来源 | doc_id | 片段 | 算金标? |", "| --- | --- | --- | --- | --- |"]
        for i, h in enumerate(r.get("hits") or [], 1):
            snip = (h.get("snippet") or "").replace("|", "/")[:60]
            out.append(f"| {i} | {h.get('source')} | {h.get('doc_id')} | {snip} |  |")
        out.append("")
    Path(args.out).write_text("\n".join(out), encoding="utf-8")
    print(f"worksheet: {args.out}（{len(cases)} 条，已标注 {done}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
