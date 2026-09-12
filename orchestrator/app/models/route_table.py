"""从 models.yaml 生成路由展示表（model-selection §3.4 / §4 格式），禁止手工维护。"""

from __future__ import annotations

from app.models.config import ModelsConfig

HEADER = "| task | 主 | 降级 1 | 降级 2 | 需视觉 |\n| --- | --- | --- | --- | --- |"
EMPTY = "—"


def _cell(cfg: ModelsConfig, alias: str, lane: str) -> str:
    alias_lane = cfg.lane_of(alias)
    return alias if alias_lane == lane else f"{alias}（{alias_lane}）"


def render_route_table(cfg: ModelsConfig, lane: str | None = None) -> str:
    lane = lane or cfg.default_lane
    tasks = cfg.lanes[lane]
    rows = [HEADER]
    for task, route in tasks.items():
        cells = [_cell(cfg, a, lane) for a in route.chain[:3]]
        cells += [EMPTY] * (3 - len(cells))
        rows.append(f"| {task} | {' | '.join(cells)} | {'是' if route.needs_vision else '否'} |")
    for kind in ("embedding", "rerank"):
        aliases = cfg.aliases_of_kind(kind)  # type: ignore[arg-type]
        cells = [f"{a}（{cfg.models[a].provider}）" for a in aliases[:3]]
        cells += [EMPTY] * (3 - len(cells))
        rows.append(f"| {kind} | {' | '.join(cells)} | {EMPTY} |")
    return "\n".join(rows) + "\n"
