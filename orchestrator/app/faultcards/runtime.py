"""进程级 FaultCardLibrary（图节点用；测试可注入）。"""

from __future__ import annotations

import os

from app.faultcards.library import FaultCardLibrary

_lib: FaultCardLibrary | None = None
_built = False


def set_fault_card_library(lib: FaultCardLibrary | None) -> None:
    global _lib, _built
    _lib = lib
    _built = lib is not None


def get_fault_card_library() -> FaultCardLibrary | None:
    """HAIKE_FAULT_CARDS=off（单测默认）时返回 None：不预加载、不产生故障卡证据。"""
    global _lib, _built
    if _built:
        return _lib
    _built = True
    if os.environ.get("HAIKE_FAULT_CARDS", "on").lower() in ("off", "0", "false"):
        return None
    if _lib is None:
        from app.plans.runtime import get_plan_library
        from app.settings import settings

        _lib = FaultCardLibrary.from_yaml(
            settings.fault_cards_config_path, plan_ids=set(get_plan_library().plan_ids)
        )
    return _lib
