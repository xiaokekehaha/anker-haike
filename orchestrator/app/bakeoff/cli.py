"""haike-bakeoff：一条命令跑完评测并输出对比表。

  haike-bakeoff [--task intake ...] [--alias deepseek ...] [--repeats N] [--out DIR] [--lane L]

只有当前环境有 key 且 id 非 TBD 的候选会真正发请求；其余标「未跑」进表。报告写 DIR/bakeoff.md 与 bakeoff.json。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.bakeoff.config import ALL_TASKS, load_bakeoff_config
from app.bakeoff.runner import render_markdown, run_bakeoff, to_json
from app.bakeoff.samples import load_samples
from app.models.config import ConfigError, load_models_config
from app.settings import REPO_ROOT, settings


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="bake-off 评测（票 42）")
    p.add_argument("--task", action="append", help="只跑这些 task（可多次）")
    p.add_argument("--alias", action="append", help="只跑这些别名（可多次）")
    p.add_argument(
        "--extra", action="append", help="把链外别名也纳入候选（可多次，如 deepseek-pro）"
    )
    p.add_argument("--repeats", type=int, default=None)
    p.add_argument("--lane", default=None)
    p.add_argument("--config", default=settings.models_config_path)
    p.add_argument("--bakeoff-config", default=None)
    p.add_argument("--out", default=str(REPO_ROOT / "reports" / "bakeoff"))
    p.add_argument("-q", "--quiet", action="store_true")
    args = p.parse_args(argv)
    try:
        models_cfg = load_models_config(args.config, lane_override=args.lane or settings.model_lane)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    cfg = load_bakeoff_config(args.bakeoff_config)
    if args.repeats:
        cfg = cfg.model_copy(update={"repeats": args.repeats})
    tasks = args.task or list(ALL_TASKS)
    samples = {t: load_samples(t) for t in tasks}
    empty = [t for t, s in samples.items() if not s]
    if empty:
        print(f"无样本，跳过：{', '.join(empty)}", file=sys.stderr)
    samples = {t: s for t, s in samples.items() if s}
    log = (lambda _m: None) if args.quiet else (lambda m: print(m, file=sys.stderr, flush=True))
    results = asyncio.run(
        run_bakeoff(
            models_cfg,
            cfg,
            samples,
            lane=args.lane,
            aliases=args.alias,
            extra=args.extra,
            progress=log,
        )
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    md = render_markdown(results, cfg, models_version=models_cfg.version)
    (out / "bakeoff.md").write_text(md, encoding="utf-8")
    (out / f"bakeoff-{stamp}.json").write_text(
        json.dumps(to_json(results), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(md)
    print(f"报告：{out / 'bakeoff.md'}；明细：{out / f'bakeoff-{stamp}.json'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
