"""进程级回放状态（票 43）：REPLAY_CASE_ID 设置时加载录制包并核对清单；models / knowledge runtime 据此切换实现。

get_replay_package()：首次调用加载 + 核对，任一版本不符抛 ReplayIncompatible（main 启动失败；节点侧不会走到）。
未设置 REPLAY_CASE_ID 时返回 None，所有真实实现照旧。测试可 set_replay_package() 注入。
"""

from __future__ import annotations

import logging

from app.replay.package import ReplayIncompatible, ReplayPackage, current_versions, load_package

log = logging.getLogger("replay.runtime")
_package: ReplayPackage | None = None
_built = False


def set_replay_package(package: ReplayPackage | None) -> None:
    global _package, _built
    _package = package
    _built = package is not None


def replay_case_id() -> str:
    from app.settings import settings

    return (settings.replay_case_id or "").strip()


def is_replay_mode() -> bool:
    return bool(_package) if _built else bool(replay_case_id())


def versions_now() -> dict[str, str | None]:
    from app.models.config import load_models_config
    from app.settings import settings

    models_ver = load_models_config(
        settings.models_config_path, lane_override=settings.model_lane
    ).version
    return current_versions(
        models_ver=models_ver,
        rules_path=settings.rules_config_path,
        kb_manifest_path=settings.kb_manifest_path,
        kb_ver_override=settings.kb_ver,
    )


def get_replay_package() -> ReplayPackage | None:
    """REPLAY_CASE_ID 未设置 → None；设置 → 加载并核对（失败抛 ReplayIncompatible，不静默降级）。"""
    global _package, _built
    if _built:
        return _package
    case_id = replay_case_id()
    if not case_id:
        _built = True
        return None
    from app.settings import settings

    pkg = load_package(settings.replay_dir, case_id)
    pkg.check(versions_now())
    _package, _built = pkg, True
    log.info("replay mode enabled %s", pkg.describe())
    return pkg


def describe() -> dict | None:
    """health 用：回放开关与命中 / 未命中计数；异常也收敛为可读字典。"""
    if not is_replay_mode():
        return None
    try:
        pkg = get_replay_package()
    except ReplayIncompatible as exc:
        return {"status": "down", "case_id": exc.case_id, "detail": "; ".join(exc.problems)[:300]}
    if pkg is None:
        return None
    out = {"status": "ok", **pkg.describe()}
    from app.knowledge.runtime import get_knowledge_adapter
    from app.models.runtime import get_model_router

    router, adapter = get_model_router(), get_knowledge_adapter()
    out["model_hits"] = getattr(router, "hits", 0)
    out["model_misses"] = len(getattr(router, "misses", []) or [])
    out["knowledge_hits"] = getattr(adapter, "hits", 0)
    out["knowledge_misses"] = len(getattr(adapter, "misses", []) or [])
    return out
