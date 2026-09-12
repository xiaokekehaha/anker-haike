"""进程级 PlanLibrary 取用（图节点用；测试可注入）。"""

from __future__ import annotations

from app.plans.library import PlanLibrary

_lib: PlanLibrary | None = None


def set_plan_library(lib: PlanLibrary | None) -> None:
    global _lib
    _lib = lib


def get_plan_library() -> PlanLibrary:
    global _lib
    if _lib is None:
        from app.settings import settings

        _lib = PlanLibrary.from_yaml(settings.plans_config_path)
    return _lib
