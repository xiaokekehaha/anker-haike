"""进程级 PlanLibrary 取用（图节点用；测试可注入）。计划全部由官方 Q&A 生成（app.plans.qa）。"""

from __future__ import annotations

from app.plans.library import PlanLibrary

_lib: PlanLibrary | None = None


def set_plan_library(lib: PlanLibrary | None) -> None:
    global _lib
    _lib = lib


def get_plan_library() -> PlanLibrary:
    global _lib
    if _lib is None:
        from app.plans.qa import qa_plan_library

        _lib = qa_plan_library()
    return _lib
