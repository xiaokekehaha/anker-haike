"""进程级 ModelRouter 取用（图节点用；测试可注入）。

HAIKE_LLM=off 时 get_model_router() 返回 None：节点走降级路径，不发任何模型请求（单测默认，见 tests/__init__.py）。
"""

from __future__ import annotations

import logging
import os

from app.models.config import load_models_config
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter

log = logging.getLogger("models.runtime")
_router: ModelRouter | None = None
_built = False


def set_model_router(router: ModelRouter | None) -> None:
    global _router, _built
    _router = router
    _built = router is not None


def get_model_router() -> ModelRouter | None:
    global _router, _built
    if _built:
        return _router
    _built = True
    if os.environ.get("HAIKE_LLM", "on").lower() in ("off", "0", "false"):
        log.info("HAIKE_LLM=off: model router disabled, nodes use degraded paths")
        return None
    from app.settings import settings

    cfg = load_models_config(settings.models_config_path, lane_override=settings.model_lane)
    _router = ModelRouter(ModelRegistry(cfg))
    return _router
