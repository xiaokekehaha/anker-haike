from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.admin.router import router as admin_router
from app.analytics.runtime import close_analytics, open_analytics
from app.catalog import ProductCatalog
from app.diagnose.config import get_retrieval_config
from app.health.router import router as health_router
from app.images.runtime import close_image_store, open_image_store
from app.models import ModelRegistry, ModelRouter, load_models_config
from app.models.api import router as models_router
from app.models.probe import ModelProbes
from app.models.runtime import set_model_router
from app.observability.alerts import build_from_settings, health_watch_loop, set_alert_manager
from app.observability.runtime import LangfuseExporter, configure_logging, set_exporter
from app.plans.runtime import get_plan_library
from app.replay.runtime import get_replay_package
from app.retention import retention_loop
from app.sessions.router import router as sessions_router
from app.sessions.runtime import close_session_runtime, open_session_runtime
from app.settings import settings
from app.warranty.service import directory as dealer_directory

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
    probe_disabled = None
    if app.state.replay is not None:
        probe_disabled = "演示回放模式不发起真实模型检测"
    elif os.environ.get("HAIKE_LLM", "on").lower() in ("off", "0", "false"):
        probe_disabled = "当前环境已关闭真实模型调用"
    app.state.model_probes = ModelProbes(app.state.model_registry, disabled_reason=probe_disabled)
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
    # 排障计划由官方 Q&A 生成；Q&A 解析或计划校验不通过时启动失败
    app.state.plans = get_plan_library()
    dealer_directory()  # 启动即加载经销商名录，数据有误时启动失败
    # 检索编排配置同样在启动期校验：retrieval.yaml 与镜像内代码不成对时（典型是 make rollback
    # 只换 config 不换镜像）进程直接起不来，而不是 /health 200、走到诊断节点才 node_failed
    get_retrieval_config()
    log.info(
        "catalog v%s products=%d; plans v%s count=%d",
        app.state.catalog.version,
        len(app.state.catalog.products),
        app.state.plans.version,
        len(app.state.plans.plan_ids),
    )
    # 票 05：会话存储 + LangGraph PostgresSaver；数据库不可用时不阻止启动，sessions 接口返回 503
    await open_session_runtime(app)
    await open_image_store(app)  # 票 29：复用会话连接池
    await open_analytics(app)  # 管理员观测台：事实采集 sink（复用会话连接池）
    # 票 48：分类 TTL 清理循环（会话 24 h / 追踪 7 d；图片 1 h 由 images.runtime 负责）
    app.state.retention_task = (
        asyncio.create_task(retention_loop(app.state.session_pool), name="retention")
        if getattr(app.state, "session_pool", None) is not None
        else None
    )
    handler = configure_logging(settings.observability_log_path)
    # 票 50：最简告警——规则挂在 record() 上；/health 连续失败由后台探测
    from app.health.router import aggregator as health_aggregator

    app.state.alerts = build_from_settings(settings)
    set_alert_manager(app.state.alerts)
    app.state.health_watch_task = asyncio.create_task(
        health_watch_loop(health_aggregator, app.state.alerts, settings.alert_health_interval_s),
        name="health-watch",
    )
    log.info("alerts sinks=%s thresholds=%s", [x.name for x in app.state.alerts.sinks], app.state.alerts.t)
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
        await app.state.model_probes.close()
        set_exporter(None)
        if exporter:
            await exporter.close()
        logging.getLogger().removeHandler(handler)
        handler.close()
        if getattr(app.state, "health_watch_task", None) is not None:
            app.state.health_watch_task.cancel()
        if getattr(app.state, "alerts", None) is not None:
            await app.state.alerts.drain()
            set_alert_manager(None)
        if getattr(app.state, "retention_task", None) is not None:
            app.state.retention_task.cancel()
        await close_analytics(app)
        await close_image_store(app)
        await close_session_runtime(app)


def create_app() -> FastAPI:
    app = FastAPI(title="智能服务编排", version="0.1.0", lifespan=_lifespan)
    app.include_router(health_router)
    app.include_router(models_router)
    app.include_router(sessions_router)
    from app.admin.l3_router import router as l3_router
    app.include_router(l3_router)
    app.include_router(admin_router)  # 管理员观测台 /admin/api/*（黑客松范围无鉴权）

    static_dir = Path(settings.static_dir)
    admin_index = static_dir / "admin" / "index.html"
    if admin_index.is_file():
        # 观测台是单页应用：/admin 下的深链（/admin/sessions/<id>）都回同一个 index.html，
        # 由前端路由接管。注册在静态挂载之前、API 之后，不会遮住 /admin/api/*。
        @app.get("/admin", include_in_schema=False)
        @app.get("/admin/{path:path}", include_in_schema=False)
        async def admin_spa(path: str = "") -> FileResponse:
            return FileResponse(admin_index)

    if static_dir.is_dir():
        # 前端构建产物同源托管（票 02）；放在最后以免遮住 API 路由
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


app = create_app()
