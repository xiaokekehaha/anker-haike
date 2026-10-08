"""plans.yaml 加载 + 跨计划一致性校验 + L4 内存缓存（07 §12）。"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from app.plans.models import Plan, PlansConfig, plan_json_schema


class PlansError(RuntimeError):
    def __init__(self, path: str | Path, problems: list[str]):
        self.path = str(path)
        self.problems = problems
        super().__init__(
            f"plans config invalid ({path}):\n" + "\n".join(f"  - {p}" for p in problems)
        )


def _format(exc: ValidationError) -> list[str]:
    return [f"{'.'.join(str(p) for p in e['loc']) or '<root>'}: {e['msg']}" for e in exc.errors()]


def load_plans_config(path: str | Path) -> PlansConfig:
    path = Path(path)
    if not path.is_file():
        raise PlansError(path, ["file not found"])
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PlansError(path, [f"invalid yaml: {exc}"]) from exc
    try:
        cfg = PlansConfig.model_validate(raw)
    except ValidationError as exc:
        raise PlansError(path, _format(exc)) from exc
    problems: list[str] = []
    seen: set[tuple[str, int]] = set()
    for plan in cfg.plans:
        key = (plan.plan_id, plan.version)
        if key in seen:
            problems.append(f"duplicate plan {plan.plan_id} v{plan.version}")
        seen.add(key)
        for step in plan.steps:
            if step.evidence_key not in cfg.evidence:
                problems.append(
                    f"{plan.plan_id}.{step.step_id}.instruction_src -> {step.instruction_src!r} not in evidence index"
                )
    if problems:
        raise PlansError(path, problems)
    return cfg


class PlanLibrary:
    """进程内只读计划库；`reload_if_changed()` 在配置 version 变化时整体替换。"""

    def __init__(self, cfg: PlansConfig, path: str | Path | None = None):
        self._path = Path(path) if path else None
        self._apply(cfg)

    def _apply(self, cfg: PlansConfig) -> None:
        self.version = cfg.version
        self.evidence = dict(cfg.evidence)
        # 同一 plan_id 只保留最高版本
        latest: dict[str, Plan] = {}
        for p in cfg.plans:
            if p.plan_id not in latest or p.version > latest[p.plan_id].version:
                latest[p.plan_id] = p
        self._plans = latest

    @classmethod
    def from_yaml(cls, path: str | Path) -> PlanLibrary:
        return cls(load_plans_config(path), path)

    def reload_if_changed(self) -> bool:
        if self._path is None:
            return False
        cfg = load_plans_config(self._path)
        if cfg.version == self.version:
            return False
        self._apply(cfg)
        return True

    # ---- 查询 ----
    @property
    def plans(self) -> list[Plan]:
        return list(self._plans.values())

    @property
    def plan_ids(self) -> list[str]:
        return sorted(self._plans)

    def get(self, plan_id: str) -> Plan:
        return self._plans[plan_id]

    def allowed_for(self, *, category: str, sku: str | None = None) -> list[Plan]:
        """当前产品状态允许的计划集合：confirmed_sku 传 sku，category_only 不传（09 §2.1、§3.2）。"""
        return [p for p in self._plans.values() if p.applies(category=category, sku=sku)]

    def differentiated_skus(self, *, category: str, symptom_codes=()) -> set[str]:
        """知识按型号分化的 SKU：型号专属计划的 sku_list，加上被通用计划排除的 excluded_skus。
        给了症状码就只看与之相交的计划。集合为空表示知道型号也不改变下一步（spec 2026-09-19-0810 A）。"""
        codes = set(symptom_codes)
        out: set[str] = set()
        for p in self._plans.values():
            if p.applies_to.category != category or (codes and not codes.intersection(p.symptom_codes)):
                continue
            out.update(p.applies_to.sku_list if p.applies_to.scope == "sku" else p.applies_to.excluded_skus)
        return out

    def schema_for(self, *, category: str, sku: str | None = None) -> dict:
        return plan_json_schema([p.plan_id for p in self.allowed_for(category=category, sku=sku)])

    def evidence_snippet(self, instruction_src: str) -> str:
        return self.evidence[instruction_src.removeprefix("evidence:")].snippet
