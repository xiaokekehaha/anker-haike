from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.catalog import ProductCatalog
from app.faultcards.runtime import get_fault_card_library
from app.health.router import router as health_router
from app.images.runtime import close_image_store, open_image_store
from app.models import ModelRegistry, ModelRouter, load_models_config
from app.models.runtime import set_model_router
from app.observability.runtime import LangfuseExporter, configure_logging, set_exporter
from app.plans import PlanLibrary
from app.replay.runtime import get_replay_package
from app.sessions.router import router as sessions_router
from app.sessions.runtime import close_session_runtime, open_session_runtime
from app.settings import settings
from app.warranty.runtime import get_receipt_lookup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("orchestrator")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    log.info("config %s", settings.redacted())
    # 票 09：模型配置缺失或不一致时启动失败（ConfigError 列出具体项）
    models_cfg = load_models_config(settings.models_config_path, lane_override=settings.model_lane)
    app.state.model_registry = ModelRegistry(models_cfg)
    # 票 43：REPLAY_CASE_ID 设置时加载录制包并核对 {prompt_ver, models_ver, kb_ver, rules_ver}；
    # 不符抛 ReplayIncompatible → 进程启动失败（不静默降级到真实模型）
    app.state.replay = get_replay_package()
    if app.state.replay is not None:
        from app.replay.router import ReplayRouter

        app.state.model_router = ReplayRouter(app.state.model_registry, app.state.replay)
        log.warning("REPLAY MODE %s", app.state.replay.describe())
    else:
        app.state.model_router = ModelRouter(app.state.model_registry)
    set_model_router(app.state.model_router)  # 票 17：图节点取用同一 Router（含全局有界门）
    log.info("models %s", app.state.model_registry.describe())
    # 票 19 / 31：产品目录与排障计划进 L4 内存缓存；计划 next_on / 证据引用不合法时启动失败
    app.state.catalog = ProductCatalog.from_yaml(settings.catalog_config_path)
    app.state.plans = PlanLibrary.from_yaml(settings.plans_config_path)
    app.state.receipt_lookup = get_receipt_lookup()
    app.state.fault_cards = (
        get_fault_card_library()
    )  # 票 33：故障卡 ≤ 800 token、plan_id 合法，否则启动失败
    log.info(
        "catalog v%s products=%d; plans v%s ids=%s",
        app.state.catalog.version,
        len(app.state.catalog.products),
        app.state.plans.version,
        app.state.plans.plan_ids,
    )
    # 票 05：会话存储 + LangGraph PostgresSaver；数据库不可用时不阻止启动，sessions 接口返回 503
    await open_session_runtime(app)
    await open_image_store(app)  # 票 29：复用会话连接池
    handler = configure_logging(settings.observability_log_path)
    exporter = None
    if settings.langfuse_enabled:
        if settings.langfuse_public_key and settings.langfuse_secret_key:
            exporter = LangfuseExporter(
                settings.langfuse_base_url,
                settings.langfuse_public_key,
                settings.langfuse_secret_key,
            )
            exporter.start()
            set_exporter(exporter)
        else:
            log.warning("Langfuse enabled but credentials missing; using JSONL only")
    try:
        yield
    finally:
        set_exporter(None)
        if exporter:
            await exporter.close()
        logging.getLogger().removeHandler(handler)
        handler.close()
        await close_image_store(app)
        await close_session_runtime(app)


def create_app() -> FastAPI:
    app = FastAPI(title="智能服务编排", version="0.1.0", lifespan=_lifespan)
    app.include_router(health_router)
    app.include_router(sessions_router)

    static_dir = Path(settings.static_dir)
    if static_dir.is_dir():
        # 前端构建产物同源托管（票 02）；放在最后以免遮住 API 路由
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


app = create_app()
