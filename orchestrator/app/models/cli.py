"""模型层命令行：

- haike-route-table [--lane L]        从 models.yaml 生成路由表（Markdown）
- haike-model-probe TASK [--alias A]  对 task 发一次最简调用，打印命中模型与延迟

只打印别名 / 厂商 / 模型 id，不打印 key。无其他厂商 key 时默认走 deepseek 别名。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from app.models.config import ConfigError, load_models_config
from app.models.probe import invoke_probe
from app.models.registry import ModelNotConfigured, ModelRegistry
from app.models.route_table import render_route_table
from app.settings import settings

DEFAULT_PROBE_ALIAS = "deepseek"


def _load(args):
    try:
        return load_models_config(args.config, lane_override=args.lane or settings.model_lane)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2) from None


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", default=settings.models_config_path)
    p.add_argument("--lane", default=None, help="覆盖 MODEL_LANE")


def route_table(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="生成路由展示表")
    _common(p)
    args = p.parse_args(argv)
    cfg = _load(args)
    print(f"通道：{cfg.default_lane}（models.yaml {cfg.version}）\n")
    print(render_route_table(cfg), end="")
    return 0


def pick_probe_alias(registry: ModelRegistry, task: str, alias: str | None) -> str:
    """显式别名 > 链上第一个可用 > deepseek 默认测试别名。"""
    if alias:
        return alias
    hit = registry.first_available(task)
    if hit:
        return hit.alias
    return DEFAULT_PROBE_ALIAS


def probe(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="对 task 发一次最简调用")
    _common(p)
    p.add_argument("task")
    p.add_argument("--alias", default=None, help="强制使用某别名")
    args = p.parse_args(argv)
    cfg = _load(args)
    registry = ModelRegistry(cfg)
    try:
        route = cfg.route(args.task)
    except KeyError as exc:
        print(exc, file=sys.stderr)
        return 2
    alias = pick_probe_alias(registry, args.task, args.alias)
    r = registry.resolve(alias)
    chain = " → ".join(x.alias for x in registry.chain(args.task))
    print(f"task={args.task} lane={cfg.default_lane} chain=[{chain}] probing alias={alias}")
    start = time.perf_counter()
    try:
        resp = asyncio.run(
            invoke_probe(registry, alias, min(20, r.spec.timeout_s), effort=route.effort)
        )
    except ModelNotConfigured as exc:
        print(f"skip: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001 - 探测脚本：任何厂商错误都要打印类型
        ms = int((time.perf_counter() - start) * 1000)
        print(f"FAIL model_used={r.model_used} latency_ms={ms} error={type(exc).__name__}: {exc}")
        return 1
    ms = int((time.perf_counter() - start) * 1000)
    text = resp.content if isinstance(resp.content, str) else str(resp.content)
    print(f"OK model_used={r.model_used} lane={r.lane} latency_ms={ms} reply={text.strip()[:40]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(probe())
